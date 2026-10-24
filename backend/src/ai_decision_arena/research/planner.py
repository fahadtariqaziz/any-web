"""Query planning: Claude turns the clarified case into targeted searches for all three lanes.

Quick (patient chat) sessions skip the Claude call and use fixed query templates with the condition name:
it saves a few seconds, and two broad queries per lane are enough for a short summary. The patient lane gets
a third, story-style query: real experiences become the examples the chat agent shares later."""

import json

from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.prompting import BUILDER_RULES, user_case_block
from ai_decision_arena.schemas import PERSPECTIVES, ResearchPlan, SearchQuery
from ai_decision_arena.state import ArenaState

SYSTEM_PROMPT = """You are the research planner of Health Decision Arena. Three lanes of web research run for the
user's condition, and every lane must answer the same questions: how people manage the condition day to day
(routine), what they eat (diet), which medications or treatments are used, how long until progress is seen,
and how common or rare the condition is.

Lanes:
- research: peer-reviewed studies, systematic reviews, meta-analyses (PubMed, Cochrane, journals).
- doctor: clinical guidelines and doctor-written references (WHO, CDC, NICE, NHS, Mayo Clinic, specialist societies).
- patient: real-world experiences and reviews from people living with the condition (Reddit, patient forums).

Rules:
- Return exactly {per_lane} queries per lane ({total} in total). Group them by lane, most important topic first.
- Each query combines the condition with ONE topic. Spread the topics so the lane covers routine, diet,
  medications, timeline and prevalence as far as the query budget allows (combine related topics in one query
  when needed, e.g. "diet and exercise").
- Exactly ONE query per lane must have topic overview_prevalence or progress_timeline and ask how common or
  rare the condition is and how long until improvement is typically seen (patient lane: "how long did it take
  to see improvement").
- Make queries specific to the user: type/stage, key medications, constraints (e.g. "vegetarian"),
  important symptoms. Patient-lane queries should sound like how people talk ("what worked", "experience").
- Queries are short keyword searches, not sentences. No years unless recency matters.
- preferred_domains: only condition-specific official organisations you are sure about
  (e.g. diabetes.org for diabetes); empty list otherwise. General medical sites are added automatically.
- If <focus> is non-empty this is a FOLLOW-UP search: target ONLY those open questions, still one lane per
  query, and still cover all three lanes.

<examples>
Few-shot examples of good and bad queries (for other cases; never copy them, write queries for THIS user):
Case: type 2 diabetes, on metformin, vegetarian, wants to lose weight.
- research, good: "type 2 diabetes vegetarian diet HbA1c randomized trial"
- research, bad: "What is the best diet for diabetes?" (a sentence, not specific to the user)
- doctor, good: "type 2 diabetes metformin lifestyle guideline NICE"
- patient, good: "type 2 diabetes vegetarian what worked weight loss experience"
- patient, bad: "diabetes" (no topic, too broad)
Case: migraine with aura, 3 attacks a month, office job.
- doctor, good: "migraine with aura preventive treatment guideline"
- patient, good: "migraine with aura how long until preventive worked reddit"
</examples>
""" + BUILDER_RULES

LANE_ORDER = {p: i for i, p in enumerate(PERSPECTIVES)}


QUICK_QUERY = {
    "research": ("{term} diet exercise and medication systematic review", "medications_treatment"),
    "doctor": ("{term} management guidelines daily routine diet medication", "routine_lifestyle"),
    "patient": ("{term} what worked for you diet routine experience", "routine_lifestyle"),
}


def quick_plan(state: ArenaState) -> ResearchPlan:
    """No LLM: one broad management query + the outlook query per lane."""
    term = (state.get("project_name") or "").replace("(undiagnosed)", "").strip() or state.get("question", "")[:80]
    queries = []
    for perspective in PERSPECTIVES:
        query, topic = QUICK_QUERY[perspective]
        queries.append(SearchQuery(query=query.format(term=term), perspective=perspective, topic=topic, preferred_domains=[]))
        queries.append(SearchQuery(query=OUTLOOK_QUERY[perspective].format(term=term), perspective=perspective,
                                   topic="overview_prevalence", preferred_domains=[]))
    queries.append(patient_story_query(term, PATIENT_STORY_QUERIES[0]))
    return ResearchPlan(search_term=term, queries=queries)


# Story-style patient searches: [0] runs in every quick plan, [1] only as the top-up when too few stories came back.
PATIENT_STORY_QUERIES = (
    "{term} my experience what helped me forum",
    "{term} personal story lifestyle changes that worked reddit",
)


def patient_story_query(term: str, template: str) -> SearchQuery:
    return SearchQuery(query=template.format(term=term), perspective="patient", topic="routine_lifestyle",
                       preferred_domains=[])


def plan_queries(state: ArenaState, focus: list[str] | None = None) -> ResearchPlan:
    settings = get_settings()
    if settings.session_mode == "quick" and focus is None:
        return quick_plan(state)
    per_lane = settings.queries_per_perspective
    user_content = f"""{user_case_block(state)}
<focus>{json.dumps(focus or [], indent=2)}</focus>"""

    plan = call_structured(
        ResearchPlan,
        SYSTEM_PROMPT.replace("{per_lane}", str(per_lane)).replace("{total}", str(per_lane * len(PERSPECTIVES))),
        user_content,
        max_tokens=2500,
        run_name="research_planner_llm",
    )
    # Python enforces the budget per lane even if Claude returns more, and fixes the lane order.
    kept: list[SearchQuery] = []
    count = {p: 0 for p in PERSPECTIVES}
    for q in plan.queries:
        if count[q.perspective] < per_lane:
            count[q.perspective] += 1
            kept.append(q)
    if focus is None:
        kept = _ensure_outlook_query(kept, plan.search_term, per_lane)
    plan.queries = sorted(kept, key=lambda q: LANE_ORDER[q.perspective])
    return plan


OUTLOOK_TOPICS = ("overview_prevalence", "progress_timeline")
OUTLOOK_QUERY = {
    "research": "{term} prevalence epidemiology and time to improvement with treatment",
    "doctor": "{term} how common is it typical course how long until symptoms improve",
    "patient": "{term} how long did it take to see improvement experience",
}


def _ensure_outlook_query(queries: list[SearchQuery], term: str, per_lane: int) -> list[SearchQuery]:
    """The user always gets 'how common is it' and 'how long until progress'. If Claude spent a lane's
    whole budget elsewhere, the lane's last query is replaced by a fixed prevalence/timeline query.
    (Only on the first pass: follow-up searches are focused on the Judge's open questions.)"""
    result = list(queries)
    for perspective in PERSPECTIVES:
        lane = [q for q in result if q.perspective == perspective]
        if any(q.topic in OUTLOOK_TOPICS for q in lane):
            continue
        fallback = SearchQuery(
            query=OUTLOOK_QUERY[perspective].format(term=term), perspective=perspective,
            topic="overview_prevalence", preferred_domains=[],
        )
        if len(lane) >= per_lane:
            result.remove(lane[-1])      # lowest-priority query of the lane makes room
        result.append(fallback)
    return result
