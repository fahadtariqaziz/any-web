"""Step 2.1 — see Pydantic validation in action. No API calls.

Run from the backend/ folder:
    uv run python scripts/schemas_demo.py
"""

import json

from pydantic import ValidationError

from ai_decision_arena.schemas import ClarificationResult, Evidence, ResearchPlan, Verdict


def show(title: str, fn) -> None:
    print(f"\n--- {title} ---")
    try:
        result = fn()
        print("✅ valid:", result)
    except ValidationError as exc:
        print(f"❌ rejected ({exc.error_count()} error(s)):")
        for err in exc.errors():
            print(f"   • {'.'.join(map(str, err['loc']))}: {err['msg']}")


# 1) A good evidence record
good = {
    "evidence_id": "ev_001",
    "perspective": "doctor",
    "source_title": "NHS: Type 2 diabetes - Food and keeping active",
    "source_url": "https://www.nhs.uk/conditions/type-2-diabetes/food-and-keeping-active/",
    "source_type": "medical_reference",
    "evidence_strength": "expert_or_reference",
    "relevant_excerpt": "Aim for at least 2.5 hours of moderate activity a week.",
    "is_direct_quote": False,
    "claims_supported": ["Regular activity is part of type 2 diabetes management"],
    "relevance_score": 0.9,
}
show("Good evidence", lambda: Evidence.model_validate(good).evidence_id)

# 2) Bad evidence: wrong id format, unknown perspective, invalid URL, unknown source type, score > 1
bad = good | {"evidence_id": "evidence-1", "perspective": "nurse", "source_url": "not a url",
              "source_type": "blog", "relevance_score": 1.7}
show("Bad evidence", lambda: Evidence.model_validate(bad))

# 3) Clarification: the exact field name `need_clarification` is required, and questions must exist
show("Clarification OK", lambda: ClarificationResult(
    need_clarification=True, questions=["How long ago were you diagnosed?"], reason="Changes the guidance.",
    new_profile_facts=[], new_symptoms=[], new_constraints=[], new_red_flags=[], assumptions=[]))
show("Clarification asking with no questions (model_validator)", lambda: ClarificationResult(
    need_clarification=True, questions=[], reason="oops",
    new_profile_facts=[], new_symptoms=[], new_constraints=[], new_red_flags=[], assumptions=[]))

# 4) Research plan must cover all three lanes
show("Research plan missing the patient lane", lambda: ResearchPlan(search_term="type 2 diabetes", queries=[
    {"query": "type 2 diabetes diet meta-analysis", "perspective": "research", "topic": "diet", "preferred_domains": []},
    {"query": "type 2 diabetes guideline treatment", "perspective": "doctor", "topic": "medications_treatment", "preferred_domains": []},
    {"query": "type 2 diabetes prevalence", "perspective": "research", "topic": "overview_prevalence", "preferred_domains": []},
]))

# 5) Judge verdict: only the 4 allowed decisions
show("Verdict with unknown decision", lambda: Verdict(decision="pick_doctor_plan", reason="I like it"))

# 6) How a model is stored in ArenaState: a plain JSON-friendly dict
print("\n--- Evidence as stored in state (model_dump) ---")
print(json.dumps(Evidence.model_validate(good).model_dump(mode="json"), indent=2))

# 7) This JSON schema is what Claude will see when it fills a model (structured output)
print("\n--- JSON schema Claude will receive for ClarificationResult ---")
print(json.dumps(ClarificationResult.model_json_schema(), indent=2))
