"""The Health Decision Arena graph.

    START → intake → clarification ─┬─(need_clarification)─► await_clarification ─► clarification (loop)
                                    └─(enough info)────────► research → proposer → critic → judge
    judge ─┬─(request_more_research)──► research          (focused; bounded; never with red flags / over budget)
           ├─(request_clarification)──► clarification
           └─(proceed / insufficient_evidence)──► evidence_checker ─┬─(material gap, loop allowed)─► research
                                                                    └──────────────────────────────► final_report
    final_report → completion → END        (the report always shows the best plan of all three perspectives)
    Any node that raises → its error is stored (nodes/node_wrapper.py) → completion (status failed).

Every edge is "guarded": if the state carries an error, the graph goes straight to completion. Nodes are not
retried here: every LLM call already retries and falls back to a second model (llm.py).

Red flags never pause the graph: they are recorded, shown in the UI and the report, and change how the
Proposer / Judge behave (emergency-first plans, no loops).

Quick mode (patient chat, state["mode"] == "quick"): same nodes, but no loops (quick settings: max 1 debate round, 0 research retries). Unless
QUICK_DOUBLE_CHECK=true, the two double-check agents are skipped too, to keep onboarding near 30 seconds:
    research → proposer → judge → final_report → completion
"""

from typing import Callable, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ai_decision_arena.config import get_settings
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
}


# --- routing functions: read the state, return the NAME of the next step ------------

def route_after_clarification(state: ArenaState) -> Literal["await_clarification", "research"]:
    return "await_clarification" if state.get("need_clarification") else "research"


def skips_double_check(state: ArenaState) -> bool:
    """Quick sessions skip the Critic and the Evidence Checker unless QUICK_DOUBLE_CHECK=true."""
    return state.get("mode") == "quick" and not get_settings().quick_double_check


def route_after_proposer(state: ArenaState) -> Literal["critic", "judge"]:
    return "judge" if skips_double_check(state) else "critic"


def route_after_judge(state: ArenaState) -> Literal["research", "clarification", "evidence_checker", "final_report"]:
    # The Judge node already applied the loop limits; here we only read its decision.
    decision = (state.get("verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    if decision == "request_clarification":
        return "clarification"
    # proceed or insufficient_evidence
    return "final_report" if skips_double_check(state) else "evidence_checker"


def route_after_evidence_checker(state: ArenaState) -> Literal["research", "final_report"]:
    decision = (state.get("checker_verdict") or {}).get("decision")
    if decision == "request_more_research":
        return "research"
    return "final_report"


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
    connect("proposer", route_after_proposer, ["critic", "judge"])
    connect("critic", "judge", ["judge"])
    connect("judge", route_after_judge, ["research", "clarification", "evidence_checker", "final_report"])
    connect("evidence_checker", route_after_evidence_checker, ["research", "final_report"])
    connect("final_report", "completion", ["completion"])
    builder.add_edge("completion", END)

    return builder.compile(checkpointer=checkpointer)
