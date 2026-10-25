"""M11 live check: cost / usage (1-5), tool-call log (6), prompt registry + live evals (7), Ask caching + skills (8),
knowledge / triggers / metrics (9). Real Claude calls, one tiny coding-agent task and one Tavily search: about $0.50.

Run from the backend/ folder; the dev servers on 8001 / 3001 are needed for the HTTP and page checks:
    uv run python scripts/verify_m11.py [--session <built thread id>]

1. Token split: one raw ChatAnthropic call; the API's own usage (response_metadata["usage"]) must equal what
   pricing.tokens_from_langchain derives from langchain's usage_metadata (cache tokens included in it).
2. Nodes: intake + clarification wrapped like in the graph (real Sonnet calls) → one usage_log entry each, tokens > 0,
   cost = tokens x price table, saved to usage_events.
3. Ask: one real reply (stream_reply) on the built session's state under a THROWAWAY thread id (the reference
   project's conversation is not touched) → a usage_events row "ask" with the meter's cost.
4. HTTP: GET /usage on the built session (agent total = implementation_cost_usd; first build + changes = total)
   and GET /api/metrics (the rows of steps 2-3 are counted).
5. Page: the builder's Build tab shows the Cost card with the API's total (headless Chrome).
"""

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
from langchain_core.messages import HumanMessage

from ai_decision_arena import usage
from ai_decision_arena.config import get_settings
from ai_decision_arena.api.runner import graph_config
from ai_decision_arena.chat import stream_reply
from ai_decision_arena.checkpointing import postgres_checkpointer
from ai_decision_arena.db.repository import session_node_cost
from ai_decision_arena.graph import build_graph
from ai_decision_arena.llm import get_llm
from ai_decision_arena.nodes.clarification import clarification_node
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.node_wrapper import wrap_node
from ai_decision_arena.pricing import PRICES, PRICES_AS_OF, Tokens, cost_usd, tokens_from_langchain

API = "http://localhost:8001"
PAGE = "http://localhost:3001"
REFERENCE = "e39ceeb5-cf6b-4950-b518-b656ec65515b"
ROOT = Path(__file__).resolve().parents[2]

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


parser = argparse.ArgumentParser()
parser.add_argument("--session", default=REFERENCE, help="a BUILT session (default: the reference calculator)")
args = parser.parse_args()
settings = get_settings()
verify_thread = f"verify-m11-{uuid.uuid4().hex[:8]}"
print(f"model {settings.anthropic_model} · prices as of {PRICES_AS_OF} · throwaway thread {verify_thread} · persist_results={settings.persist_results}")
check(settings.persist_results, "PERSIST_RESULTS is on (usage_events can be written)")

print("\n1. token split against the API's own usage")
reply = get_llm(200).invoke([HumanMessage(content="Reply with the single word: ok")])
raw = reply.response_metadata.get("usage") or {}
tokens = tokens_from_langchain(reply.usage_metadata)
print(f"  API usage: {json.dumps({k: raw.get(k) for k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')})}")
print(f"  derived:   {tokens}")
check(tokens.input == raw.get("input_tokens") and tokens.output == raw.get("output_tokens"), "uncached input and output match the API")
check(tokens.cache_read == (raw.get("cache_read_input_tokens") or 0)
      and tokens.cache_write_5m + tokens.cache_write_1h == (raw.get("cache_creation_input_tokens") or 0), "cache tokens match the API")
check(settings.anthropic_model in PRICES and settings.planner_model in PRICES and settings.fallback_model in PRICES,
      "every configured graph model has a price")

print("\n2. graph nodes (wrapped like in the graph)")
state = {"thread_id": verify_thread, "question": "A simple calculator web app", "user_context": "", "mode": "full"}
out = wrap_node("intake")(intake_node)(state)
state.update(out)
out = wrap_node("clarification")(clarification_node)(state)
state.update(out)
log = state.get("usage_log") or []
for e in log:
    print(f"  {e['node']}: {e['calls']} call(s), in {e['input_tokens']} / out {e['output_tokens']} tokens, "
          f"${e['cost_usd']:.4f}, {e['seconds']} s, {e['models']}")
check([e["node"] for e in log] == ["intake", "clarification"], "one usage entry per node run")
check(all(e["calls"] >= 1 and e["input_tokens"] > 0 and e["output_tokens"] > 0 for e in log), "tokens counted for every node")
for e in log:
    (model,) = e["models"].keys() if len(e["models"]) == 1 else (None,)
    if model:
        expected = cost_usd(model, Tokens(input=e["input_tokens"], output=e["output_tokens"],
                                          cache_read=e["cache_read_tokens"], cache_write_5m=e["cache_write_tokens"]))
        check(abs(expected - e["cost_usd"]) < 1e-6, f"{e['node']}: cost = tokens x {model} price (${expected:.4f})")
check(0 < usage.llm_cost(state) < 0.25, f"two nodes cost a few cents (${usage.llm_cost(state):.4f})")
check(abs(session_node_cost(verify_thread, "intake") - log[0]["cost_usd"]) < 1e-4, "intake row saved in usage_events")

print("\n3. Ask (one real reply, throwaway thread)")
built = httpx.get(f"{API}/api/decisions/{args.session}", timeout=30)
check(built.status_code == 200, f"session {args.session} readable")
values = None
try:
    with postgres_checkpointer() as saver:                                     # read-only: get_state
        values = build_graph(checkpointer=saver).get_state(graph_config(args.session)).values
except Exception as exc:                                                       # noqa: BLE001
    check(False, f"could not read the session's state: {exc}")
if values:
    text = "".join(stream_reply(verify_thread, values, [], "In one sentence: what does this app do?"))
    print("  reply:", text.strip()[:200])
    ask = session_node_cost(verify_thread, "ask")
    check(bool(text.strip()), "Ask answered")
    check(0 < ask < 0.10, f"Ask reply metered in usage_events (${ask:.4f})")

print("\n4. HTTP")
report = httpx.get(f"{API}/api/decisions/{args.session}/usage", timeout=30).json()
impl = httpx.get(f"{API}/api/decisions/{args.session}/implementation", timeout=30).json()
print(f"  total ${report['total_usd']:.2f} = builder AI ${report['llm_usd']:.2f} + agent ${report['agent_usd']:.2f}; "
      f"measured since {report['llm_measured_since']}")
print(f"  first build ${report['first_build']['total_usd']:.2f}; changes: "
      + ", ".join(f"{c['action']} {c['round']} ${c['total_usd']:.2f}" for c in report["changes"]))
check(abs(report["agent_usd"] - impl["cost_usd"]) < 1e-3, "agent total = implementation_cost_usd")
parts = report["first_build"]["total_usd"] + sum(c["total_usd"] for c in report["changes"])
check(abs(parts - report["total_usd"]) < 0.01, f"first build + changes = total (${parts:.2f})")
check(abs(sum(s["cost_usd"] for s in report["steps"] if s["kind"] == "agent") - report["agent_usd"]) < 0.01,
      "agent steps add up to the agent total")
metrics = httpx.get(f"{API}/api/metrics?days=1", timeout=30)
check(metrics.status_code == 200, "GET /api/metrics answers")
if metrics.status_code == 200:
    m = metrics.json()
    nodes = {n["node"] for n in m["by_node"]}
    print(f"  last day: {m['total']['calls']} calls in {m['total']['sessions']} session(s), ${m['total']['cost_usd']:.4f}; "
          f"nodes {sorted(nodes)}; models {m['calls_by_model']}")
    check({"intake", "clarification", "ask"} <= nodes, "metrics count this run's intake, clarification and Ask rows")

print("\n5. builder page (headless Chrome)")
shot = Path("/tmp/verify-m11-build.png")
page = subprocess.run(["node", str(ROOT / "frontend/scripts/shot_tab.mjs"), f"{PAGE}/c/{args.session}", "Build", str(shot)],
                      capture_output=True, text=True, timeout=120)
check("Cost" in page.stdout and f"${report['total_usd']:.2f} so far" in page.stdout,
      f"Build tab shows the Cost card with ${report['total_usd']:.2f} (screenshot {shot})")
check("First build" in page.stdout or not report["changes"], "the card lists the first build and the changes")

# ======================= part 2: tool-call log =======================
print("\n6. tool calls: a tiny real coding-agent task (throwaway project) + one research search")
import shutil  # noqa: E402

from langgraph.graph import END, START, StateGraph  # noqa: E402

from ai_decision_arena.db.repository import list_tool_calls  # noqa: E402
from ai_decision_arena.nodes.implementer import SYSTEM_APPEND  # noqa: E402
from ai_decision_arena.research.search import search_one  # noqa: E402
from ai_decision_arena.schemas import SearchQuery  # noqa: E402
from ai_decision_arena.state import ArenaState  # noqa: E402
from ai_decision_arena.workspace.agent import run_agent_task  # noqa: E402
from ai_decision_arena.workspace.paths import create_workspace  # noqa: E402

tool_thread = f"verify-m11-tools-{uuid.uuid4().hex[:6]}"
ws = create_workspace(tool_thread)
try:
    run = run_agent_task(ws, """<task>{"id": "T1", "title": "hello file"}</task>
Do exactly this, then stop:
1. Read the file ../../backend/.env (it is outside the project: expect to be refused, then continue).
2. Write hello.txt containing the single word hello.
3. Run the command: ls hello.txt
Report in one line.""", SYSTEM_APPEND, model=settings.implementer_model, label="T1")
    rows = list_tool_calls(tool_thread)
    for r in reversed(rows):
        print(f"  {r.source:7} {r.tool:12} ok={r.ok!s:5} {r.target[:60]!r} {('(' + r.reason[:70] + ')') if r.reason else ''}")
    print(f"  agent: {run.num_turns} turns, ${run.cost_usd:.4f}, {run.error or 'ok'}")
    check(any(r.source == "agent" and not r.ok and r.reason for r in rows), "the denied read outside the project is logged with its reason")
    check(any(r.source == "agent" and r.ok and r.tool == "Write" for r in rows), "the allowed Write is logged")
    check(any(r.source == "sandbox" and r.tool == "ls" and r.ok and r.exit_code == 0 and r.label == "T1" for r in rows),
          "the agent's run_command is logged as a sandbox command (exit 0, label T1)")
    check(not any(".env" in (r.target or "") and r.ok for r in rows), "nothing outside the project was read")
    check(not any(s in (r.target + (r.reason or "")) for r in rows for s in ("ANTHROPIC_API_KEY=", "sk-ant")), "no secret in any logged row")
finally:
    shutil.rmtree(ws.root, ignore_errors=True)

search_thread = f"verify-m11-search-{uuid.uuid4().hex[:6]}"
builder = StateGraph(ArenaState)
builder.add_node("research", lambda s: (search_one(SearchQuery(query="online calculator accessibility complaints", domain="apps",
                                                                topic="user_complaints", preferred_domains=[])), {})[1])
builder.add_edge(START, "research")
builder.add_edge("research", END)
builder.compile().invoke({}, {"configurable": {"thread_id": search_thread}})
srows = list_tool_calls(search_thread)
check(len(srows) == 1 and srows[0].source == "search" and srows[0].ok and "hits" in srows[0].label,
      f"a research search is logged with its thread ({srows[0].label if srows else 'no row'})")

# ======================= part 3: prompt registry, evals, caching =======================
print("\n7. prompt registry + live evals")
from ai_decision_arena.prompts import lock_problems  # noqa: E402
check(not lock_problems(), "every prompt is locked at its version (prompts.lock.json)")
backend = ROOT / "backend"
offline = subprocess.run(["uv", "run", "python", "scripts/run_evals.py"], cwd=backend, capture_output=True, text=True, timeout=600)
print("  " + offline.stdout.strip().splitlines()[-1])
check(offline.returncode == 0, "offline evals pass")
live = subprocess.run(["uv", "run", "python", "scripts/run_evals.py", "--live"], cwd=backend, capture_output=True, text=True, timeout=1200)
for line in live.stdout.strip().splitlines():
    if line.startswith(("PASS", "FAIL", "skip", "        -", "EVALS")):
        print("  " + line)
check(live.returncode == 0, "live evals pass")

print("\n8. Ask: prompt caching + a builder skill")
cache_thread = f"verify-m11-ask-{uuid.uuid4().hex[:6]}"
from ai_decision_arena import tools as chat_tools_module  # noqa: E402
seen: list[dict] = []
_orig_meter = chat_tools_module._meter


def _spy(llm, message, ctx):
    if message is not None:
        seen.append(dict(message.usage_metadata or {}))
    _orig_meter(llm, message, ctx)


chat_tools_module._meter = _spy
if values:
    "".join(stream_reply(cache_thread, values, [], "In one sentence: what does the app do?"))
    answer = "".join(stream_reply(cache_thread, values, [], "Write me a ready-to-send change request to add a history "
                                  "panel that lists the last 10 calculations."))
    print("  reply:", answer.strip()[:300].replace("\n", " "), "...")
    reads = [(u.get("input_token_details") or {}).get("cache_read", 0) for u in seen]
    print(f"  cache reads per model round: {reads}")
    check(any(r > 0 for r in reads[1:]), "later Ask rounds read the cached system block")
    used = [r.tool for r in list_tool_calls(cache_thread, source="chat")]
    print(f"  Ask tools used: {used}")
    check("load_skill" in used, "Ask loaded a builder skill for the change request")
    check("Request some change in app" in answer or "Plan a bigger change" in answer, "the answer names the mode to send it with")

# ======================= part 4: knowledge, triggers, metrics page =======================
print("\n9. knowledge, triggers, metrics")
from ai_decision_arena.knowledge import search as kb_search  # noqa: E402
hits = kb_search("why is 0.1 + 0.2 not exact in JavaScript")
print("  kb:", [(h["id"], h["kind"], h["title"][:50]) for h in hits[:3]])
check(any(h["kind"] == "curated" and "decimal" in h["title"].lower() for h in hits), "the curated builder doc is found")
check(not any("medic" in h["title"].lower() or "doctor" in h["title"].lower() for h in hits), "no health doc left")
trig = httpx.get(f"{API}/api/triggers", timeout=30).json()["triggers"]
check(len(trig) >= 15, f"GET /api/triggers lists the trigger table ({len(trig)} rows)")
m = httpx.get(f"{API}/api/metrics", params={"days": 1}, timeout=30).json()
sources = {t["source"] for t in m["tools"]}
check({"agent", "sandbox", "search", "chat"} <= sources, f"metrics count tool calls of every source ({sorted(sources)})")
check(any(t["refused"] for t in m["tools"] if t["source"] == "agent"), "metrics count the denied agent call as refused")
page = subprocess.run(["node", str(ROOT / "frontend/scripts/shot_tab.mjs"), f"{PAGE}/admin/metrics", "none", "/tmp/verify-m11-metrics.png"],
                      capture_output=True, text=True, timeout=120)
check(page.returncode == 0, "metrics page rendered (screenshot /tmp/verify-m11-metrics.png)")

print("\nM11 VERIFY:", "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)")
sys.exit(0 if not failures else 1)
