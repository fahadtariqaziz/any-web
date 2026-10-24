"""The graph's shape and its routing functions (pure Python, no LLM)."""

from ai_decision_arena import graph as G

EXPECTED_NODES = {"intake", "clarification", "await_clarification", "research", "proposer", "critic", "judge",
                  "evidence_checker", "final_report", "completion"}


def test_graph_compiles_with_expected_nodes(graph):
    drawn = graph.get_graph()
    nodes = {n for n in drawn.nodes if not n.startswith("__")}
    assert nodes == EXPECTED_NODES
    assert any(e.source == "__start__" and e.target == "intake" for e in drawn.edges)
    assert any(e.source == "completion" and e.target == "__end__" for e in drawn.edges)


def test_every_node_can_fail_to_completion(graph):
    """Every wrapped node has a guarded edge to completion (status failed path)."""
    drawn = graph.get_graph()
    sources = {e.source for e in drawn.edges if e.target == "completion"}
    assert sources >= EXPECTED_NODES - {"completion"}


def test_proposer_always_goes_to_the_critic(graph):
    """Quick sessions no longer skip the Critic or the Evidence Checker (M3 decision)."""
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert ("proposer", "critic") in edges
    assert ("proposer", "judge") not in edges
    assert ("judge", "final_report") not in edges


def test_route_after_clarification():
    assert G.route_after_clarification({"need_clarification": True}) == "await_clarification"
    assert G.route_after_clarification({"need_clarification": False}) == "research"
    assert G.route_after_clarification({}) == "research"


def test_route_after_judge_reads_the_decision_only():
    assert G.route_after_judge({"verdict": {"decision": "request_more_research"}}) == "research"
    assert G.route_after_judge({"verdict": {"decision": "request_clarification"}}) == "clarification"
    assert G.route_after_judge({"verdict": {"decision": "proceed"}}) == "evidence_checker"
    assert G.route_after_judge({"verdict": {"decision": "insufficient_evidence"}}) == "evidence_checker"
    assert G.route_after_judge({"mode": "quick", "verdict": {"decision": "proceed"}}) == "evidence_checker"
    assert G.route_after_judge({}) == "evidence_checker"


def test_route_after_evidence_checker():
    assert G.route_after_evidence_checker({"checker_verdict": {"decision": "request_more_research"}}) == "research"
    assert G.route_after_evidence_checker({"checker_verdict": {"decision": "proceed"}}) == "final_report"
    assert G.route_after_evidence_checker({}) == "final_report"


def test_guarded_route_goes_to_completion_on_error():
    route = G.guarded(G.route_after_judge)
    assert route({"error": {"node": "judge"}, "verdict": {"decision": "proceed"}}) == "completion"
    assert route({"verdict": {"decision": "proceed"}}) == "evidence_checker"
    fixed = G.guarded("proposer")
    assert fixed({}) == "proposer"
    assert fixed({"error": {"node": "research"}}) == "completion"
