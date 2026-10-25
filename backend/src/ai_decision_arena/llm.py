"""Shared model access for every agent: Claude, or a local Ollama model when LLM_PROVIDER=local (config.py).

What call_structured() does when something goes wrong, in this order:
1. API errors (rate limit, timeout, 5xx): the Anthropic SDK retries them itself
   with exponential backoff, up to `llm_max_retries` times (ChatAnthropic.max_retries).
2. Invalid structured output (fails Pydantic validation): call_structured() shows
   Claude the validation error and asks again, up to `llm_max_retries` times.
   If the output was cut off at max_tokens, it asks for a shorter answer instead
   (without re-sending the truncated text).
3. Model fallback: if 1 or 2 is exhausted, the SAME call is repeated once on settings.fallback_model
   (a different model is often up when the main one is overloaded, or gets the schema right).
4. If the fallback fails too: LLMUnavailableError, whose message is the API error of each model.
   The node wrapper (nodes/node_wrapper.py) records it and the session ends as "failed",
   showing that message to the user.

Every attempt that got a response is metered (usage.record: tokens + USD, also the invalid and truncated ones,
which are billed too); the node wrapper turns the node's meter into a `usage_log` entry.
"""

import threading
from contextlib import nullcontext
from functools import lru_cache
from typing import TypeVar

import anthropic
import httpx
import ollama
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.config import get_config
from pydantic import BaseModel

from ai_decision_arena.config import get_settings
from ai_decision_arena.pricing import tokens_from_langchain
from ai_decision_arena.progress import report
from ai_decision_arena.usage import record

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(Exception):
    """Claude's output still failed validation after all retries."""

    def __init__(self, schema_name: str, attempts: int, last_error: str):
        self.schema_name = schema_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"{schema_name}: invalid output after {attempts} attempt(s): {last_error}")


class LLMUnavailableError(Exception):
    """The main model AND the fallback model failed. The message is meant for the user: one line per model."""


# Failures worth a second try on another model. Anything else (e.g. a bug in our code) is raised as it is.
# (Local: Ollama's own errors and connection / timeout errors; there is no fallback model, but they become
# LLMUnavailableError with a readable message the same way.)
FALLBACK_ERRORS = (anthropic.APIError, ollama.ResponseError, httpx.HTTPError, ConnectionError, LLMOutputError)


def describe_llm_error(exc: Exception) -> str:
    """The API's own error in one readable line, e.g. "529 overloaded_error: Overloaded"."""
    if isinstance(exc, anthropic.APIStatusError):
        body = exc.body.get("error", {}) if isinstance(exc.body, dict) else {}
        return f"{exc.status_code} {body.get('type', 'api_error')}: {body.get('message', exc.message)}"
    if isinstance(exc, anthropic.APITimeoutError):
        return "timeout: no answer from the Claude API in time"
    if isinstance(exc, anthropic.APIConnectionError):
        return f"connection error: {exc.message}"
    if isinstance(exc, ollama.ResponseError):
        return f"ollama {exc.status_code}: {exc.error}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout: no answer from the local model in time"
    if isinstance(exc, (httpx.ConnectError, ConnectionError)):
        return f"cannot reach Ollama at {get_settings().local_base_url} (is the Ollama app / `ollama serve` running?)"
    return f"{type(exc).__name__}: {exc}"



def get_llm(max_tokens: int | None = None, model: str | None = None, effort: str | None = None,
            timeout: float | None = None) -> BaseChatModel:
    """The chat model client; `model` overrides settings.anthropic_model,
    `effort` sets output_config.effort (langchain merges it with the structured-output format; ignored locally),
    `timeout` the per-request timeout in seconds."""
    settings = get_settings()
    if settings.is_local:
        return _local_client(model or settings.anthropic_model, max_tokens or settings.llm_max_tokens,
                             timeout or settings.llm_timeout_seconds)
    return _client(model or settings.anthropic_model, max_tokens or settings.llm_max_tokens,
                   timeout or settings.llm_timeout_seconds, settings.llm_max_retries, effort)


@lru_cache
def _client(model: str, max_tokens: int, timeout: float, max_retries: int, effort: str | None = None) -> ChatAnthropic:
    """One ChatAnthropic client per combination, reused across calls."""
    return ChatAnthropic(
        model=model,
        api_key=get_settings().anthropic_api_key,  # SecretStr is accepted directly
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,                   # SDK backoff for transient API errors
        output_config={"effort": effort} if effort else None,
    )


@lru_cache
def _local_slots() -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(get_settings().local_max_parallel)


def model_slot():
    """Held around one local model call (LOCAL_MAX_PARALLEL at a time), so a call queued behind its siblings does not
    spend its timeout waiting inside Ollama. No-op for Claude."""
    return _local_slots() if get_settings().is_local else nullcontext()


@lru_cache
def _local_client(model: str, max_tokens: int, timeout: float) -> BaseChatModel:
    """One ChatOllama client per combination. Structured output uses Ollama's `format` (JSON schema, enforced while
    generating), so even small models return valid JSON. No num_ctx here: the model's own (verify_local.py builds a
    32K one) keeps ONE copy loaded for the graph, the chat and the coding agent."""
    from langchain_ollama import ChatOllama

    settings = get_settings()
    return ChatOllama(model=model, base_url=settings.local_base_url, num_predict=max_tokens,
                      reasoning=settings.local_think, client_kwargs={"timeout": timeout})


# --- model availability (never assume a model exists) --------------------------------------------------

@lru_cache
def available_models() -> frozenset[str] | None:
    """Model ids this API key can use (GET /v1/models; locally: Ollama's installed models, with and without the
    ":latest" tag), or None if the list could not be read. Cached per process."""
    try:
        if get_settings().is_local:
            tags = httpx.get(f"{get_settings().local_base_url}/api/tags", timeout=5).json()["models"]
            return frozenset(n for m in tags for n in (m["name"], m["name"].removesuffix(":latest")))
        client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key.get_secret_value(), timeout=15)
        return frozenset(m.id for m in client.models.list())
    except Exception:                 # network / auth problems: the caller decides
        return None


def resolve_model(wanted: str) -> tuple[str, str]:
    """(model to use, note). `wanted` if the API lists it; otherwise the session's default model with a warning.
    If the list cannot be read, `wanted` is kept (the call itself then fails over to the fallback chain)."""
    ids = available_models()
    default = get_settings().anthropic_model
    if ids is None:
        return wanted, f"model list unavailable; using {wanted} unchecked (fallback: {default})"
    if wanted in ids:
        return wanted, ""
    return default, f"{wanted} is not available to this API key; using {default} instead"


def call_structured(
    schema: type[T],
    system_prompt: str,
    user_content: str,
    *,
    max_tokens: int | None = None,
    run_name: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    timeout: float | None = None,
) -> T:
    """Ask Claude to fill `schema` and return a validated instance of it.

    Tries the main model, then once the fallback model (see the module docstring). `model` replaces the main model
    (e.g. the planner's Opus; its fallback is then the session's default model); `effort` / `timeout` apply to the
    main model only. Without `effort`, the graph node's entry in settings.node_effort is used (if any).
    Raises LLMUnavailableError if both fail.
    """
    settings = get_settings()
    name = run_name or schema.__name__
    if effort is None:
        effort = settings.node_effort.get(_current_node())
    if model:
        models = [model] + ([settings.anthropic_model] if settings.anthropic_model != model else [settings.fallback_model])
    else:
        models = [settings.anthropic_model, settings.fallback_model]
    models = list(dict.fromkeys(m for m in models if m))     # no empty fallback, no model twice (local: just one)

    failures = []
    for i, model_id in enumerate(models):
        try:
            return _call_structured(schema, system_prompt, user_content, model=model_id, max_tokens=max_tokens,
                                    run_name=name if i == 0 else f"{name}_fallback",
                                    effort=effort if i == 0 else None, timeout=timeout)
        except FALLBACK_ERRORS as exc:
            failures.append(f"{model_id}: {describe_llm_error(exc)}")
            if i + 1 < len(models):
                report(_current_node(), f"{name}: {model_id} failed ({describe_llm_error(exc)[:120]}); trying {models[i + 1]}")
    source = "The local model (Ollama) failed. " if settings.is_local else "The Claude API failed. "
    raise LLMUnavailableError(source + " | ".join(failures))


def _current_node() -> str:
    """The graph node this call runs in (LangGraph puts it in the run config), so progress lines group right."""
    try:
        return get_config().get("metadata", {}).get("langgraph_node", "llm")
    except RuntimeError:          # called outside a graph run (scripts)
        return "llm"


def _call_structured(
    schema: type[T],
    system_prompt: str,
    user_content: str,
    *,
    model: str,
    max_tokens: int | None,
    run_name: str,
    effort: str | None = None,
    timeout: float | None = None,
) -> T:
    """One model: SDK retries + self-correction. Raises an anthropic.APIError or LLMOutputError."""
    settings = get_settings()
    structured_llm = get_llm(max_tokens, model=model, effort=effort, timeout=timeout).with_structured_output(
        schema,
        method="json_schema",   # Anthropic native structured outputs / Ollama `format`
        include_raw=True,       # return errors instead of raising, so we can retry
    )
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
    attempts = settings.llm_max_retries + 1
    last_error = ""

    for attempt in range(1, attempts + 1):
        with model_slot():
            result = structured_llm.invoke(
                messages,
                config={"run_name": run_name, "metadata": {"attempt": attempt, "model": model}},
            )
        raw = result["raw"]
        record(model, tokens_from_langchain(getattr(raw, "usage_metadata", None)), ok=result["parsed"] is not None)
        if result["parsed"] is not None:
            return result["parsed"]

        if (raw.response_metadata.get("stop_reason") == "max_tokens"           # Claude
                or raw.response_metadata.get("done_reason") == "length"):      # Ollama
            # Output was cut off. Re-sending the truncated text wastes tokens: just ask for less.
            last_error = "output truncated at max_tokens"
            messages = messages + [HumanMessage(content=(
                "Your previous answer was cut off because it was too long. "
                f"Return the complete {schema.__name__} again, much more concisely: "
                "shorter texts, fewer items, only what matters most."
            ))]
            continue

        # Validation failed: show Claude its own answer plus the exact error, then retry.
        last_error = str(result["parsing_error"])[:1000]
        messages = messages + [
            raw,
            HumanMessage(content=(
                f"Your previous output was invalid:\n{last_error}\n\n"
                f"Return a corrected {schema.__name__} that satisfies every constraint."
            )),
        ]

    raise LLMOutputError(schema.__name__, attempts, last_error)
