"""Node 12 — Brief review by the user (spec §6), split in TWO graph nodes like clarification:

- await_brief_review_node   (human)  shows the validated brief and pauses with interrupt(); stores the reply.
                                     No LLM here: on resume LangGraph re-runs the node from its first line.
- brief_review_router_node  (Python, + one small LLM call only when the user left target="auto")
                                     approve → records the approval (time + hash of the approved markdown) and saves
                                     the approved version to project_artifacts;
                                     request_changes → decides where the change goes.

Where changes go (spec §6): a misunderstanding of the requirements → clarification; a research quality issue →
research (the feedback becomes the research focus); a proposal issue → proposer; wording → brief_writer (edits the
previous draft). Every path comes back through brief_writer → brief_validator, so a revised brief is always
revalidated before it is shown again. The user's feedback reaches every agent through <brief_feedback> in the
shared case block (prompting.user_case_block).

Loops are bounded by max_review_rounds: once that many change requests were made, only wording changes (or
approval) are accepted. Nothing is planned or built before an explicit approval (spec §12).

Writes (owner): brief_feedback, brief_review_round_count (await); brief_review_route, brief_approved_at,
brief_approved_hash, brief_revision_count (reset), research_focus, status, current_node (router).
"""

from datetime import datetime, timezone

from langgraph.config import get_config
from langgraph.types import interrupt
from pydantic import ValidationError

from ai_decision_arena.brief import brief_hash
from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, user_case_block
from ai_decision_arena.schemas import BriefReviewReply, FeedbackRouting
from ai_decision_arena.state import ArenaState

ROUTING_PROMPT = """You route a user's change request on a project's problem statement and solution brief to the step of an
AI application builder that can make the change. Read the request (the LAST item of <brief_feedback>) and the brief's
summary, and pick ONE target:
- requirements: the brief misunderstood what the user wants (audience, purpose, must-have features, platform,
  constraints), or the user adds a new requirement. The requirements are re-clarified and everything is redone.
- research: the user says facts, sources or evidence are missing, outdated or wrong, or asks to look into something.
- proposal: the requirements and facts are fine but the recommended solution should change (another approach,
  architecture, technology, feature set or scope).
- wording: the content is right; the text should be clearer, shorter, reordered, or a small detail added or removed.
Prefer the cheapest target that can really make the change (wording < proposal < research < requirements).
""" + BUILDER_RULES

STATUS_BY_ROUTE = {"wording": "writing_brief", "requirements": "intake", "research": "researching", "proposal": "debating"}


def await_brief_review_node(state: ArenaState) -> dict:
    """Human input: show the brief and pause until the user approves or asks for changes. (No LLM here.)"""
    settings = get_settings()
    validation = state.get("brief_validation") or {}
    rounds_used = state.get("brief_review_round_count", 0)
    # Once the app is BUILT (M10: a bigger change reopened the brief), the brief may only be edited: re-research, a new
    # proposal or new requirements would re-run the debate and describe a different app than the one that exists.
    built = bool(state.get("workspace_dir"))
    wording_only = built or rounds_used >= settings.max_review_rounds
    checks = validation.get("checks", [])
    payload = {
        "type": "brief_review",
        "brief_markdown": state.get("brief_markdown", ""),
        "brief": state.get("brief"),
        "validation_summary": {
            "checks_passed": sum(1 for c in checks if c["passed"]),
            "checks_total": len(checks),
            "open_issues": validation.get("open_issues", []),
            "word_count": validation.get("word_count", 0),
            "word_budget": validation.get("word_budget", 0),
        },
        "unresolved_questions": state.get("unresolved_questions", []),
        "round": rounds_used + 1,
        "max_rounds": settings.max_review_rounds,
        "wording_only": wording_only,
        "wording_only_reason": "built" if built else "rounds" if wording_only else None,
    }

    error = None
    while True:
        raw = interrupt((payload | {"error": error}) if error else payload)
        try:
            reply = BriefReviewReply.model_validate(raw)
        except ValidationError as exc:
            error = f"Invalid reply: {exc.errors()[0]['msg']}"
            continue
        if reply.action == "request_changes" and wording_only and reply.target not in ("auto", "wording"):
            error = ("Your app is already built: changes to the brief are applied as edits (wording) only."
                     if built else f"The brief was already revised {rounds_used} times: only wording changes (or "
                     "approval) are accepted now.")
            continue
        break

    target = "wording" if (reply.action == "request_changes" and wording_only) else reply.target
    entry = {"round": rounds_used + 1, "action": reply.action, "target": target, "feedback": reply.feedback.strip(),
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return {
        "brief_feedback": [*state.get("brief_feedback", []), entry],
        "brief_review_round_count": rounds_used + (1 if reply.action == "request_changes" else 0),
        "current_node": "await_brief_review",
    }


def _route_by_llm(state: ArenaState) -> FeedbackRouting:
    brief = state.get("brief") or {}
    summary = {
        "problem": (brief.get("problem_statement") or {}).get("statement", {}).get("text", ""),
        "solution": (brief.get("proposed_solution") or {}).get("how_it_addresses_problem", {}).get("text", ""),
        "mvp_features": (brief.get("proposed_solution") or {}).get("mvp_features", []),
        "architecture": (brief.get("architecture") or {}).get("overview", {}).get("text", ""),
    }
    return call_structured(FeedbackRouting, ROUTING_PROMPT, f"{user_case_block(state)}\n<brief_summary>{summary}</brief_summary>",
                           max_tokens=600, run_name="brief_feedback_routing_llm")


def _save_approved_brief(state: ArenaState, approved_at: str, digest: str) -> None:
    """Approved versions are kept in project_artifacts (spec §10.6). The checkpoint stays the source of truth: a failed
    save is reported, not fatal (completion saves the session again at the end)."""
    from ai_decision_arena.db.repository import save_artifact

    # The API does not put thread_id into the state: read it from the run's config (like completion does).
    thread_id = (get_config().get("configurable") or {}).get("thread_id") or state.get("thread_id", "")
    if not get_settings().persist_results or not thread_id:
        report("brief_review_router", "approved brief not saved to project_artifacts (persistence off or no thread id)"
               if get_settings().persist_results else "persistence off: approved brief kept in the session only")
        return
    try:
        version = save_artifact(thread_id, "brief", state.get("brief_markdown", ""), state.get("brief") or {},
                                digest, approved_at)
        report("brief_review_router", f"approved brief saved as version {version}")
    except Exception as exc:
        report("brief_review_router", f"could not save the approved brief ({type(exc).__name__}); it stays in the session")


def brief_review_router_node(state: ArenaState) -> dict:
    """Apply the user's reply: record the approval, or decide where the change request goes."""
    last = state.get("brief_feedback", [])[-1]
    update: dict = {"current_node": "brief_review_router", "brief_revision_count": 0}

    if last["action"] == "approve":
        approved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        digest = brief_hash(state.get("brief_markdown", ""))
        _save_approved_brief(state, approved_at, digest)
        report("brief_review_router", "decision: approved; the brief is the basis for planning")
        return update | {"brief_review_route": "approved", "brief_approved_at": approved_at,
                         "brief_approved_hash": digest, "status": "planning"}

    target = last["target"]
    if target == "auto":
        routing = _route_by_llm(state)
        target = routing.target
        report("brief_review_router", f"your request goes to: {target} ({routing.reasoning[:160]})")
    feedback = [*state["brief_feedback"][:-1], last | {"resolved_target": target}]
    update |= {"brief_feedback": feedback, "brief_review_route": target, "status": STATUS_BY_ROUTE[target],
               "brief_approved_at": None, "brief_approved_hash": None}
    if target == "research":
        update["research_focus"] = [f"The user asked, reviewing the brief: {last['feedback']}"]
    elif target == "requirements":     # clarification → research: the follow-up search covers the corrected requirements
        update["research_focus"] = [f"The user corrected the requirements, reviewing the brief: {last['feedback']}. "
                                    "Find evidence for what this changes."]
    report("brief_review_router", f"decision: request_changes → {target}")
    return update
