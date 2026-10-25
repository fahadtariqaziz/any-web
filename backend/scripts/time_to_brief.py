"""Live timing: the real graph from the idea to the brief review pause (intake → ... → brief_validator).

Clarification questions are answered automatically, so the clock measures the agents only (active_seconds, human
pauses excluded). Prints seconds, calls and output tokens per node, from the session's usage_log.
    PERSIST_RESULTS=false uv run python scripts/time_to_brief.py ["your idea"] [--target 60]
Costs real API calls (Sonnet / Haiku, roughly $0.3-0.6) and Tavily credits. Exit code 1 if over the target.
"""

import sys
import time
import uuid
from collections import defaultdict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.config import get_settings
from ai_decision_arena.graph import build_graph

args = [a for a in sys.argv[1:] if not a.startswith("--")]
IDEA = args[0] if args else "A simple calculator web app"
TARGET = float(sys.argv[sys.argv.index("--target") + 1]) if "--target" in sys.argv else 60.0
ANSWER = "Keep it simple; use your best judgment for anything not stated."

settings = get_settings()
print(f"idea: {IDEA!r} · model {settings.anthropic_model} · extractor {settings.extractor_model} · "
      f"validator {settings.validator_model}\nnode effort: {settings.node_effort}\n")

graph = build_graph(InMemorySaver())


draft_at: list[float] = []      # when the first draft became readable (the UI shows it while the validator checks)


def run(graph_input) -> None:
    """Run until the next pause, printing every progress event (the loop reasons: judge, checker, validator)."""
    for event in graph.stream(graph_input, config, stream_mode="custom"):
        if event.get("type") == "progress":
            print(f"  {time.time() - started:6.1f}s [{event['node']}] {event['message']}")
            if event["message"].startswith("brief drafted") and not draft_at:
                draft_at.append(time.time() - started)


config = {"configurable": {"thread_id": f"time-to-brief-{uuid.uuid4().hex[:8]}"}}
started = time.time()
run({"question": IDEA, "mode": "full"})
for _ in range(6):                                  # answer clarification rounds until the brief review pause
    snapshot = graph.get_state(config)
    if not snapshot.next or not snapshot.interrupts:
        break
    payload = snapshot.interrupts[0].value
    if payload["type"] != "clarification":
        break
    print(f"clarification: {len(payload['questions'])} question(s), answered automatically")
    run(Command(resume={"answers": {q: ANSWER for q in payload["questions"]}}))
wall = time.time() - started

state = graph.get_state(config).values
per_node: dict[str, dict] = defaultdict(lambda: {"runs": 0, "seconds": 0.0, "calls": 0, "output": 0})
for e in state.get("usage_log", []):
    n = per_node[e["node"]]
    n["runs"] += 1
    n["seconds"] += e.get("seconds", 0.0)
    n["calls"] += e.get("calls", 0)
    n["output"] += e.get("output_tokens", 0)

print(f"\n{'node':18} {'runs':>4} {'seconds':>8} {'calls':>5} {'out tok':>8}")
for name, n in per_node.items():
    print(f"{name:18} {n['runs']:4} {n['seconds']:8.1f} {n['calls']:5} {n['output']:8}")
active = state.get("active_seconds", 0.0)
cost = sum(e.get("cost_usd", 0.0) for e in state.get("usage_log", []))
paused_at = state.get("current_node")
failed = [c for c in (state.get("brief_validation") or {}).get("checks", []) if not c["passed"]]
for c in failed:
    print(f"validator open issue: {c['check_id']} ({c.get('severity')}): {c['issue'][:160]}")
print(f"\nstopped after: {paused_at} · status {state.get('status')} · error {state.get('error')}")
if draft_at:
    print(f"first draft readable at {draft_at[0]:.1f}s (wall clock)")
print(f"active (agents only): {active:.1f}s · wall incl. auto-answers: {wall:.1f}s · cost ${cost:.3f}")
ok = paused_at == "brief_validator" and not state.get("error") and active <= TARGET
print(("PASS" if ok else "FAIL") + f" (target {TARGET:.0f}s active, brief validated)")
sys.exit(0 if ok else 1)
