"""Node 1 — Intake: validate and normalize the user's app or website idea.

Writes (owner): question, user_context, project_name, project_category, idea_summary, project_profile,
requested_features, constraints, missing_information, risk_flags, counters, status, current_node.
"""

from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES
from ai_decision_arena.schemas import IntakeResult, utc_now
from ai_decision_arena.state import ArenaState

MIN_QUESTION_CHARS = 3        # "a blog" is a valid start; clarification fills in the rest
MAX_QUESTION_CHARS = 4000
MAX_CONTEXT_CHARS = 4000
MAX_MISSING_ITEMS = 8

SYSTEM_PROMPT = """You are the Intake agent of an AI application builder. A user describes an app, website, tool,
service or automation they want built. Your job: read what they wrote and normalize it. You do NOT design the
solution here and you do NOT add ideas of your own.

Rules:
- Extract ONLY what the user explicitly stated. Never invent the audience, platform, features, budget, timeline
  or technology. If the user did not say it, it is not a fact.
- Keep values close to the user's wording.
- project_name: a short working name from their words ("habit tracker app", "bakery website"); never a brand name.
- idea_summary: 1-2 neutral sentences: what they want to build, for whom, and why, as far as they said.
- project_profile: audience, platform, timeline, budget, team, existing assets, business model, only if stated.
- requested_features: each capability they asked for, with the details they gave.
- constraints: technology preferences, hosting, budget, deadline, compliance, must-use integrations, things to avoid.
- missing_information: the unknowns that would most change the solution: who the users are, the problem they face
  today and how they handle it now, must-have features, platform, constraints, what success looks like. Most
  important first.
- risk_flags: ONLY risky aspects the user actually mentioned (payments, health or financial data, minors, scraping,
  user-generated content, regulated domains). Empty list otherwise.
- If the input does not describe something to build (a general question, small talk, a request for advice), set
  is_app_request to false.
""" + BUILDER_RULES


class InvalidInputError(ValueError):
    """User input failed validation. Not retryable: the user must fix it."""


def validate_input(question: str, user_context: str) -> None:
    if len(question) < MIN_QUESTION_CHARS:
        raise InvalidInputError(f"Please describe the app or website you want to build (min {MIN_QUESTION_CHARS} characters).")
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
    report("intake", "reading your idea and extracting what you stated")
    user_content = f"<user_input>\n<question>{question}</question>"
    if user_context:
        user_content += f"\n<extra_context>{user_context}</extra_context>"
    user_content += "\n</user_input>"
    result = call_structured(IntakeResult, SYSTEM_PROMPT, user_content, max_tokens=2000, run_name="intake_llm")

    if not result.is_app_request:
        raise InvalidInputError("This doesn't look like an app or website idea. Try something like: "
                                "'A habit tracker app for students' or 'A website for my bakery with online orders'.")

    # 3) Return only the fields Intake owns, and initialize the session counters.
    return {
        "question": question,
        "user_context": user_context,
        "project_name": result.project_name.strip().lower() or "untitled project",
        "project_category": result.project_category,
        "idea_summary": result.idea_summary,
        "project_profile": {item.name: item.value for item in result.project_profile},
        "requested_features": {item.name: item.value for item in result.requested_features},
        "constraints": {item.name: item.value for item in result.constraints},
        "missing_information": result.missing_information[:MAX_MISSING_ITEMS],
        "risk_flags": result.risk_flags,
        "clarification_answers": {},
        "assumptions": [],
        "clarification_round_count": 0,
        "research_retry_count": 0,
        "debate_round": 0,
        "research_focus": [],
        "unresolved_questions": [],
        "started_at": utc_now().isoformat(timespec="seconds"),
        "withdrawn_risk_flags": [],
        "status": "intake",
        "current_node": "intake",
    }
