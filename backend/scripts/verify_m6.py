"""M6 live check: the planner (Opus) on the real graph, from the cached brief (calculator idea), then plan approval.

Needs backend/.cache/brief_calculator.json (written by scripts/verify_m4.py). One Opus call (a few minutes at effort
"high"; a failed plan check costs a self-correcting retry). Steps:
1. The planner model is checked against the API's model list (never assumed).
2. The cached brief is marked approved (as brief_review_router does) and the graph continues from there: the guard
   lets the planner run, the plan is checked and shown at the plan review pause.
3. The plan is approved: approval hash recorded, plan saved to project_artifacts (real DB), session completed.
    uv run python scripts/verify_m6.py
Writes backend/.cache/plan_calculator.json (the full state) for M7/M8.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.brief import brief_hash
from ai_decision_arena.config import get_settings, session_mode
from ai_decision_arena.db.repository import list_artifacts
from ai_decision_arena.graph import build_graph
from ai_decision_arena.llm import available_models, resolve_model
from ai_decision_arena.plan import plan_hash, plan_is_approved
from ai_decision_arena.schemas import ImplementationPlan, ProblemBrief, command_problems

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
BRIEF_CACHE = CACHE_DIR / "brief_calculator.json"
PLAN_CACHE = CACHE_DIR / "plan_calculator.json"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


if not BRIEF_CACHE.exists():
    sys.exit(f"{BRIEF_CACHE} is missing: run scripts/verify_m4.py first.")

cached = json.loads(BRIEF_CACHE.read_text())
thread_id = f"verify-m6-{int(time.time())}"
config = {"configurable": {"thread_id": thread_id}}

with session_mode("full"):
    settings = get_settings()

    # --- 1) model availability ------------------------------------------------------------------------------
    print("=== 1) planner model")
    ids = available_models()
    model, note = resolve_model(settings.planner_model)
    print(f"  {len(ids or [])} models listed; planner wants {settings.planner_model} → {model} {note}")
    check(ids is not None, "the API's model list was read")
    check(model == settings.planner_model, f"{settings.planner_model} is available and used")

    # --- 2) planner -------------------------------------------------------------------------------------------
    print(f"\n=== 2) planner (effort {settings.planner_effort}, max_tokens {settings.planner_max_tokens})")
    approved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = {k: v for k, v in cached.items() if not k.startswith("plan") and k not in ("implementation_plan", "implementation_tasks")}
    state |= {"mode": "full", "brief_feedback": [{"round": 1, "action": "approve", "target": "auto", "feedback": "", "at": approved_at}],
              "brief_review_route": "approved", "brief_approved_at": approved_at,
              "brief_approved_hash": brief_hash(cached["brief_markdown"])}
    graph = build_graph(InMemorySaver())
    graph.update_state(config, state, as_node="brief_review_router")
    started = time.time()
    graph.invoke(None, config)
    seconds = time.time() - started
    snapshot = graph.get_state(config)
    values = snapshot.values
    payload = snapshot.interrupts[0].value if snapshot.interrupts else {}
    check(snapshot.next == ("await_plan_review",), f"paused at the plan review ({snapshot.next}) after {seconds:.0f}s")
    if values.get("error"):
        print(f"  error: {values['error']}")
    if not values.get("implementation_plan"):
        print("\nM6 VERIFY: FAIL (no plan)")
        sys.exit(1)

    plan = ImplementationPlan.model_validate(values["implementation_plan"])
    brief = ProblemBrief.model_validate(values["brief"])
    print("\n" + "=" * 100 + "\n" + values["plan_markdown"] + "=" * 100)
    print(f"  {len(plan.phases)} phases, {len(plan.tasks)} tasks, model {values['models_used'].get('planner')}")
    check(values["models_used"].get("planner") == model, "models_used records the planner model")
    check(payload.get("type") == "plan_review" and payload.get("round") == 1, "payload type plan_review, version 1")
    check(2 <= len(plan.tasks) <= 40 and len(plan.phases) >= 2, "a plan with phases and 2-40 tasks")
    check(plan.tasks[0].depends_on == [] and all(t.verify_commands for t in plan.tasks), "first task has no dependency; every task has verify commands")
    all_commands = [c for t in plan.tasks for c in t.verify_commands] + plan.commands.install + plan.commands.test + plan.commands.build + [plan.commands.dev]
    check(all(not command_problems(c) for c in all_commands), f"all {len(all_commands)} commands pass the sandbox policy")
    covered = {" ".join(c.feature.lower().split()) for c in plan.feature_coverage}
    missing = [f for f in brief.proposed_solution.mvp_features if " ".join(f.lower().split()).strip(" .") not in {x.strip(" .") for x in covered}]
    check(not missing, f"every approved MVP feature is covered ({len(brief.proposed_solution.mvp_features)}; missing {missing})")
    check([t["id"] for t in values["implementation_tasks"]] == [t.id for t in plan.tasks], "implementation_tasks derived from the plan")
    check(not plan_is_approved(values), "not approved yet")

    # --- 3) approve -------------------------------------------------------------------------------------------
    print("\n=== 3) approve the plan")
    graph.invoke(Command(resume={"action": "approve"}), config)
    snapshot = graph.get_state(config)
    values = snapshot.values
    check(snapshot.next == (), "graph finished after the plan approval")
    check(plan_is_approved(values) and values["plan_approved_hash"] == plan_hash(values["plan_markdown"]),
          "approval matches exactly the reviewed plan (and the approved brief)")
    if settings.persist_results:
        rows = list_artifacts(thread_id)
        print(f"  artifacts: {[(r.kind, r.version, r.content_hash[:12]) for r in rows]}")
        check([r.kind for r in rows] == ["plan"] and rows[0].content_hash == values["plan_approved_hash"],
              "approved plan stored in project_artifacts with its hash")

CACHE_DIR.mkdir(exist_ok=True)
PLAN_CACHE.write_text(json.dumps(dict(values), indent=2, default=str))
print(f"\n💾 full state saved to {PLAN_CACHE}")
print("\nM6 VERIFY:", "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)")
sys.exit(0 if not failures else 1)
