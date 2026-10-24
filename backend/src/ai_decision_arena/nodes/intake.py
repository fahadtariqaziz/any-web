"""Node 1 — Intake: validate and normalize the user's health concern.

Writes (owner): question, user_context, condition_name, condition_category, case_summary,
health_profile, symptoms, constraints, missing_information, red_flags, counters, status, current_node.
"""

from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import SAFETY_RULES
from ai_decision_arena.schemas import IntakeResult, utc_now
from ai_decision_arena.state import ArenaState

MIN_QUESTION_CHARS = 3        # "flu" is a valid start; clarification fills in the rest
MAX_QUESTION_CHARS = 4000
MAX_CONTEXT_CHARS = 4000
MAX_MISSING_ITEMS = 8

SYSTEM_PROMPT = """You are the Intake agent of Health Decision Arena, a system that helps people understand
how a health condition is managed from three perspectives: published research, doctors, and other patients.

Your job: read what the user wrote and normalize it. You do NOT give advice here.

Rules:
- Extract ONLY what the user explicitly stated. Never invent age, diagnosis type, medications, duration,
  severity or anything else. If the user did not say it, it is not a fact.
- Keep values close to the user's wording.
- condition_name: the condition as the user frames it ("diabetes", not "type 2 diabetes mellitus" unless they said so).
  If they only describe symptoms, summarize the symptoms and mark it "(undiagnosed)".
- missing_information: the unknowns that would most change the guidance. Typical ones: exact type or stage,
  whether a doctor confirmed the diagnosis, how long they have had it, current treatment, other conditions,
  age group, lifestyle, and what they want to achieve. Most important first.
- red_flags: ONLY symptoms the user actually mentioned that may need urgent care. Empty list otherwise.
- case_summary restates the situation neutrally in 1-2 sentences, without adding facts.
- If the input is not about a health condition, symptom, treatment or recovery, set is_health_concern to false.
""" + SAFETY_RULES


class InvalidInputError(ValueError):
    """User input failed validation. Not retryable: the user must fix it."""


def validate_input(question: str, user_context: str) -> None:
    if len(question) < MIN_QUESTION_CHARS:
        raise InvalidInputError(f"Please describe your condition or symptoms (min {MIN_QUESTION_CHARS} characters).")
    if len(question) > MAX_QUESTION_CHARS:
        raise InvalidInputError(f"Text is too long (max {MAX_QUESTION_CHARS} characters).")
    if len(user_context) > MAX_CONTEXT_CHARS:
        raise InvalidInputError(f"Context is too long (max {MAX_CONTEXT_CHARS} characters).")


def intake_node(state: ArenaState) -> dict:
    question = (state.get("question") or "").strip()
    user_context = (state.get("user_context") or "").strip()

    # 1) Cheap Python validation first: no tokens spent on bad input.
    validate_input(question, user_context)

    # 2) Claude extracts structure. The original text is never rewritten.
    report("intake", "reading your message and extracting the facts you stated")
    user_content = f"<user_input>\n<question>{question}</question>"
    if user_context:
        user_content += f"\n<extra_context>{user_context}</extra_context>"
    user_content += "\n</user_input>"
    result = call_structured(IntakeResult, SYSTEM_PROMPT, user_content, max_tokens=2000, run_name="intake_llm")

    if not result.is_health_concern:
        raise InvalidInputError("This doesn't look like a health condition or symptom. "
                                "Try something like: 'I have diabetes' or 'I get migraines every week'.")

    # 3) Return only the fields Intake owns, and initialize the session counters.
    return {
        "question": question,
        "user_context": user_context,
        "condition_name": result.condition_name.strip() or "unspecified condition",
        "condition_category": result.condition_category,
        "case_summary": result.case_summary,
        "health_profile": {item.name: item.value for item in result.health_profile},
        "symptoms": {item.name: item.value for item in result.symptoms},
        "constraints": {item.name: item.value for item in result.constraints},
        "missing_information": result.missing_information[:MAX_MISSING_ITEMS],
        "red_flags": result.red_flags,
        "clarification_answers": {},
        "assumptions": [],
        "clarification_round_count": 0,
        "research_retry_count": 0,
        "debate_round": 0,
        "research_focus": [],
        "unresolved_questions": [],
        "started_at": utc_now().isoformat(timespec="seconds"),
        "withdrawn_red_flags": [],
        "status": "intake",
        "current_node": "intake",
    }
