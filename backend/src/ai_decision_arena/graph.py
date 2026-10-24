"""The AI App Builder graph.

    START → intake → clarification ─┬─(need_clarification)─► await_clarification ─► clarification (loop, ≤ 3 rounds)
                                    └─(enough info)────────► research → proposer → critic → judge
    judge ─┬─(request_more_research)──► research          (focused; bounded by limits.py)
           ├─(request_clarification)──► clarification
           └─(proceed / insufficient_evidence)──► evidence_checker ─┬─(material gap, loop allowed)─► research
                                                                    └──────────────────────────────► final_report
    final_report → brief_writer → brief_validator ─┬─(revise, ≤ max_brief_revisions)──► brief_writer
                                                   ├─(clarify, loop allowed)──────────► clarification
                                                   └─(approve)────────────────────────► await_brief_review (pause)
    await_brief_review → brief_review_router ─┬─(approved)────► completion → END     (M6: planner)
                                              ├─(wording)─────► brief_writer
                                              ├─(requirements)► clarification
                                              ├─(research)────► research
                                              └─(proposal)────► proposer
    Any node that raises → its error is stored (nodes/node_wrapper.py) → completion (status failed).

Every edge is "guarded": if the state carries an error, the graph goes straight to completion. Nodes are not
retried here: every LLM call already retries and falls back to a second model (llm.py).

Risk flags never change routing: they are recorded and shown, and the Proposer / Judge take them into account.
Quick sessions run the SAME nodes with the quick settings (fewer searches, one proposal, no loops); nothing is skipped.
"""

from typing import Callable, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ai_decision_arena.brief import brief_is_approved
from ai_decision_arena.nodes.brief_review import await_brief_review_node, brief_review_router_node
from ai_decision_arena.nodes.brief_validator import brief_validator_node
from ai_decision_arena.nodes.brief_writer import brief_writer_node
from ai_decision_arena.nodes.clarification import await_clarification_node, clarification_node
from ai_decision_arena.nodes.critic import critic_node
from ai_decision_arena.nodes.evidence_checker import evidence_checker_node
from ai_decision_arena.nodes.final_report import completion_node, final_report_node
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
    "evidence_checker": evidence_checker_node,
    "final_report": final_report_node,
    "brief_writer": brief_writer_node,
    "brief_validator": brief_validator_node,
    "await_brief_review": await_brief_review_node,
    "brief_review_router": brief_review_router_node,
}


# --- routing functions: read the state, return the NAME of the next step ------------

def route_after_clarification(state: ArenaState) -> Literal["await_clarification", "research"]:
    return "await_clarification" if state.get("need_clarification") else "research"


def route_after_judge(state: ArenaState) -> Literal["research", "clarification", "evidence_checker"]:
    # The Judge node already applied the loop limits; here we only read its decision.
    decision = (state.get("verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    if decision == "request_clarification":
        return "clarification"
    return "evidence_checker"           # proceed or insufficient_evidence


def route_after_evidence_checker(state: ArenaState) -> Literal["research", "final_report"]:
    decision = (state.get("checker_verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    return "final_report"


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
                                                          "await_brief_review", "completion"]:
    route = state.get("brief_review_route")
    if route == "approved":
        # Hard guard (not only the UI): the approval must match the brief in the state right now.
        return "completion" if brief_is_approved(state) else "await_brief_review"     # M6: planner
    return REVIEW_ROUTES.get(route or "", "await_brief_review")


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
    connect("judge", route_after_judge, ["research", "clarification", "evidence_checker"])
    connect("evidence_checker", route_after_evidence_checker, ["research", "final_report"])
    connect("final_report", "brief_writer", ["brief_writer"])
    connect("brief_writer", "brief_validator", ["brief_validator"])
    connect("brief_validator", route_after_brief_validator, ["brief_writer", "clarification", "await_brief_review"])
    connect("await_brief_review", "brief_review_router", ["brief_review_router"])
    connect("brief_review_router", route_after_brief_review,
            ["brief_writer", "clarification", "research", "proposer", "await_brief_review"])
    builder.add_edge("completion", END)

    return builder.compile(checkpointer=checkpointer)
