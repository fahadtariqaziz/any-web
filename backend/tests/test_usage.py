"""M11 cost accounting: prices, token splitting, the meter (threads, retries), node entries, the LLM budget,
attribution per phase / change, and the /usage endpoint."""

import pytest
from langchain_core.messages import AIMessage
from langsmith.utils import ContextThreadPoolExecutor

from ai_decision_arena import llm, usage
from ai_decision_arena.limits import loops_allowed
from ai_decision_arena.nodes.node_wrapper import wrap_node
from ai_decision_arena.pricing import Tokens, cost_usd, tokens_from_anthropic, tokens_from_langchain
from ai_decision_arena.schemas import IntakeResult

from tests.test_api import client, finish_via_api, wait_until_not_running  # noqa: F401 - fixture reuse


# --- prices and token splitting -------------------------------------------------------------------------------

def test_langchain_input_tokens_include_cache_tokens_which_are_split_out():
    tokens = tokens_from_langchain({"input_tokens": 1500, "output_tokens": 300,
                                    "input_token_details": {"cache_read": 1000, "cache_creation": 200}})
    assert (tokens.input, tokens.cache_read, tokens.cache_write_5m, tokens.output) == (300, 1000, 200, 300)
    ttl = tokens_from_langchain({"input_tokens": 600, "output_tokens": 0, "input_token_details": {
        "cache_read": 0, "cache_creation": 0, "ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 400}})
    assert (ttl.input, ttl.cache_write_5m, ttl.cache_write_1h) == (100, 100, 400)
    assert tokens_from_langchain(None) == Tokens()


def test_agent_sdk_usage_excludes_cache_tokens_already():
    tokens = tokens_from_anthropic({"input_tokens": 50, "output_tokens": 10, "cache_read_input_tokens": 900,
                                    "cache_creation_input_tokens": 300})
    assert (tokens.input, tokens.cache_read, tokens.cache_write_5m) == (50, 900, 300)


def test_cost_per_model_and_tier():
    one_m = Tokens(input=1_000_000, output=1_000_000)
    assert cost_usd("claude-sonnet-5-5", one_m) == pytest.approx(12.0)
    assert cost_usd("claude-opus-5-5", one_m) == pytest.approx(24.0)
    assert cost_usd("claude-opus-5-5", Tokens(cache_read=1_000_000)) == pytest.approx(0.20)
    assert cost_usd("claude-sonnet-5-5", Tokens(cache_write_5m=1_000_000)) == pytest.approx(2.5)
    assert cost_usd("claude-haiku-5-5", Tokens(input=50_000, output=1_000)) == pytest.approx(0.0055)
    # Haiku 5.5 prompts over 100K tokens use the higher price
    assert cost_usd("claude-haiku-5-5", Tokens(input=200_000)) == pytest.approx(0.10)
    assert cost_usd("some-future-model", one_m) == 0.0


# --- the meter ------------------------------------------------------------------------------------------------

def test_meter_collects_calls_from_context_copying_threads_and_flags_unpriced_models():
    with usage.metering() as meter:
        with ContextThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: usage.record("claude-sonnet-5-5", Tokens(input=1000, output=100)), range(8)))
        usage.record("mystery-model", Tokens(input=10), ok=False)
    assert meter.calls == 9 and meter.failed_calls == 1
    assert meter.models == {"claude-sonnet-5-5": 8, "mystery-model": 1} and meter.unpriced == {"mystery-model"}
    assert meter.cost_usd == pytest.approx(8 * (1000 * 2 + 100 * 10) / 1_000_000)
    usage.record("claude-sonnet-5-5", Tokens(input=1))       # outside a meter: ignored, no error


class _StructuredStub:
    """with_structured_output(...).invoke() returning an invalid answer first, then a valid one."""

    def __init__(self, results):
        self.results = list(results)

    def with_structured_output(self, *args, **kwargs):
        return self

    def invoke(self, messages, config=None):
        return self.results.pop(0)


def _raw(input_tokens: int, output_tokens: int, stop: str = "end_turn") -> AIMessage:
    return AIMessage(content="{}", response_metadata={"stop_reason": stop},
                     usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens,
                                     "total_tokens": input_tokens + output_tokens})


def test_every_attempt_of_a_structured_call_is_billed(monkeypatch):
    good = IntakeResult.model_construct()
    stub = _StructuredStub([{"parsed": None, "raw": _raw(1000, 4000, "max_tokens"), "parsing_error": None},
                            {"parsed": good, "raw": _raw(1200, 500), "parsing_error": None}])
    monkeypatch.setattr(llm, "get_llm", lambda *a, **k: stub)
    with usage.metering() as meter:
        assert llm.call_structured(IntakeResult, "system", "user") is good
    assert meter.calls == 2 and meter.failed_calls == 1
    assert meter.tokens.input == 2200 and meter.tokens.output == 4500


# --- node entries and the budget ------------------------------------------------------------------------------

def test_wrapped_node_appends_one_usage_entry_also_when_it_fails():
    @wrap_node("judge")
    def judge(state):
        usage.record("claude-sonnet-5-5", Tokens(input=1000, output=100))
        usage.record("claude-sonnet-5-5", Tokens(input=1000, output=100))
        return {"status": "debating"}

    @wrap_node("critic")
    def critic(state):
        usage.record("claude-sonnet-5-5", Tokens(input=500))
        raise RuntimeError("boom")

    @wrap_node("await_brief_review")
    def pause(state):
        return {}

    update = judge({"usage_log": [{"node": "intake", "cost_usd": 0.01}]})
    assert [e["node"] for e in update["usage_log"]] == ["intake", "judge"]
    assert update["usage_log"][-1]["calls"] == 2 and update["usage_log"][-1]["cost_usd"] == pytest.approx(0.006)
    failed = critic({})
    assert failed["status"] == "failed" and failed["usage_log"][0]["error"] == "unknown"
    assert "usage_log" not in pause({})                      # no calls → no entry


@pytest.mark.usefixtures("auto_loops")
def test_llm_budget_stops_automatic_loops(monkeypatch):
    state = {"usage_log": [{"cost_usd": 3.0}, {"cost_usd": 2.5}], "debate_round": 1}
    can_debate, can_research, can_clarify, blocked = loops_allowed(state)
    assert not (can_debate or can_research or can_clarify)
    assert any("LLM budget" in b for b in blocked)
    assert loops_allowed({"usage_log": [{"cost_usd": 0.5}], "debate_round": 1})[0]


# --- attribution ----------------------------------------------------------------------------------------------

def test_cost_is_attributed_to_phases_first_build_and_each_change():
    state = {
        "usage_log": [
            {"node": "research", "at": "2026-10-25T10:00:00+00:00", "cost_usd": 0.30, "calls": 4},
            {"node": "planner", "at": "2026-10-25T10:05:00+00:00", "cost_usd": 0.50, "calls": 1},
            {"node": "brief_writer", "at": "2026-10-25T11:01:00+00:00", "cost_usd": 0.20, "calls": 3},   # replan
            {"node": "planner", "at": "2026-10-25T11:02:00+00:00", "cost_usd": 0.40, "calls": 1},
        ],
        "implementation_log": [
            {"task_id": "T1", "attempt": 1, "ok": True, "cost_usd": 0.10, "at": "2026-10-25T10:10:00+00:00"},
            {"task_id": "C1", "attempt": 1, "ok": True, "cost_usd": 0.05, "at": "2026-10-25T10:31:00+00:00"},
            {"task_id": "T2", "attempt": 1, "ok": True, "cost_usd": 0.25, "at": "2026-10-25T11:05:00+00:00"},
        ],
        "implementation_cost_usd": 0.40,
        "change_requests": [
            {"round": 1, "action": "change", "request": "percent key", "at": "2026-10-25T10:30:00+00:00"},
            {"round": 2, "action": "finish", "request": "", "at": "2026-10-25T10:40:00+00:00"},
            {"round": 3, "action": "replan", "request": "scientific", "at": "2026-10-25T11:00:00+00:00", "reopened": True},
        ],
    }
    report = usage.session_cost(state)
    assert report["llm_usd"] == pytest.approx(1.40) and report["agent_usd"] == pytest.approx(0.40)
    assert report["total_usd"] == pytest.approx(1.80)
    assert report["first_build"] == {"llm_usd": 0.8, "agent_usd": 0.1, "total_usd": 0.9}
    change, replan = report["changes"]
    assert (change["action"], change["agent_usd"], change["llm_usd"], change["tasks"]) == ("change", 0.05, 0.0, ["C1"])
    assert (replan["llm_usd"], replan["agent_usd"], replan["tasks"]) == (0.6, 0.25, ["T2"])
    phases = {p["phase"]: p for p in report["phases"]}
    assert phases["Plan"]["llm_usd"] == pytest.approx(0.9) and phases["Build"]["agent_usd"] == pytest.approx(0.4)
    assert report["llm_measured_since"] == "2026-10-25T10:00:00+00:00"


def test_a_session_from_before_m11_reports_agent_cost_only():
    report = usage.session_cost({"implementation_log": [{"task_id": "T1", "cost_usd": 0.2, "at": "2026-10-24T09:00:00+00:00"}],
                                 "implementation_cost_usd": 0.2})
    assert report["llm_measured_since"] is None and report["llm_usd"] == 0 and report["total_usd"] == 0.2


# --- end to end over the API (fake LLM: $0.004 per call; fake agent: $0.01 per attempt) ------------------------

def test_usage_endpoint_after_a_build_and_a_change(client):  # noqa: F811
    thread_id = finish_via_api(client, "A simple calculator web app")
    client.post(f"/api/decisions/{thread_id}/resume",
                json={"type": "reopen", "action": "change", "request": "Add a percent key: 430 - 20% = 344."})
    wait_until_not_running(client, thread_id)
    report = client.get(f"/api/decisions/{thread_id}/usage").json()
    nodes = {s["node"] for s in report["steps"] if s["kind"] == "llm"}
    assert {"intake", "clarification", "research", "proposer", "critic", "judge", "brief_writer", "planner"} <= nodes
    assert report["llm_usd"] > 0 and report["agent_usd"] == pytest.approx(0.01 * sum(
        s["kind"] == "agent" for s in report["steps"]))
    assert report["total_usd"] == pytest.approx(report["llm_usd"] + report["agent_usd"], abs=1e-3)
    assert report["llm_budget_usd"] == 5.0 and report["ask_usd"] is None          # PERSIST_RESULTS=false in tests
    assert "C1" in report["changes"][-1]["tasks"] and report["changes"][-1]["agent_usd"] >= 0.01
    assert {p["phase"] for p in report["phases"]} >= {"Clarification", "Research", "Proposals", "Brief", "Plan", "Build"}
