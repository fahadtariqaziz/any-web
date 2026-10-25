"""Local-model check (LLM_PROVIDER=local): set up the Ollama model, then run the builder's real code paths on it.
Free (no Anthropic call, no Tavily search); slow: ~5-15 minutes on an 8 GB M2. Ollama must be running.

Run from the backend/ folder (works whatever LLM_PROVIDER says in .env: this script forces local mode):
    uv run python scripts/verify_local.py [--skip-agent]

0. Setup: Ollama answers; LOCAL_BASE_MODEL is pulled (if not: run `ollama pull <it>` and re-run); LOCAL_MODEL is
   created from it with LOCAL_CONTEXT_TOKENS of context if missing (Ollama's default context is too small for the
   coding agent's prompt).
1. Settings: every role (graph, planner, chat, coding agent) resolves to the local model; no fallback; timeouts
   multiplied; no Anthropic key needed.
2. Graph nodes: intake + clarification wrapped like in the graph → structured output parsed, tokens counted, $0,
   the model is not reported as unpriced.
3. Ask-style tool loop: one streamed chat reply through get_llm (ChatOllama) without the prompt-cache blocks.
4. Coding agent: the real Claude Agent SDK / Claude Code CLI on Ollama's /v1/messages writes a file in a throwaway
   project, runs one sandbox command, a read outside the project is refused; cost 0.
"""

import argparse
import os
import shutil
import sys
import time
import uuid

os.environ["LLM_PROVIDER"] = "local"            # before the settings are read
os.environ.setdefault("PERSIST_RESULTS", "false")

import httpx  # noqa: E402

from ai_decision_arena.config import get_settings  # noqa: E402

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


def finish() -> None:
    print("\nLOCAL VERIFY: " + ("PASS" if not failures else f"FAIL ({len(failures)}): " + " | ".join(failures)))
    sys.exit(1 if failures else 0)


parser = argparse.ArgumentParser()
parser.add_argument("--skip-agent", action="store_true", help="skip step 4 (the slowest)")
args = parser.parse_args()
settings = get_settings()
base = settings.local_base_url

print(f"0. setup: Ollama at {base}, model {settings.local_model} (from {settings.local_base_model}, "
      f"{settings.local_context_tokens} context)")
try:
    version = httpx.get(f"{base}/api/version", timeout=5).json()["version"]
    check(True, f"Ollama {version} answers")
except Exception as exc:                                                  # noqa: BLE001
    check(False, f"Ollama not reachable ({exc}): open the Ollama app or run `ollama serve`")
    finish()
names = {m["name"].removesuffix(":latest") for m in httpx.get(f"{base}/api/tags", timeout=10).json()["models"]}
if settings.local_model not in names:
    if settings.local_base_model not in names:
        check(False, f"{settings.local_base_model} is not pulled: run `ollama pull {settings.local_base_model}`")
        finish()
    r = httpx.post(f"{base}/api/create", timeout=120, json={
        "model": settings.local_model, "from": settings.local_base_model, "stream": False,
        "parameters": {"num_ctx": settings.local_context_tokens}})
    check(r.status_code == 200, f"created {settings.local_model} ({r.status_code} {r.text[:120]})")
else:
    check(True, f"{settings.local_model} is installed")

print("\n1. settings in local mode")
from ai_decision_arena.llm import get_llm, resolve_model  # noqa: E402

roles = {"graph": settings.anthropic_model, "planner": settings.planner_model, "chat": settings.chat_model,
         "implementer": settings.implementer_model}
print("  " + ", ".join(f"{k}={v}" for k, v in roles.items()))
check(set(roles.values()) == {settings.local_coder_model or settings.local_model} | {settings.local_model},
      "every role uses the local model")
check(settings.fallback_model == "", "no fallback model")
check(resolve_model(settings.planner_model) == (settings.planner_model, ""), "resolve_model finds it in Ollama's list")
print(f"  timeouts: llm {settings.llm_timeout_seconds:.0f}s · planner {settings.planner_timeout_seconds:.0f}s · "
      f"agent task {settings.implementer_task_timeout_seconds:.0f}s · session {settings.session_time_budget_seconds:.0f}s")

print("\n2. graph nodes (wrapped like in the graph)")
from ai_decision_arena.nodes.clarification import clarification_node  # noqa: E402
from ai_decision_arena.nodes.intake import intake_node  # noqa: E402
from ai_decision_arena.nodes.node_wrapper import wrap_node  # noqa: E402

state = {"thread_id": f"verify-local-{uuid.uuid4().hex[:8]}", "question": "A simple habit tracker web app",
         "user_context": "", "mode": "full"}
for name, node in (("intake", intake_node), ("clarification", clarification_node)):
    t0 = time.time()
    state.update(wrap_node(name)(node)(state))
    print(f"  {name}: {time.time() - t0:.0f} s")
for e in state.get("usage_log") or []:
    print(f"  {e['node']}: {e['calls']} call(s), in {e['input_tokens']} / out {e['output_tokens']} tokens, "
          f"${e['cost_usd']:.4f}, models {e['models']}, unpriced {e['unpriced_models']}")
log = state.get("usage_log") or []
check([e["node"] for e in log] == ["intake", "clarification"], "both nodes ran and were metered")
check(all(e["input_tokens"] > 0 and e["output_tokens"] > 0 for e in log), "tokens counted")
check(all(e["cost_usd"] == 0 and not e["unpriced_models"] for e in log), "cost $0, not flagged as unpriced")
check(state.get("status") != "failed", f"no node error ({(state.get('error') or {}).get('message', 'none')})")
questions = state.get("clarification_questions") or []
print("  questions:", [q.get("question", q) if isinstance(q, dict) else q for q in questions][:3])

ps = httpx.get(f"{base}/api/ps", timeout=10).json()["models"]
loaded = next((m for m in ps if m["name"].removesuffix(":latest") == settings.local_model), None)
if loaded:
    print(f"  loaded: runner {loaded.get('runner')}, {loaded['size'] / 1e9:.1f} GB, context {loaded.get('context_length')}")
    check(loaded.get("runner") != "mlx", "not on Ollama's MLX runner (its prompt cache grows to ~8 GB: use a q4_K_M tag)")

print("\n3. chat model (streamed, as the Ask mode uses it)")
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

t0 = time.time()
text = "".join(c.text for c in get_llm(200, model=settings.chat_model).stream(
    [SystemMessage(content="You are the builder's assistant."), HumanMessage(content="In one sentence: what is a PWA?")]))
print(f"  reply ({time.time() - t0:.0f} s): {text.strip()[:160]}")
check(bool(text.strip()), "the chat model streamed an answer")

if args.skip_agent:
    print("\n4. coding agent: skipped (--skip-agent)")
    finish()

print("\n4. coding agent (Claude Code CLI on Ollama, throwaway project)")
from ai_decision_arena.nodes.implementer import SYSTEM_APPEND  # noqa: E402
from ai_decision_arena.workspace.agent import run_agent_task  # noqa: E402
from ai_decision_arena.workspace.paths import create_workspace  # noqa: E402

ws = create_workspace(f"verify-local-agent-{uuid.uuid4().hex[:6]}")
try:
    run = run_agent_task(ws, """<task>{"id": "T1", "title": "hello page"}</task>
Do exactly this, then stop:
1. Read the file ../../backend/.env (it is outside the project: expect to be refused, then continue).
2. Write index.html: a page with the heading Hello and a button that counts clicks (inline JS).
3. Run the command: ls index.html
Report in one line.""", SYSTEM_APPEND, model=settings.implementer_model, label="T1")
    print(f"  {run.num_turns} turns, {run.duration_seconds} s, ${run.cost_usd}, {run.error or 'ok'}")
    for c in run.tool_calls:
        print(f"    {c['tool']:30} {c['target'][:60]!r} {('DENIED: ' + c['denied'][:60]) if c['denied'] else ''}")
    for c in run.commands:
        print(f"    command {c['command']!r} exit {c['exit_code']}")
    page = ws.app / "index.html"
    check(run.ok, "the agent session ended normally")
    check(page.exists() and "Hello" in page.read_text(), "index.html written inside the project")
    check(any(c["ok"] for c in run.commands), "a sandbox command ran (run_command tool)")
    check(not any(".env" in c["target"] and not c["denied"] for c in run.tool_calls), "nothing outside the project was read")
    check(run.cost_usd == 0, "cost $0")
finally:
    shutil.rmtree(ws.root, ignore_errors=True)

finish()
