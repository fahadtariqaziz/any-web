"""M11 part 3: the prompt registry is complete and locked, and sessions record the versions they used."""

from ai_decision_arena import prompts
from ai_decision_arena.graph import build_graph
from ai_decision_arena.prompting import BUILDER_RULES


def test_every_prompt_is_locked_at_its_version():
    problems = prompts.lock_problems()
    assert not problems, "\n".join(problems)


def test_every_model_calling_node_has_a_registered_prompt():
    # final_report makes no call since the speed work (its narrative is written by brief_writer, in parallel); the
    # claim check's prompt (id evidence_checker) is sent by the critic (every proposal) and the judge (fallback).
    llm_nodes = {"intake", "clarification", "research", "proposer", "critic", "judge",
                 "brief_writer", "brief_validator", "brief_review_router", "planner", "implementer"}
    assert llm_nodes <= set(build_graph().nodes)
    for node in llm_nodes | {"ask"}:
        assert set(prompts.versions_for(node)) - {"builder_rules"}, f"no prompt registered for {node}"


def test_shared_rules_are_hashed_once(monkeypatch):
    before = {pid: s.text_hash() for pid, s in prompts.REGISTRY.items()}
    import ai_decision_arena.prompting as prompting
    from ai_decision_arena.nodes import intake
    monkeypatch.setattr(prompting, "BUILDER_RULES", BUILDER_RULES + "\n- a new shared rule")
    monkeypatch.setattr(intake, "SYSTEM_PROMPT", intake.SYSTEM_PROMPT.replace(BUILDER_RULES, prompting.BUILDER_RULES))
    after = {pid: s.text_hash() for pid, s in prompts.REGISTRY.items()}
    # (only intake was rebuilt with the new rules here; at import time every agent would be)
    assert before["builder_rules"] != after["builder_rules"] and before["intake"] == after["intake"]


def test_a_changed_prompt_without_a_version_bump_is_reported(monkeypatch):
    from ai_decision_arena.nodes import judge
    monkeypatch.setattr(judge, "SYSTEM_PROMPT", judge.SYSTEM_PROMPT + "\nBe brief.")
    assert any(p.startswith("judge: text changed but version is still 1") for p in prompts.lock_problems())


def test_a_session_records_the_prompt_versions_it_used(graph, fake_llm, fake_search):
    from tests.conftest import finish_session
    config = {"configurable": {"thread_id": "t-prompts"}}
    graph.invoke({"question": "A simple calculator web app", "user_context": "", "mode": "full"}, config)
    state = finish_session(graph, config)
    used = state["prompt_versions"]
    assert {"builder_rules", "intake", "clarification", "research_planner", "extractor", "proposer", "critic", "judge",
            "brief_writer", "brief_validator", "planner"} <= set(used)
    assert all(v == prompts.REGISTRY[p].version for p, v in used.items())
    assert state["metrics"]["prompt_versions"] == used
    entry = next(e for e in state["usage_log"] if e["node"] == "planner")
    assert entry["prompts"]["planner"] == prompts.REGISTRY["planner"].version


def test_offline_evals_pass():
    """Every eval case's offline checks hold (scripts/run_evals.py, test fakes, a few seconds)."""
    import subprocess
    import sys
    from pathlib import Path
    out = subprocess.run([sys.executable, "scripts/run_evals.py"], cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-2000:]
    assert "EVALS (offline):" in out.stdout


def test_eval_checks():
    from ai_decision_arena.evals import Request, evaluate
    reqs = [Request("PlanExtension", "s", "<built_tasks> x"), Request("PlanExtension", "s", "y")]
    assert evaluate({"on": "request", "check": "schema", "equals": "PlanExtension"}, reqs, None, None) is None
    assert evaluate({"on": "request", "check": "contains", "text": "<built_tasks>"}, reqs, None, None) is None
    assert evaluate({"on": "request", "check": "contains", "text": "<built_tasks>", "all_calls": True}, reqs, None, None)
    assert evaluate({"on": "request", "check": "calls", "schema": "FeedbackRouting", "equals": 0}, reqs, None, None) is None
    out = {"q": ["Who uses it?", "Budget, launch date, or assets?"], "a": {"b": "web_app"}}
    assert evaluate({"on": "output", "path": "a.b", "check": "in", "values": ["web_app"]}, [], out, None) is None
    assert evaluate({"on": "output", "path": "q", "check": "each_max_count", "pattern": ",[^,?]*\\bor\\b", "max": 0}, [], out, None)
    assert evaluate({"on": "output", "path": "q", "check": "len_between", "min": 1, "max": 2}, [], out, None) is None
    assert evaluate({"on": "raises", "check": "error_type", "equals": "ValueError"}, [], None, ValueError("x")) is None
    assert evaluate({"on": "output", "path": "a", "check": "equals", "value": 1}, [], None, KeyError("k"))


def test_llm_judge_check(monkeypatch):
    from ai_decision_arena import evals
    monkeypatch.setattr(evals, "judge", lambda q, item: evals.JudgeVerdict(reason="r", answer="budget" in item))
    check = {"on": "output", "path": "q", "check": "llm_judge", "each": True, "expect": False, "question": "packed?"}
    assert evals.evaluate(check, [], {"q": ["Who uses it?"]}, None) is None
    assert "judged wrong" in evals.evaluate(check, [], {"q": ["Who uses it?", "Tech, hosting, budget or timeline?"]}, None)
