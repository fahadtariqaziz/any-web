"""Node 2 — Clarification: decide if we must ask the user something, then pause to ask.

Split into TWO graph nodes on purpose:
- clarification_node        (LLM)   decides: ask or not? Never pauses.
- await_clarification_node  (human) calls interrupt() and stores the answers.

Why split? On resume, LangGraph re-runs the paused node FROM ITS FIRST LINE.
If the Claude call lived in the same node as interrupt(), it would run again on resume:
extra cost, and possibly DIFFERENT questions than the ones the user just answered.

Loop: clarification → await_clarification → clarification → ... → research   (up to max_clarification_rounds)
The Judge can also send the graph back here with its own questions (verdict.clarification_questions), and so can
the brief validator (brief_validation.clarification_questions).

Speed: before the first research pass, the research planner (research.planner.plan_queries) runs in parallel with
the clarification call. When no more questions are asked, its plan goes to `research_plan` and the research node
uses it instead of planning again (saves one call's wait). When questions ARE asked the plan is discarded (one wasted
small call per round of questions).

Writes (owner): need_clarification, clarification_questions, clarification_answers, assumptions,
clarification_round_count, withdrawn_risk_flags, research_plan (see Speed); also merges new project facts / features / constraints / risk flags,
and refines project_name / idea_summary when the answers make them more precise.
"""

import json

from langgraph.types import interrupt
from langsmith.utils import ContextThreadPoolExecutor
from pydantic import ValidationError

from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, user_case_block
from ai_decision_arena.research.planner import plan_queries
from ai_decision_arena.schemas import ClarificationAnswers, ClarificationResult
from ai_decision_arena.state import ArenaState

MAX_QUESTIONS_PER_ROUND = 6
MAX_ANSWER_CHARS = 2000

SYSTEM_PROMPT = """You are the Clarification agent of an AI application builder. Before research starts, decide whether
the user must answer questions, and write those questions.

FIRST ROUND (no previous answers yet): ask 4-6 short questions so the research and the solution fit THIS project.
Cover, unless already stated: (1) who the users are and what problem they face today, (2) the main objective or
outcome the user wants, (3) the must-have features for a first version, (4) the platform (web, mobile, desktop),
(5) the ONE constraint that matters most for this idea (a technology preference, budget, deadline, hosting or
compliance: choose one, do not list them), (6) existing alternatives they know or use and what is wrong with them,
(7) how they will judge success. Pick the most useful within the limit; skip anything already answered.

LATER ROUNDS (at most {max_rounds} rounds in total): ask again ONLY if an answer revealed something that materially
changes the research or the solution (a different audience, a regulated domain, a platform change, a contradiction
between answers, a must-have feature that is still unclear). Otherwise set need_clarification to false.

If <judge_questions> is non-empty, the Judge needs those answers to rank the proposals: ask them (reworded if
helpful) plus anything else essential, within the limit. If <brief_questions> is non-empty, the brief validator
found critical information missing or contradictory in the solution brief: ask those the same way.
If <brief_feedback> holds a request about the requirements (the user corrected the brief), put the facts it states
into new_profile_facts / new_features / new_constraints (reuse existing keys when it corrects them), refine the
project name / summary if needed, and ask only if the request itself is unclear.

Rules:
- At most {max_questions} questions per round, in plain language. ONE question = ONE answer: never pack several
  sub-questions into one. If a topic has several sub-questions, ask only the single most useful one, with example
  answers in brackets.
- Never join separate topics in one question as a list ("technology, hosting, budget or timeline preferences?"):
  those are four questions. Ask the one that matters most, or ask them separately within the limit.
- Questions must be specific to this idea (name the product type, the audience, the feature), never generic.
- Never ask about something the user already stated or already answered, including facts in
  <remembered_from_earlier_sessions> (a returning user): at most confirm one that matters and may have changed.
- Put new facts from the user's answers into new_profile_facts / new_features / new_constraints.
  Extract only what the user actually said. An answer of "(skipped by user)" means unknown.
- Put newly revealed risky aspects (payments, personal or health data, minors, scraping, regulated domains) into
  new_risk_flags. Only GENUINELY NEW ones: never repeat or reword a flag already listed in <risk_flags>.
- If an answer CORRECTS a fact already in <project_profile>, reuse that exact key in new_profile_facts so the old
  value is overwritten (e.g. "platform": "mobile"), instead of adding a second, contradicting key.
- withdrawn_risk_flags: ONLY when a later answer of the user directly contradicts the factual premise of a flag in
  <risk_flags> (flag "stores health data", user now says "no personal data at all"). Copy the flag text exactly.
  If in doubt, keep the flag.
- refined_project_name / refined_idea_summary: fill them when the answers make the idea more precise or change it
  materially; otherwise empty strings.
- If can_ask_more is false, you MUST set need_clarification to false.
- Whenever need_clarification is false, list explicit assumptions for important info that is still missing.
""" + BUILDER_RULES


def _build_user_content(state: ArenaState, can_ask_more: bool) -> str:
    judge_questions = (state.get("verdict") or {}).get("clarification_questions", [])
    validation = state.get("brief_validation") or {}
    brief_questions = validation.get("clarification_questions", []) if validation.get("verdict") == "clarify" else []
    return f"""{user_case_block(state)}
<missing_information>{json.dumps(state.get("missing_information", []), indent=2)}</missing_information>
<judge_questions>{json.dumps(judge_questions, indent=2)}</judge_questions>
<brief_questions>{json.dumps(brief_questions, indent=2)}</brief_questions>
<rounds_used>{state.get("clarification_round_count", 0)}</rounds_used>
<can_ask_more>{str(can_ask_more).lower()}</can_ask_more>"""


def clarification_node(state: ArenaState) -> dict:
    """LLM decision: do we need more input? (No interrupt here.)"""
    settings = get_settings()
    rounds_used = state.get("clarification_round_count", 0)
    can_ask_more = rounds_used < settings.max_clarification_rounds

    report("clarification", "deciding which questions would change the solution" if rounds_used == 0
           else "reading your answers and deciding whether to ask more")
    def decide() -> ClarificationResult:
        return call_structured(
            ClarificationResult,
            SYSTEM_PROMPT.replace("{max_questions}", str(MAX_QUESTIONS_PER_ROUND))
                         .replace("{max_rounds}", str(settings.max_clarification_rounds)),
            _build_user_content(state, can_ask_more),
            max_tokens=2000,
            run_name="clarification_llm",
        )

    def plan_ahead():
        try:
            return plan_queries(state)
        except Exception:          # a failed speculative plan costs nothing: the research node plans itself
            return None

    first_research_pass = not state.get("evidence")
    with ContextThreadPoolExecutor(max_workers=2) as pool:
        planned = pool.submit(plan_ahead) if first_research_pass else None
        result = decide()
        research_plan = planned.result() if planned else None

    # Merge facts learned from the user's answers.
    profile = dict(state.get("project_profile", {}))
    profile.update({item.name: item.value for item in result.new_profile_facts})
    features = dict(state.get("requested_features", {}))
    features.update({item.name: item.value for item in result.new_features})
    constraints = dict(state.get("constraints", {}))
    constraints.update({item.name: item.value for item in result.new_constraints})
    risk_flags, withdrawn = _merge_risk_flags(state, result)

    # Python has the final say on routing, not the LLM:
    # no asking past the round limit, no repeated questions, no empty question lists.
    already_asked = set(state.get("clarification_answers", {}))
    questions = [q for q in result.questions if q not in already_asked][:MAX_QUESTIONS_PER_ROUND]
    need = result.need_clarification and can_ask_more and bool(questions)

    update = {
        "project_profile": profile,
        "requested_features": features,
        "constraints": constraints,
        "risk_flags": risk_flags,
        "withdrawn_risk_flags": withdrawn,
        "need_clarification": need,
        "clarification_questions": questions if need else [],
        "clarification_reason": result.reason,
        "current_node": "clarification",
    }
    # Python accepts a refinement only if the LLM actually gave one.
    if result.refined_project_name.strip():
        update["project_name"] = result.refined_project_name.strip().lower()
    if result.refined_idea_summary.strip():
        update["idea_summary"] = result.refined_idea_summary.strip()
    if need:
        update["status"] = "awaiting_clarification"
    else:
        assumptions = result.assumptions
        if not assumptions and not state.get("assumptions"):
            # Never continue silently: record what is still unknown, without guessing values.
            assumptions = [f"Not specified by user: {item}" for item in state.get("missing_information", [])]
        update["assumptions"] = list(state.get("assumptions", [])) + [a for a in assumptions if a not in state.get("assumptions", [])]
        update["status"] = "researching"
        if research_plan is not None:
            update["research_plan"] = research_plan.model_dump(mode="json")
    return update


def _merge_risk_flags(state: ArenaState, result: ClarificationResult) -> tuple[list[str], list[dict]]:
    """New flags are appended; a flag is withdrawn only if the LLM names an EXISTING flag (exact text,
    ignoring case and spaces). Withdrawn flags are moved to withdrawn_risk_flags, never deleted."""
    def key(text: str) -> str:
        return " ".join(text.lower().split())

    risk_flags = list(state.get("risk_flags", []))
    withdrawn = list(state.get("withdrawn_risk_flags", []))
    for item in result.withdrawn_risk_flags:
        match = next((f for f in risk_flags if key(f) == key(item.flag)), None)
        if match:                                   # unknown text → ignored, the flag stays active
            risk_flags.remove(match)
            withdrawn.append({"flag": match, "reason": item.reason})
    gone = {key(w["flag"]) for w in withdrawn}
    risk_flags += [f for f in result.new_risk_flags if f not in risk_flags and key(f) not in gone]
    return risk_flags, withdrawn


def await_clarification_node(state: ArenaState) -> dict:
    """Human input: pause the graph until the user answers. (No LLM here.)"""
    questions = state.get("clarification_questions", [])
    payload = {
        "type": "clarification",
        "questions": questions,
        "round": state.get("clarification_round_count", 0) + 1,
    }

    # Keep asking until the answer is valid. Each interrupt() is a separate pause.
    error = None
    while True:
        raw = interrupt((payload | {"error": error}) if error else payload)
        try:
            answers = ClarificationAnswers.model_validate(raw).answers
        except ValidationError as exc:
            error = f"Invalid answer format: {exc.errors()[0]['msg']}"
            continue
        unknown = set(answers) - set(questions)
        if unknown:
            error = f"Answers given for questions that were not asked: {sorted(unknown)}"
            continue
        break

    # Store every asked question; unanswered ones are recorded as skipped.
    cleaned = {
        q: (answers.get(q) or "").strip()[:MAX_ANSWER_CHARS] or "(skipped by user)"
        for q in questions
    }
    return {
        "clarification_answers": {**state.get("clarification_answers", {}), **cleaned},
        "clarification_round_count": state.get("clarification_round_count", 0) + 1,
        "clarification_questions": [],
        "current_node": "await_clarification",
    }
