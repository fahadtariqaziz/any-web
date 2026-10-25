"""Triggers: what makes the builder act, in one table (spec §10.8 "explicit conditions for transitions"; M11).

`TRIGGERS` lists every event → condition → action of the platform and where it is implemented. The graph's own
transitions are decided by pure-Python route functions (graph.py) on the checkpointed state, never by an LLM alone;
the human pauses are interrupts (section 5 of handoff.md). Two triggers run without a user:
- the idle-preview stop: a thread in the API process (workspace/processes.IdleStopper) stops dev servers nobody
  looked at for PREVIEW_IDLE_MINUTES; `run_idle_previews()` runs the same job on demand (POST /api/triggers/idle-previews);
- startup reconcile: the API adopts dev servers that survived a restart and kills sandbox commands whose owner died.
(The health app's scheduled "check-in" chat messages were retired in M11: an app builder has no reason to message
a quiet user.)
"""

import logging

from ai_decision_arena.config import get_settings

log = logging.getLogger(__name__)

TRIGGERS: list[dict] = [
    {"event": "new prompt", "condition": "it describes an app / website (intake)", "action": "clarification",
     "where": "POST /api/decisions → intake → route_after_clarification"},
    {"event": "clarification decided", "condition": "material requirements missing, rounds left (≤ 3)",
     "action": "pause for answers", "where": "clarification → await_clarification"},
    {"event": "requirements clear", "condition": "no question left or rounds used", "action": "research (3 domains)",
     "where": "route_after_clarification"},
    {"event": "research done", "condition": "always", "action": "proposer → critic → judge", "where": "graph edges"},
    {"event": "judge verdict", "condition": "more research / clarification asked AND loops_allowed (rounds, time, "
     "LLM budget)", "action": "research or clarification, else evidence check", "where": "route_after_judge, limits.py"},
    {"event": "evidence checked", "condition": "material gap AND loops_allowed", "action": "research, else brief",
     "where": "route_after_evidence_checker"},
    {"event": "brief validated", "condition": "revise ≤ max_brief_revisions / clarify if loops allowed / approve",
     "action": "rewrite, clarification, or pause for review", "where": "route_after_brief_validator"},
    {"event": "brief review reply", "condition": "approve (hash of the reviewed text) / change + target "
     "(wording-only once built or after max_review_rounds)", "action": "planner, or the target node",
     "where": "await_brief_review → brief_review_router"},
    {"event": "plan review reply", "condition": "approve (plan AND brief hashes) / change (≤ max_plan_revisions)",
     "action": "implementer, or planner", "where": "plan_review_router, route_after_plan_review"},
    {"event": "task attempt finished", "condition": "tasks pending AND agent budget left", "action": "next task, "
     "else build check", "where": "route_after_implementer"},
    {"event": "build check failed", "condition": "fix rounds left AND agent budget left", "action": "fix task F<n>, "
     "else preview anyway", "where": "route_after_build_check"},
    {"event": "build check done", "condition": "always", "action": "(re)start the preview, pause for changes",
     "where": "preview → await_change_request"},
    {"event": "change pause reply", "condition": "change (≤ max_change_requests) / replan / finish",
     "action": "task C<n> / brief first then plan extension / completion", "where": "change_request_router"},
    {"event": "reopen", "condition": "finished AND built", "action": "same as a change pause reply",
     "where": "POST /resume {type: reopen}"},
    {"event": "node raised", "condition": "any error stored", "action": "completion (failed)", "where": "guarded edges"},
    {"event": "interrupted run (restart)", "condition": "checkpoint has a next node", "action": "resume without "
     "repeating finished steps", "where": "POST /resume {type: continue}"},
    {"event": "preview idle", "condition": f"no GET /preview for preview_idle_minutes", "action": "stop the dev server",
     "where": "IdleStopper thread / POST /api/triggers/idle-previews"},
    {"event": "API start", "condition": "always", "action": "adopt live dev servers, kill orphaned commands",
     "where": "ProcessManager.reconcile (lifespan)"},
]


def run_idle_previews(manager, idle_minutes: float | None = None) -> list[str]:
    """Stop the previews idle for `idle_minutes` (default PREVIEW_IDLE_MINUTES) now; returns their session ids."""
    stopped = manager.stop_idle(idle_minutes if idle_minutes is not None else get_settings().preview_idle_minutes)
    if stopped:
        log.info("idle previews stopped on demand: %s", stopped)
    return stopped
