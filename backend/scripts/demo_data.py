"""Saved, already-clarified state for a demo user so scripts can skip the questions.
This is a made-up example profile, not evidence."""

CLARIFIED_STATE = {
    "question": "I have diabetes",
    "user_context": "",
    "condition_name": "type 2 diabetes",
    "condition_category": "metabolic_endocrine",
    "case_summary": "The user has type 2 diabetes diagnosed about six months ago, takes metformin, "
                    "and wants to lower blood sugar and lose weight without insulin.",
    "health_profile": {
        "diagnosis": "type 2 diabetes, confirmed by a doctor",
        "diagnosed_since": "about 6 months ago",
        "age": "42",
        "sex": "male",
        "medications": "metformin 500 mg twice a day",
        "other_conditions": "overweight, mildly high blood pressure",
        "goal": "lower blood sugar and lose weight, avoid insulin if possible",
    },
    "symptoms": {
        "fatigue": "most afternoons",
        "increased thirst": "especially at night",
        "frequent urination": "two or three times every night",
    },
    "constraints": {
        "diet": "vegetarian",
        "budget": "prefers low-cost options",
        "preferences": "would rather avoid injections",
    },
    "missing_information": ["latest HbA1c or blood sugar readings", "current activity level"],
    "red_flags": [],
    "clarification_answers": {
        "Has a doctor confirmed the diabetes, and do you know if it is type 1 or type 2?": "yes, type 2",
        "How long ago were you diagnosed?": "about 6 months ago",
        "Which symptoms do you have now, and when do they occur?": "tired most afternoons, thirsty at night, urinating 2-3 times a night",
        "Which medications or treatments are you taking or have tried?": "metformin 500 mg twice a day",
        "Do you have other conditions or allergies?": "overweight, mildly high blood pressure, no allergies",
        "What does your daily routine and diet look like, and what do you want to achieve?":
            "desk job, little exercise, vegetarian; want lower blood sugar and weight loss without insulin",
    },
    "assumptions": ["Not specified by user: latest HbA1c or blood sugar readings", "Not specified by user: current activity level"],
    "clarification_round_count": 1,
    "research_retry_count": 0,
    "debate_round": 0,
}
