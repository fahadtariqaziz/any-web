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
  With settings.auto_approve_plan (default) there is no pause: the brief approval covers the plan, the node writes an
  "approve" reply marked auto, and the router records the approval (hash) exactly like a user approval.
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
from ai_decision_arena.plan import (built_part, extension_schema_for, merge_extension, plan_hash, plan_schema_for,
                                   render_plan_markdown, tasks_from_plan)
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
- At most {max_tasks}, in execution order. Prefer FEWER, LARGER tasks: each one a coherent feature slice with its
  tests that the coding agent can still implement and verify in one go (e.g. "the calculation engine: tokenizer,
  evaluator and formatting, with their tests"), not single files or tiny steps. Aim for about 4-8 tasks for a small
  app (a single-page tool, a few screens) and at most about 12 for a larger one: every task costs a fixed overhead
  (agent start, reading the code, verification). The first task scaffolds the project (package manifest, folder
  structure, test runner configured, a trivial passing test) so every later task can be verified.
- depends_on lists earlier task ids only, and ONLY real dependencies (the task uses or extends that task's code or
  files): independent tasks are built in parallel, so a chain of false dependencies makes the build slower. Give
  independent tasks separate files (two tasks never write the same file unless one depends on the other) and put
  shared setup (package manifest, configs) in the first task. files are relative paths inside the project.
- acceptance_criteria are checkable outcomes. verify_commands prove them by running real tests or scripts from the
  project root: each is ONE plain command (no &&, ;, pipes, redirects or env assignments), starting with one of:
  {executables}. Prefer the project's test runner (e.g. "npm test", "npx vitest run tests/engine.test.js").
- feature_coverage: one entry per MVP feature in <mvp_features>, the feature copied EXACTLY as written there, with
  the task ids that implement it.
- commands.dev starts the dev server and must make it listen on the port given in the PORT environment variable
  (configure the dev script accordingly, e.g. Vite `--port $PORT` belongs in the package.json script, not in the
  command). The generated project runs in its own folder; never publish, push or touch files outside it.
- Never put secrets in the code; apps that need keys read them from environment variables and ship a .env.example.
- Apps with a user interface must look like a finished product, not browser defaults. Choose the styling approach in
  tech_stack (prefer Tailwind CSS; a hand-written CSS design system with tokens is fine for very small apps) and make
  the FIRST task set up the design foundation with it: the app shell (top bar or sidebar navigation, content column)
  and shared UI components (button, input / select with label, form layout, card, table, page header, alert, empty
  state). Every later UI task builds its screens from those components and lists "styled with the shared components:
  labelled stacked form fields, tables for records, an empty state" among its acceptance_criteria.
- The preview runs the dev server WITHOUT a .env file and is checked in a headless browser: the first screen must
  render even when settings or external services (e.g. a Supabase URL and key) are missing. Plan that no module
  throws at import time over missing configuration; the app shows a screen that names the missing settings instead.
""" + BUILDER_RULES

REVISION_NOTE = """
This is a REVISION requested by the user. <previous_plan> is the plan they reviewed and <plan_feedback> their change
requests (the last one is new). Apply them, keep what they did not ask to change, and stay within the approved brief:
if a request contradicts the brief, follow the brief and say so in risks_and_decisions."""


EXTENSION_NOTE = """
The app is ALREADY BUILT and running: <built_plan> lists the tasks that were built (their code exists), <built_tasks>
their verified status, <later_changes> the change requests done after the plan, <project_files> the files in the
project now. The approved brief was updated; <requested_change> is what the user asked for. Write a PlanExtension:
ONLY the new work that takes the built app to the updated brief, as few small tasks as possible, ids continuing after
the highest built task id. Never repeat or rebuild built work: change existing files where needed (name them in
`files`) and keep every built feature, test and later change working. depends_on may name built tasks.
feature_coverage covers every MVP feature of the brief, citing built task ids for features that already exist. The
descriptive fields (summary, tech_stack, project_structure, architecture, commands...) describe the whole project
after the change; keep the built project's commands unless the change needs new ones."""

MAX_PROJECT_FILES = 150


def _project_files(state: ArenaState) -> list[str]:
    """Relative paths in the session's app/ (without dependency / build folders), for the extension planner."""
    from ai_decision_arena.workspace.export import collect
    from ai_decision_arena.workspace.paths import workspace_for
    thread_id = (get_config().get("configurable") or {}).get("thread_id", "")
    try:
        return [rel for rel, _ in collect(workspace_for(thread_id), state.get("project_name")).files][:MAX_PROJECT_FILES]
    except Exception:                                            # noqa: BLE001 - the list is context, not a requirement
        return []


def requested_change(state: ArenaState) -> str:
    """The user's latest bigger-change request (it went to the brief first: brief_feedback source change_request)."""
    for f in reversed(state.get("brief_feedback", [])):
        if f.get("source") == "change_request":
            return f["feedback"]
    return ""


def _approved_brief(state: ArenaState) -> ProblemBrief:
    return ProblemBrief.model_validate(state["brief"])


def _user_content(state: ArenaState, brief: ProblemBrief, revising: bool, built: ImplementationPlan | None = None) -> str:
    content = brief.model_dump(mode="json", include=set(BriefContent.model_fields))
    references = [{"number": r.number, "title": r.title, "url": str(r.url)} for r in brief.references]
    text = f"""<project_name>{state.get("project_name", "")}</project_name>
<approved_brief>{json.dumps(content, indent=1)}</approved_brief>
<brief_references>{json.dumps(references, indent=1)}</brief_references>
<mvp_features>{json.dumps(brief.proposed_solution.mvp_features, indent=1)}</mvp_features>"""
    if built is not None:
        status = {t["id"]: t["status"] for t in state.get("implementation_tasks", [])}
        later = [{"id": t["id"], "title": t["title"], "status": t["status"],
                  "request": ((t.get("spec") or {}).get("description") or "")[-400:]}
                 for t in state.get("implementation_tasks", []) if t.get("phase") in ("change", "fix")]
        text += f"""
<built_plan>{json.dumps(built.model_dump(mode="json"), indent=1)}</built_plan>
<built_tasks>{json.dumps([{"id": t.id, "status": status.get(t.id)} for t in built.tasks])}</built_tasks>
<later_changes>{json.dumps(later, indent=1)}</later_changes>
<project_files>{json.dumps(_project_files(state))}</project_files>
<requested_change>{requested_change(state) or "(see the brief: bring the app in line with it)"}</requested_change>"""
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
    stored = ImplementationPlan.model_validate(state["implementation_plan"]) if state.get("implementation_plan") else None
    built = built_part(stored, state.get("implementation_tasks", [])) if stored else None      # the app already exists
    revision = state.get("plan_revision_count", 0) + (1 if revising or built is not None else 0)
    model, note = resolve_model(settings.planner_model)
    if note:
        report("planner", note)
    doing = ("planning only the new work on top of the built app" if built is not None
             else "revising the plan with your changes" if revising else "writing the implementation plan")
    report("planner", f"{doing} with {model} (effort {settings.planner_effort}); this takes a few minutes")

    system = (SYSTEM_PROMPT.replace("{max_tasks}", str(MAX_PLAN_TASKS))
              .replace("{executables}", ", ".join(ALLOWED_EXECUTABLES))
              + (EXTENSION_NOTE if built is not None else "") + (REVISION_NOTE if revising else ""))
    mvp = brief.proposed_solution.mvp_features
    schema = extension_schema_for(mvp, built) if built is not None else plan_schema_for(mvp)
    out = call_structured(schema, system, _user_content(state, brief, revising, built),
                          max_tokens=settings.planner_max_tokens, run_name="planner_llm", model=model,
                          effort=settings.planner_effort, timeout=settings.planner_timeout_seconds)
    if built is not None:
        # Built tasks keep their status / attempts / results (and the C / F tasks after the plan); new ones are pending.
        plan = ImplementationPlan.model_validate(merge_extension(built, out))
        worked = [t for t in state.get("implementation_tasks", []) if t.get("status") != "pending"]
        new_ids = {t.id for t in out.tasks}
        tasks = worked + [t for t in tasks_from_plan(plan) if t["id"] in new_ids]
        built_ids = frozenset(t.id for t in built.tasks)
    else:
        plan = ImplementationPlan.model_validate(out.model_dump())      # store the plain schema
        tasks, built_ids = tasks_from_plan(plan), frozenset()
    markdown = render_plan_markdown(plan, state.get("project_name", ""), revision, model, built_ids)
    report("planner", f"plan ready: {len(plan.phases)} phases, {len(plan.tasks)} tasks"
                      + (f" ({len(plan.tasks) - len(built_ids)} new, {len(built_ids)} built)" if built_ids else "")
                      + f", {len(plan.feature_coverage)} MVP features covered")
    return {
        "implementation_plan": plan.model_dump(mode="json"),
        "plan_markdown": markdown,
        "plan_revision_count": revision,
        "implementation_tasks": tasks,
        "models_used": {**state.get("models_used", {}), "planner": model},
        "status": "awaiting_plan_review",
        "current_node": "planner",
    }


def await_plan_review_node(state: ArenaState) -> dict:
    """Human input: show the plan and pause until the user approves or asks for changes. (No LLM here.)"""
    settings = get_settings()
    if settings.auto_approve_plan:
        report("await_plan_review", "plan approved automatically (the approved brief covers it; AUTO_APPROVE_PLAN)")
        entry = {"round": state.get("plan_revision_count", 0) + 1, "action": "approve", "feedback": "", "auto": True,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return {"plan_feedback": [*state.get("plan_feedback", []), entry], "current_node": "await_plan_review"}
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
        "new_task_count": sum(t.get("status") == "pending" for t in state.get("implementation_tasks", [])),
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
