"""M5 live check: the user's review of the brief, on the real graph, starting from the cached M4 state (calculator).

Needs backend/.cache/brief_calculator.json (written by scripts/verify_m4.py). Steps:
1. The router LLM classifies three typical change requests (target "auto"): 3 small Claude calls.
2. The graph is loaded at the review pause (InMemorySaver + update_state as brief_validator), the payload is checked.
3. A WORDING change request: the writer revises the reviewed draft, the validator re-checks it, the graph pauses
   again at review round 2 (3 + 1-4 Claude calls).
4. Approve: approval time + hash recorded, the approved brief saved to project_artifacts in the real database
   (ai_decision_arena_2), completion saves the session. Then the artifact row is read back.
    uv run python scripts/verify_m5.py
"""

import json
import sys
import time
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.brief import brief_hash, brief_is_approved
from ai_decision_arena.config import get_settings, session_mode
from ai_decision_arena.db.repository import list_artifacts
from ai_decision_arena.graph import build_graph
from ai_decision_arena.nodes.brief_review import _route_by_llm

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "brief_calculator.json"
NEW_NAME = "PlainCalc"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


if not CACHE.exists():
    sys.exit(f"{CACHE} is missing: run scripts/verify_m4.py first.")

cached = json.loads(CACHE.read_text())
thread_id = f"verify-m5-{int(time.time())}"
config = {"configurable": {"thread_id": thread_id}}

with session_mode("full"):
    settings = get_settings()
    print(f"model: {settings.anthropic_model} · thread {thread_id} · persist_results={settings.persist_results}")

    # --- 1) auto routing ------------------------------------------------------------------------------------
    print("\n=== 1) routing change requests (target auto)")
    cases = [
        ("Please make the overview shorter and fix the typo in section 2.", {"wording"}),
        ("It is actually for primary school children learning arithmetic, not for adults.", {"requirements"}),
        ("Look up what users complain about in the iOS and Android calculator apps; the evidence feels thin.", {"research"}),
    ]
    for feedback, expected in cases:
        probe = cached | {"brief_feedback": [{"round": 1, "action": "request_changes", "target": "auto", "feedback": feedback}]}
        routing = _route_by_llm(probe)
        print(f"  {routing.target:12} ← {feedback[:70]}  ({routing.reasoning[:90]})")
        check(routing.target in expected, f"routed to {sorted(expected)}")

    # --- 2) the pause -------------------------------------------------------------------------------------------
    print("\n=== 2) review pause")
    graph = build_graph(InMemorySaver())
    state = {k: v for k, v in cached.items() if k != "brief_feedback"} | {"thread_id": thread_id, "mode": "full",
                                                                           "brief_review_round_count": 0}
    check(state["brief_validation"]["verdict"] == "approve", "cached brief was approved by the validator")
    graph.update_state(config, state, as_node="brief_validator")
    graph.invoke(None, config)
    snapshot = graph.get_state(config)
    payload = snapshot.interrupts[0].value if snapshot.interrupts else {}
    check(snapshot.next == ("await_brief_review",), f"paused at await_brief_review ({snapshot.next})")
    check(payload.get("type") == "brief_review" and payload.get("round") == 1, "payload type brief_review, round 1")
    check(payload.get("brief_markdown") == cached["brief_markdown"], "payload shows the validated markdown")
    first_revision = cached["brief"]["revision"]

    # --- 3) wording change ----------------------------------------------------------------------------------------
    print(f"\n=== 3) wording change: name the app {NEW_NAME}")
    graph.invoke(Command(resume={"action": "request_changes", "target": "wording",
                                 "feedback": f"Name the app '{NEW_NAME}' and list a dark mode as a later enhancement."}), config)
    snapshot = graph.get_state(config)
    values = snapshot.values
    payload = snapshot.interrupts[0].value if snapshot.interrupts else {}
    print(f"  draft {values['brief']['revision'] + 1}: verdict {values['brief_validation']['verdict']}, "
          f"{values['brief_validation']['word_count']} words, name '{values['brief']['project_overview']['proposed_name']}'")
    check(snapshot.next == ("await_brief_review",) and payload.get("round") == 2, "revised, revalidated and shown again (round 2)")
    check(values["brief"]["revision"] > first_revision, f"draft number grew ({first_revision} → {values['brief']['revision']})")
    check(values["brief_validation"]["brief_generated_at"] == values["brief"]["generated_at"], "the validation belongs to the new draft")
    check(NEW_NAME.lower() in values["brief_markdown"].lower(), f"the new name appears in the brief")
    later = " ".join(values["brief"]["proposed_solution"]["future_enhancements"]).lower()
    check("dark" in later, f"dark mode listed as a later enhancement ({values['brief']['proposed_solution']['future_enhancements']})")
    check(values["brief_feedback"][-1]["resolved_target"] == "wording" and values["brief_review_round_count"] == 1,
          "feedback recorded (round 1, wording)")
    check(not values.get("brief_approved_at"), "not approved yet")

    # --- 4) approve -----------------------------------------------------------------------------------------------
    print("\n=== 4) approve")
    graph.invoke(Command(resume={"action": "approve"}), config)
    snapshot = graph.get_state(config)
    values = snapshot.values
    check(snapshot.next == (), "graph finished after approval")
    check(brief_is_approved(values), "approval matches exactly the reviewed brief (hash)")
    check(values["status"] in ("completed", "completed_with_uncertainty"), f"status {values['status']}")
    if settings.persist_results:
        rows = list_artifacts(thread_id, "brief")
        print(f"  artifacts: {[(r.kind, r.version, r.content_hash[:12]) for r in rows]}")
        check(len(rows) == 1 and rows[0].version == 1, "one approved brief stored as version 1")
        check(bool(rows) and rows[0].content_hash == brief_hash(values["brief_markdown"]) == values["brief_approved_hash"],
              "stored hash = approved hash = hash of the brief")
    else:
        print("  (PERSIST_RESULTS=false: artifact check skipped)")

print("\nM5 VERIFY:", "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)")
sys.exit(0 if not failures else 1)
