"""Node 13 — Planner (spec §7) and the plan review by the user (pause + router, like the brief review).

planner_node (LLM, ONE call on settings.planner_model = claude-opus-5-5 at effort "high"):
  Writes a Claude-Code-style implementation plan from the APPROVED brief only: phases, tasks with dependencies,
  files, acceptance criteria and verify commands, project structure, dependencies, architecture, APIs, components,
  data model, integrations, AI components only where the brief needs them, testing strategy, commands, risks.
  Python then checks it (schema validators: unique ids, dependencies in order, relative files, allowlisted
  commands, every approved MVP feature covered) - a failed check goes back to the planner with the exact problem.
  Guard: the planner refuses to run unless the brief in the state is the one the user approved (hash).
  The model is resolved against the API's model list (llm.resolve_model): never assumed to exist.

await_plan_review_node (human): shows the plan, pauses; reply = approve | request_changes + feedback.
plan_review_router_node (Python): approve → plan_approved_at + hash, saved to project_artifacts; changes → planner
  (the next plan gets the previous plan and the feedback). After max_plan_revisions rewrites the plan can only be
  approved. Nothing is built before both approvals (the implementer route checks plan_is_approved, M8).

Writes (owner): implementation_plan, plan_markdown, plan_revision_count, implementation_tasks, models_used (planner);
plan_feedback, plan_review_round (await); plan_review_route, plan_approved_at, plan_approved_hash (router).
"""

import json
from datetime import datetime, timezone

from langgraph.config import get_config
from langgraph.types import interrupt
from pydantic import ValidationError

from ai_decision_arena.brief import brief_is_approved
from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured, resolve_model
from ai_decision_arena.plan import plan_hash, plan_schema_for, render_plan_markdown, tasks_from_plan
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES
from ai_decision_arena.schemas import (ALLOWED_EXECUTABLES, BriefContent, ImplementationPlan, MAX_PLAN_TASKS,
                                       PlanReviewReply, ProblemBrief)
from ai_decision_arena.state import ArenaState

SYSTEM_PROMPT = """You are the Planner of an AI application builder. Write the implementation plan a coding agent will follow
task by task, like a senior engineer preparing work for Claude Code. The plan is based ONLY on the approved problem
statement and solution brief in <approved_brief>: never contradict it, never add features it does not ask for, and
settle every major architectural decision here so the coder never has to make one.

Cover: the tech stack with reasons (prefer what the brief recommends; a technology the user required is mandatory),
project structure, dependencies, architecture and data flow, data model / storage, API endpoints, frontend
components, backend services, integrations, AI components only if the brief needs them, phases, tasks, testing
strategy, the commands to install / test / build / run, and the risks or decisions to settle.

Tasks:
- At most {max_tasks}, in execution order, each small enough to implement and verify in one go (a module, a
  component, a feature slice). The first task scaffolds the project (package manifest, folder structure, test runner
  configured, a trivial passing test) so every later task can be verified.
- depends_on lists earlier task ids only. files are relative paths inside the project.
- acceptance_criteria are checkable outcomes. verify_commands prove them by running real tests or scripts from the
  project root: each is ONE plain command (no &&, ;, pipes, redirects or env assignments), starting with one of:
  {executables}. Prefer the project's test runner (e.g. "npm test", "npx vitest run tests/engine.test.js").
- feature_coverage: one entry per MVP feature in <mvp_features>, the feature copied EXACTLY as written there, with
  the task ids that implement it.
- commands.dev starts the dev server and must make it listen on the port given in the PORT environment variable
  (configure the dev script accordingly, e.g. Vite `--port $PORT` belongs in the package.json script, not in the
  command). The generated project runs in its own folder; never publish, push or touch files outside it.
- Never put secrets in the code; apps that need keys read them from environment variables and ship a .env.example.
""" + BUILDER_RULES

REVISION_NOTE = """
This is a REVISION requested by the user. <previous_plan> is the plan they reviewed and <plan_feedback> their change
requests (the last one is new). Apply them, keep what they did not ask to change, and stay within the approved brief:
if a request contradicts the brief, follow the brief and say so in risks_and_decisions."""


def _approved_brief(state: ArenaState) -> ProblemBrief:
    return ProblemBrief.model_validate(state["brief"])


def _user_content(state: ArenaState, brief: ProblemBrief, revising: bool) -> str:
    content = brief.model_dump(mode="json", include=set(BriefContent.model_fields))
    references = [{"number": r.number, "title": r.title, "url": str(r.url)} for r in brief.references]
    text = f"""<project_name>{state.get("project_name", "")}</project_name>
<approved_brief>{json.dumps(content, indent=1)}</approved_brief>
<brief_references>{json.dumps(references, indent=1)}</brief_references>
<mvp_features>{json.dumps(brief.proposed_solution.mvp_features, indent=1)}</mvp_features>"""
    if revising:
        previous = ImplementationPlan.model_validate(state["implementation_plan"]).model_dump(mode="json")
        requests = [f["feedback"] for f in state.get("plan_feedback", []) if f["action"] == "request_changes"]
        text += f"""
<previous_plan>{json.dumps(previous, indent=1)}</previous_plan>
<plan_feedback>{json.dumps(requests, indent=1)}</plan_feedback>"""
    return text


def planner_node(state: ArenaState) -> dict:
    if not brief_is_approved(state):
        # Hard guard (the route also checks): planning starts only from the brief the user approved.
        raise RuntimeError("Planning needs the approved brief, but the brief in this session is not approved "
                           "(or changed after approval).")
    settings = get_settings()
    brief = _approved_brief(state)
    revising = bool(state.get("implementation_plan")) and state.get("plan_review_route") == "changes"
    revision = state.get("plan_revision_count", 0) + (1 if revising else 0)
    model, note = resolve_model(settings.planner_model)
    if note:
        report("planner", note)
    report("planner", f"{'revising the plan with your changes' if revising else 'writing the implementation plan'} "
                      f"with {model} (effort {settings.planner_effort}); this takes a few minutes")

    system = (SYSTEM_PROMPT.replace("{max_tasks}", str(MAX_PLAN_TASKS))
              .replace("{executables}", ", ".join(ALLOWED_EXECUTABLES)) + (REVISION_NOTE if revising else ""))
    plan = call_structured(plan_schema_for(brief.proposed_solution.mvp_features), system,
                           _user_content(state, brief, revising), max_tokens=settings.planner_max_tokens,
                           run_name="planner_llm", model=model, effort=settings.planner_effort,
                           timeout=settings.planner_timeout_seconds)
    plan = ImplementationPlan.model_validate(plan.model_dump())         # store the plain schema
    markdown = render_plan_markdown(plan, state.get("project_name", ""), revision, model)
    report("planner", f"plan ready: {len(plan.phases)} phases, {len(plan.tasks)} tasks, "
                      f"{len(plan.feature_coverage)} MVP features covered")
    return {
        "implementation_plan": plan.model_dump(mode="json"),
        "plan_markdown": markdown,
        "plan_revision_count": revision,
        "implementation_tasks": tasks_from_plan(plan),
        "models_used": {**state.get("models_used", {}), "planner": model},
        "status": "awaiting_plan_review",
        "current_node": "planner",
    }


def await_plan_review_node(state: ArenaState) -> dict:
    """Human input: show the plan and pause until the user approves or asks for changes. (No LLM here.)"""
    settings = get_settings()
    revisions = state.get("plan_revision_count", 0)
    changes_allowed = revisions < settings.max_plan_revisions
    plan = state.get("implementation_plan") or {}
    payload = {
        "type": "plan_review",
        "plan_markdown": state.get("plan_markdown", ""),
        "plan": plan,
        "round": revisions + 1,
        "max_revisions": settings.max_plan_revisions,
        "changes_allowed": changes_allowed,
        "model": (state.get("models_used") or {}).get("planner", ""),
        "task_count": len(plan.get("tasks", [])),
    }

    error = None
    while True:
        raw = interrupt((payload | {"error": error}) if error else payload)
        try:
            reply = PlanReviewReply.model_validate(raw)
        except ValidationError as exc:
            error = f"Invalid reply: {exc.errors()[0]['msg']}"
            continue
        if reply.action == "request_changes" and not changes_allowed:
            error = (f"The plan was already revised {revisions} times: it can only be approved now "
                     "(or start a new session).")
            continue
        break

    entry = {"round": revisions + 1, "action": reply.action, "feedback": reply.feedback.strip(),
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return {"plan_feedback": [*state.get("plan_feedback", []), entry], "current_node": "await_plan_review"}


def _save_approved_plan(state: ArenaState, approved_at: str, digest: str) -> None:
    from ai_decision_arena.db.repository import save_artifact

    thread_id = (get_config().get("configurable") or {}).get("thread_id") or state.get("thread_id", "")
    if not get_settings().persist_results or not thread_id:
        return
    try:
        version = save_artifact(thread_id, "plan", state.get("plan_markdown", ""), state.get("implementation_plan") or {},
                                digest, approved_at)
        report("plan_review_router", f"approved plan saved as version {version}")
    except Exception as exc:
        report("plan_review_router", f"could not save the approved plan ({type(exc).__name__}); it stays in the session")


def plan_review_router_node(state: ArenaState) -> dict:
    last = state.get("plan_feedback", [])[-1]
    update: dict = {"current_node": "plan_review_router"}
    if last["action"] == "approve":
        approved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        digest = plan_hash(state.get("plan_markdown", ""))
        _save_approved_plan(state, approved_at, digest)
        report("plan_review_router", "decision: approved; the plan is ready for implementation")
        return update | {"plan_review_route": "approved", "plan_approved_at": approved_at,
                         "plan_approved_hash": digest, "status": "reporting"}
    report("plan_review_router", "decision: request_changes → planner")
    return update | {"plan_review_route": "changes", "plan_approved_at": None, "plan_approved_hash": None,
                     "status": "planning"}
