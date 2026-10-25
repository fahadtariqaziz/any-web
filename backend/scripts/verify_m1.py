"""M1 live check: real Claude calls for intake + the first clarification round on two app ideas, plus one off-topic input.

Run from the backend/ folder (about 5 small Claude calls, no Tavily, no database):
    uv run python scripts/verify_m1.py
Prints what intake extracted and the questions clarification asks, then PASS or FAIL.
"""

import json
import sys

from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.clarification import clarification_node
from ai_decision_arena.nodes.intake import InvalidInputError, intake_node

# The calculator is our standard "smallest buildable project": if the pipeline handles it end to end, bigger
# ideas follow the same path. The second idea is slightly richer to check the questions adapt to the idea.
IDEAS = [
    "A simple calculator web app",
    "A website for my small bakery where customers can see the menu and pre-order cakes for pickup",
]
OFF_TOPIC = "what is the weather like today"
HEALTH_WORDS = ("symptom", "diagnos", "medication", "doctor", "patient", "condition")

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


print(f"model: {get_settings().anthropic_model}  max_clarification_rounds: {get_settings().max_clarification_rounds}")
for idea in IDEAS:
    print(f"\n=== {idea}")
    state = {"question": idea, "user_context": "", "mode": "full"}
    out = intake_node(state)
    print("  project_name:", out["project_name"], "| category:", out["project_category"])
    print("  idea_summary:", out["idea_summary"])
    print("  profile:", json.dumps(out["project_profile"]), "| features:", json.dumps(out["requested_features"]),
          "| constraints:", json.dumps(out["constraints"]))
    print("  missing:", out["missing_information"], "| risk_flags:", out["risk_flags"])
    check(bool(out["project_name"]) and out["project_name"] != "untitled project", "intake found a project name")
    check(out["project_category"] in ("web_app", "website", "mobile_app", "saas", "other"), f"category plausible ({out['project_category']})")
    check(len(out["missing_information"]) >= 2, "intake lists what is still unknown")
    check(not any(w in json.dumps(out).lower() for w in HEALTH_WORDS), "no health vocabulary in intake output")

    state.update(out)
    clar = clarification_node(state)
    questions = clar["clarification_questions"]
    print("  questions:")
    for i, q in enumerate(questions, 1):
        print(f"    {i}. {q}")
    check(clar["need_clarification"] is True and clar["status"] == "awaiting_clarification", "first round asks questions")
    check(3 <= len(questions) <= 6, f"between 3 and 6 questions ({len(questions)})")
    check(len(set(questions)) == len(questions), "no duplicate questions")
    check(not any(w in " ".join(questions).lower() for w in HEALTH_WORDS), "no health vocabulary in the questions")
    check(all(q.count("?") <= 1 for q in questions), "one question per item")

print(f"\n=== off-topic: {OFF_TOPIC!r}")
try:
    intake_node({"question": OFF_TOPIC, "user_context": "", "mode": "full"})
    check(False, "off-topic input rejected")
except InvalidInputError as exc:
    print("  rejected:", exc)
    check("app or website" in str(exc), "off-topic input rejected with the app-builder message")

print("\nM1 VERIFY:", "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)")
sys.exit(0 if not failures else 1)
