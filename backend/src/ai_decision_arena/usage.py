"""Token and cost accounting for the builder's own model calls (spec §10.11, M11).

How it is measured:
- `llm._call_structured` records EVERY attempt it sends (self-correction retries and the fallback model included:
  each one is billed), from the response's `usage_metadata`. The Ask chat records each streamed round the same way.
- `nodes/node_wrapper.wrap_node` opens a `UsageMeter` around every node run and appends ONE entry to the state's
  `usage_log` when the node made calls ({node, at, seconds, calls, failed_calls, models, tokens, cost_usd}); the same
  entry goes to the `usage_events` table (best effort) for `/api/metrics` across sessions.
- The coding agent is NOT metered here: its cost is the Agent SDK's own `total_cost_usd` per task attempt, already in
  `implementation_log` / `implementation_cost_usd` (counting it twice would be easy to do by accident).

The meter lives in a ContextVar; the worker threads of a node (ContextThreadPoolExecutor) copy the context, so
parallel calls (critic, extractor, brief parts) land in the node's meter. The object is shared, hence the lock.
A call outside any meter (a script calling a node function directly) is simply not recorded.
"""

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from ai_decision_arena.pricing import Tokens, cost_usd, is_priced


class UsageMeter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.failed_calls = 0                   # attempts whose output was unusable (still billed)
        self.models: dict[str, int] = {}
        self.unpriced: set[str] = set()
        self.tokens = Tokens()
        self.cost_usd = 0.0

    def add(self, model: str, tokens: Tokens, ok: bool = True) -> None:
        with self._lock:
            self.calls += 1
            self.failed_calls += 0 if ok else 1
            self.models[model] = self.models.get(model, 0) + 1
            if not is_priced(model):
                self.unpriced.add(model)
            for field in ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h"):
                setattr(self.tokens, field, getattr(self.tokens, field) + getattr(tokens, field))
            self.cost_usd += cost_usd(model, tokens)

    def entry(self, node: str, started_at: str, seconds: float, **extra) -> dict:
        """The usage_log entry of one node run."""
        return {"node": node, "at": started_at, "seconds": round(seconds, 2), "calls": self.calls,
                "failed_calls": self.failed_calls, "models": dict(self.models), **self.tokens.as_dict(),
                "cost_usd": round(self.cost_usd, 6), "unpriced_models": sorted(self.unpriced), **extra}


_current: ContextVar[UsageMeter | None] = ContextVar("usage_meter", default=None)


@contextmanager
def metering():
    """Collect the usage of every call made inside this block (and its context-copying threads)."""
    meter = UsageMeter()
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)


def record(model: str, tokens: Tokens, ok: bool = True, meter: UsageMeter | None = None) -> None:
    """Add one billed call to `meter` (default: the active one; none active = not recorded)."""
    target = meter or _current.get()
    if target is not None:
        target.add(model, tokens, ok)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- reading: totals and attribution --------------------------------------------------------------------------

def llm_cost(state: dict) -> float:
    """USD of the builder's own model calls so far (usage_log; the coding agent is separate)."""
    return round(sum(float(e.get("cost_usd") or 0.0) for e in state.get("usage_log") or []), 6)


def llm_budget_left(state: dict, budget_usd: float) -> bool:
    return llm_cost(state) < budget_usd


def save_event(thread_id: str, entry: dict) -> None:
    """Store one usage entry in `usage_events` for /api/metrics (best effort: the checkpoint stays the truth)."""
    from ai_decision_arena.config import get_settings
    if not get_settings().persist_results or not thread_id:
        return
    try:
        from ai_decision_arena.db.repository import save_usage_event
        save_usage_event(thread_id, entry)
    except Exception:                    # noqa: BLE001 - metrics must never break a run
        pass


# --- per-session cost report (GET /api/decisions/{id}/usage) -------------------------------------------------

PHASES = {      # node -> the stage the builder UI shows
    "intake": "Clarification", "clarification": "Clarification",
    "research": "Research",
    "proposer": "Proposals", "critic": "Proposals", "judge": "Proposals",
    "final_report": "Proposals",
    "brief_writer": "Brief", "brief_validator": "Brief", "brief_review_router": "Brief",
    "planner": "Plan",
    "implementer": "Build", "code_review": "Build",
}


def _ts(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def session_cost(state: dict) -> dict:
    """What the session spent, from the checkpoint: the builder's model calls (usage_log, measured since M11) and
    the coding agent (implementation_log: the Agent SDK's cost per task attempt). Attribution to a change request =
    everything that ran between that request and the next reply at the change pause (its C task, fix tasks, or a
    replan's brief + plan + new tasks); before the first request = the first build."""
    usage_log = list(state.get("usage_log") or [])
    agent_log = list(state.get("implementation_log") or [])
    steps = [{"kind": "llm", "node": e["node"], "phase": PHASES.get(e["node"], "Other"), "at": e["at"],
              "cost_usd": float(e.get("cost_usd") or 0.0), "calls": e.get("calls", 0),
              "tokens": {k: e.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")},
              "seconds": e.get("seconds", 0.0), "models": e.get("models", {}), "error": e.get("error")}
             for e in usage_log]
    steps += [{"kind": "agent", "node": "implementer", "phase": "Build", "at": a.get("at", ""),
               "cost_usd": float(a.get("cost_usd") or 0.0), "task_id": a.get("task_id"), "attempt": a.get("attempt"),
               "ok": a.get("ok")} for a in agent_log]
    steps.sort(key=lambda s: _ts(s["at"]) or datetime.min.replace(tzinfo=timezone.utc))

    phases: dict[str, dict] = {}
    for s in steps:
        p = phases.setdefault(s["phase"], {"phase": s["phase"], "llm_usd": 0.0, "agent_usd": 0.0})
        p["llm_usd" if s["kind"] == "llm" else "agent_usd"] += s["cost_usd"]

    replies = [c for c in state.get("change_requests") or [] if _ts(c.get("at"))]
    windows = []
    for i, c in enumerate(replies):
        if c.get("action") == "finish":
            continue
        end = _ts(replies[i + 1]["at"]) if i + 1 < len(replies) else None
        windows.append((c, _ts(c["at"]), end))
    first_change = _ts(replies[0]["at"]) if replies else None
    initial = {"llm_usd": 0.0, "agent_usd": 0.0}
    changes = [{"round": c.get("round"), "action": c.get("action"), "request": c.get("request", ""), "at": c["at"],
                "llm_usd": 0.0, "agent_usd": 0.0, "tasks": []} for c, _, _ in windows]
    for s in steps:
        at = _ts(s["at"])
        key = "llm_usd" if s["kind"] == "llm" else "agent_usd"
        if at is None or first_change is None or at < first_change:
            initial[key] += s["cost_usd"]
            continue
        for change, (_, start, end) in zip(changes, windows):
            if start <= at and (end is None or at < end):
                change[key] += s["cost_usd"]
                if s.get("task_id") and s["task_id"] not in change["tasks"]:
                    change["tasks"].append(s["task_id"])
                break

    def rounded(d: dict) -> dict:
        out = {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}
        if "llm_usd" in out:
            out["total_usd"] = round(out["llm_usd"] + out["agent_usd"], 4)
        return out

    llm_usd = llm_cost(state)
    agent_usd = float(state.get("implementation_cost_usd") or 0.0)
    return {
        "total_usd": round(llm_usd + agent_usd, 4),
        "llm_usd": round(llm_usd, 4),
        "agent_usd": round(agent_usd, 4),
        # usage_log exists only for runs since M11: an older session's LLM spend before that was not measured
        "llm_measured_since": usage_log[0]["at"] if usage_log else None,
        "unpriced_models": sorted({m for e in usage_log for m in e.get("unpriced_models", [])}),
        "prompt_versions": state.get("prompt_versions") or {},
        "models_used": sorted({m for e in usage_log for m in e.get("models", {})} | (
            {(state.get("models_used") or {}).get("implementer")} - {None})),
        "phases": [rounded(p) for p in phases.values()],
        "first_build": rounded(initial),
        "changes": [rounded(c) for c in changes],
        "steps": [rounded(s) for s in steps],
    }
