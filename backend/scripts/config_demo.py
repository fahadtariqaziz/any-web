"""Step 2.2 — print the active settings and show validation. No API calls.

Run from the backend/ folder:
    uv run python scripts/config_demo.py
    MAX_DEBATE_ROUNDS=3 uv run python scripts/config_demo.py      # one-off override
"""

from pydantic import ValidationError

from ai_decision_arena.config import Settings, get_settings

settings = get_settings()

print("--- Active settings (secrets are masked) ---")
for name, value in settings.model_dump().items():
    print(f"  {name}: {value}")

print("\n--- Loop limits ---")
print(f"  clarification rounds: {settings.max_clarification_rounds}")
print(f"  research retries:     {settings.max_research_retries}")
print(f"  debate rounds:        {settings.max_debate_rounds}")

print("\n--- Bad rubric (adds up to 0.9) is rejected ---")
try:
    Settings(rubric_weights={"fit_to_user": 0.5, "safety": 0.4})
except ValidationError as exc:
    print(f"  ❌ {exc.errors()[0]['msg']}")

print("\n--- Out-of-range limit is rejected ---")
try:
    Settings(max_debate_rounds=50)
except ValidationError as exc:
    print(f"  ❌ max_debate_rounds: {exc.errors()[0]['msg']}")
