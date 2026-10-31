"""The AI App Builder graph.

    START → intake → clarification ─┬─(need_clarification)─► await_clarification ─► clarification (loop, ≤ 3 rounds)
                                    └─(enough info)────────► research → proposer → critic → judge
    judge ─┬─(request_more_research: thin evidence OR a material claim of the winner unverified)──► research
           ├─(request_clarification)──► clarification                      (both focused; bounded by limits.py)
           └─(proceed / insufficient_evidence)──► final_report
    final_report → brief_writer → brief_validator ─┬─(revise, ≤ max_brief_revisions)──► brief_writer
                                                   ├─(clarify, loop allowed)──────────► clarification
                                                   └─(approve)────────────────────────► await_brief_review (pause)
    await_brief_review → brief_review_router ─┬─(approved, hash guard)► planner (Opus) → await_plan_review (pause)
                                              ├─(wording)─────► brief_writer
                                              ├─(requirements)► clarification
                                              ├─(research)────► research
                                              └─(proposal)────► proposer
    await_plan_review → plan_review_router ─┬─(approved, both hashes)─► implementer
                                            └─(changes, ≤ max_plan_revisions)► planner
    implementer ─┬─(a task is pending: one attempt per step)─► implementer
                 └─(all done / failed / blocked / budget)─────► build_check
    build_check ─┬─(failed, fix round left: a fix task was added)─► implementer
                 └─────────────────────────────────────────────────► code_review
    code_review ─┬─(high-severity findings, review fix round left: a fix task)─► implementer
                 └─(passed / skipped (COMPOUND_ENGINEERING=false, build failed, nothing changed))─► preview
    preview ─┬─(page blank in headless Chrome, fix round left: a fix task was added)─► implementer
             └──────────────────────────────────────────────────────────────────────► e2e_check
    e2e_check ─┬─(no browser tests yet: task E1 writes them / a test failed, fix round left: a fix task)─► implementer
               └─(passed / skipped / no fix round left)──────────────────────────────────────────────────► await_change_request (pause)
    await_change_request → change_request_router ─┬─(change: new task)─► implementer
                                                  ├─(replan)──────────► brief_writer (bigger change: brief review, then a plan extension and plan review)
                                                  └─(finish)──────────► completion → END
    Any node that raises → its error is stored (nodes/node_wrapper.py) → completion (status failed).

Every edge is "guarded": if the state carries an error, the graph goes straight to completion. Nodes are not
retried here: every LLM call already retries and falls back to a second model (llm.py).

Risk flags never change routing: they are recorded and shown, and the Proposer / Judge take them into account.
"""

from typing import Callable, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ai_decision_arena.brief import brief_is_approved
from ai_decision_arena.nodes.planner import await_plan_review_node, plan_review_router_node, planner_node
from ai_decision_arena.plan import plan_is_approved
from ai_decision_arena.nodes.brief_review import await_brief_review_node, brief_review_router_node
from ai_decision_arena.nodes.brief_validator import brief_validator_node
from ai_decision_arena.nodes.brief_writer import brief_writer_node
from ai_decision_arena.nodes.clarification import await_clarification_node, clarification_node
from ai_decision_arena.nodes.code_review import code_review_node
from ai_decision_arena.nodes.critic import critic_node
from ai_decision_arena.nodes.final_report import completion_node, final_report_node
from ai_decision_arena.nodes.delivery import (await_change_request_node, build_check_node, change_request_router_node,
                                              e2e_check_node, preview_node)
from ai_decision_arena.nodes.implementer import implementer_node
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.judge import judge_node
from ai_decision_arena.nodes.node_wrapper import wrap_node
from ai_decision_arena.nodes.proposer import proposer_node
from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.state import ArenaState

# Nodes wrapped by wrap_node (session mode, active time, failure → state).
NODES = {
    "intake": intake_node,
    "clarification": clarification_node,
    "await_clarification": await_clarification_node,
    "research": research_node,
    "proposer": proposer_node,
    "critic": critic_node,
    "judge": judge_node,
    "final_report": final_report_node,
    "brief_writer": brief_writer_node,
    "brief_validator": brief_validator_node,
    "await_brief_review": await_brief_review_node,
    "brief_review_router": brief_review_router_node,
    "planner": planner_node,
    "await_plan_review": await_plan_review_node,
    "plan_review_router": plan_review_router_node,
    "implementer": implementer_node,
    "build_check": build_check_node,
    "code_review": code_review_node,
    "preview": preview_node,
    "e2e_check": e2e_check_node,
    "await_change_request": await_change_request_node,
    "change_request_router": change_request_router_node,
}


# --- routing functions: read the state, return the NAME of the next step ------------

def route_after_clarification(state: ArenaState) -> Literal["await_clarification", "research"]:
    return "await_clarification" if state.get("need_clarification") else "research"


def route_after_judge(state: ArenaState) -> Literal["research", "clarification", "final_report"]:
    # The Judge node already applied the loop limits (and folded in the winner's claim check); here we only read
    # its decision.
    decision = (state.get("verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    if decision == "request_clarification":
        return "clarification"
    return "final_report"               # proceed or insufficient_evidence


def route_after_brief_validator(state: ArenaState) -> Literal["brief_writer", "clarification", "await_brief_review"]:
    # The validator already applied the revision cap and the loop limits; here we only read its verdict.
    verdict = (state.get("brief_validation") or {}).get("verdict")
    if verdict == "revise":
        return "brief_writer"
    if verdict == "clarify":
        return "clarification"
    return "await_brief_review"         # approve: the user reviews the validated brief


REVIEW_ROUTES = {"wording": "brief_writer", "requirements": "clarification", "research": "research", "proposal": "proposer"}


def route_after_brief_review(state: ArenaState) -> Literal["brief_writer", "clarification", "research", "proposer",
                                                          "await_brief_review", "planner"]:
    route = state.get("brief_review_route")
    if route == "approved":
        # Hard guard (not only the UI): the approval must match the brief in the state right now.
        return "planner" if brief_is_approved(state) else "await_brief_review"
    return REVIEW_ROUTES.get(route or "", "await_brief_review")


def route_after_plan_review(state: ArenaState) -> Literal["planner", "await_plan_review", "implementer"]:
    route = state.get("plan_review_route")
    if route == "approved":
        # Hard guard (not only the UI): both approvals must match what is in the state now.
        return "implementer" if plan_is_approved(state) else "await_plan_review"
    if route == "changes":
        return "planner"
    return "await_plan_review"


def _has_pending_task(state: ArenaState) -> bool:
    return any(t.get("status") == "pending" for t in state.get("implementation_tasks", []))


def route_after_implementer(state: ArenaState) -> Literal["implementer", "build_check", "completion"]:
    # The node decides every task's status (verify commands, attempts, blocking, budget); a pending task means
    # another attempt is due. The approvals are re-checked on every step.
    if not plan_is_approved(state):
        return "completion"
    return "implementer" if _has_pending_task(state) else "build_check"


def route_after_build_check(state: ArenaState) -> Literal["implementer", "code_review"]:
    # build_check adds a fix task (pending) when a fix round is left; otherwise the review (it skips a failed build).
    return "implementer" if _has_pending_task(state) and plan_is_approved(state) else "code_review"


def route_after_code_review(state: ArenaState) -> Literal["implementer", "preview"]:
    # code_review adds a fix task for high-severity findings when a review fix round is left.
    return "implementer" if _has_pending_task(state) and plan_is_approved(state) else "preview"


def route_after_preview(state: ArenaState) -> Literal["implementer", "e2e_check"]:
    # preview adds a fix task (pending) when the page rendered blank and a fix round is left (shared with build_check).
    return "implementer" if _has_pending_task(state) and plan_is_approved(state) else "e2e_check"


def route_after_e2e_check(state: ArenaState) -> Literal["implementer", "await_change_request"]:
    # e2e_check adds the E1 task (no browser tests yet) or a fix task (a test failed, an e2e fix round left).
    return "implementer" if _has_pending_task(state) and plan_is_approved(state) else "await_change_request"


def route_after_change_request(state: ArenaState) -> Literal["implementer", "brief_writer", "completion",
                                                             "await_change_request"]:
    route = state.get("change_route")
    if route == "change":
        return "implementer" if plan_is_approved(state) else "await_change_request"
    if route == "replan":
        return "brief_writer"                      # bigger change: brief → approval → plan extension → approval
    return "completion"


def guarded(route: Callable[[ArenaState], str] | str):
    """A routing function that ends the session (→ completion) whenever an error is recorded,
    and otherwise follows `route` (a function, or a fixed target name)."""
    def _route(state: ArenaState) -> str:
        if state.get("error"):
            return "completion"
        return route(state) if callable(route) else route
    return _route


# --- graph ----------------------------------------------------------------------------

def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """A checkpointer is required for interrupt()/resume: PostgresSaver (checkpointing.py) or InMemorySaver for demos."""
    builder = StateGraph(ArenaState)
    for name, fn in NODES.items():
        builder.add_node(name, wrap_node(name)(fn))
    builder.add_node("completion", completion_node)           # terminal, pure Python, not wrapped

    def connect(src: str, route, targets: list[str]) -> None:
        builder.add_conditional_edges(src, guarded(route), {t: t for t in targets} | {"completion": "completion"})

    builder.add_edge(START, "intake")
    connect("intake", "clarification", ["clarification"])
    connect("clarification", route_after_clarification, ["await_clarification", "research"])
    connect("await_clarification", "clarification", ["clarification"])          # re-evaluate after answers
    connect("research", "proposer", ["proposer"])
    connect("proposer", "critic", ["critic"])
    connect("critic", "judge", ["judge"])
    connect("judge", route_after_judge, ["research", "clarification", "final_report"])
    connect("final_report", "brief_writer", ["brief_writer"])
    connect("brief_writer", "brief_validator", ["brief_validator"])
    connect("brief_validator", route_after_brief_validator, ["brief_writer", "clarification", "await_brief_review"])
    connect("await_brief_review", "brief_review_router", ["brief_review_router"])
    connect("brief_review_router", route_after_brief_review,
            ["brief_writer", "clarification", "research", "proposer", "await_brief_review", "planner"])
    connect("planner", "await_plan_review", ["await_plan_review"])
    connect("await_plan_review", "plan_review_router", ["plan_review_router"])
    connect("plan_review_router", route_after_plan_review, ["planner", "await_plan_review", "implementer"])
    connect("implementer", route_after_implementer, ["implementer", "build_check"])
    connect("build_check", route_after_build_check, ["implementer", "code_review"])
    connect("code_review", route_after_code_review, ["implementer", "preview"])
    connect("preview", route_after_preview, ["implementer", "e2e_check"])
    connect("e2e_check", route_after_e2e_check, ["implementer", "await_change_request"])
    connect("await_change_request", "change_request_router", ["change_request_router"])
    connect("change_request_router", route_after_change_request,
            ["implementer", "brief_writer", "completion", "await_change_request"])
    builder.add_edge("completion", END)

    return builder.compile(checkpointer=checkpointer)
