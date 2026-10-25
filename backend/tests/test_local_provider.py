"""LLM_PROVIDER=local (config._apply_local, llm, pricing): offline, no Ollama needed."""

import pytest

from ai_decision_arena import config, llm, pricing
from ai_decision_arena.config import Settings
from ai_decision_arena.pricing import Tokens


@pytest.fixture
def local(monkeypatch):
    settings = Settings(llm_provider="local", local_model="qwen-test", llm_timeout_seconds=90, local_time_multiplier=4)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    return settings


def test_every_role_uses_the_local_model(local):
    assert {local.anthropic_model, local.planner_model, local.chat_model, local.implementer_model} == {"qwen-test"}
    assert local.fallback_model == "" and local.is_local
    assert local.llm_timeout_seconds == 360


def test_separate_coder_model():
    s = Settings(llm_provider="local", local_model="a", local_coder_model="b")
    assert s.anthropic_model == "a" and s.implementer_model == "b"


def test_anthropic_mode_unchanged_and_needs_a_key(monkeypatch):
    s = Settings(llm_provider="anthropic", anthropic_api_key="k", anthropic_model="claude-sonnet-5-5")
    assert not s.is_local and s.fallback_model == "claude-haiku-5-5" and s.llm_timeout_seconds == 90
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        Settings(llm_provider="anthropic", anthropic_api_key=None)


def test_local_client_and_free_pricing(local):
    from langchain_ollama import ChatOllama

    client = llm.get_llm(500)
    assert isinstance(client, ChatOllama) and client.model == "qwen-test" and client.num_predict == 500
    assert pricing.is_priced("qwen-test") and pricing.cost_usd("qwen-test", Tokens(input=10_000, output=5_000)) == 0


def test_local_error_is_readable(local):
    import httpx

    assert "is the Ollama app" in llm.describe_llm_error(httpx.ConnectError("refused"))
