"""Shared test fixtures: no network, no database, no real API keys.

- Environment defaults are set BEFORE the package is imported, so Settings never needs backend/.env and never
  touches the real database (DATABASE_URL points at a port nobody listens on; PERSIST_RESULTS=false).
- `fake_llm` replaces `llm.call_structured` in every module that imported it by name. The fake builds a VALID
  instance of the requested Pydantic schema from the prompt text (plan ids, evidence ids, source indexes), so the
  nodes' own Python (id filtering, weighted totals, routing) runs for real while Claude is never called.
- `fake_search` replaces the Tavily call with canned hits, one small set per query.
- `graph` builds the real graph on an InMemorySaver.
"""

import os
import re

# --- 1) environment first (before any ai_decision_arena import) -------------------------------------------
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
os.environ.setdefault("TAVILY_API_KEY", "test-key-not-used")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["PERSIST_RESULTS"] = "false"
os.environ["CHECK_INS_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "postgresql://test:test@127.0.0.1:1/never_connected"

import pytest  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from ai_decision_arena import schemas as S  # noqa: E402
from ai_decision_arena.config import get_settings  # noqa: E402

# Modules that did `from ai_decision_arena.llm import call_structured`: each holds its own reference.
LLM_USERS = [
    "ai_decision_arena.nodes.intake",
    "ai_decision_arena.nodes.clarification",
    "ai_decision_arena.nodes.proposer",
    "ai_decision_arena.nodes.critic",
    "ai_decision_arena.nodes.judge",
    "ai_decision_arena.nodes.evidence_checker",
    "ai_decision_arena.nodes.final_report",
    "ai_decision_arena.research.planner",
    "ai_decision_arena.research.extractor",
]

PLAN_ID_RE = re.compile(r'<plan id="([a-z]+_[a-c])"')
EVIDENCE_ID_RE = re.compile(r'<item id="(ev_\d+)"')
SOURCE_RE = re.compile(r'<source index="(\d+)" type="([a-z_]+)" perspective="([a-z]+)"')


def tag(name: str, text: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    return m.group(1).strip() if m else ""


# --- 2) builders: one valid instance per schema, derived from the prompt --------------------------------------

def build_intake(system: str, user: str) -> S.IntakeResult:
    question = tag("question", user)
    return S.IntakeResult(
        is_app_request=True,
        project_name=question.lower()[:40] or "untitled project",
        project_category="other",
        idea_summary=f"The user wrote: {question}",
        project_profile=[],
        requested_features=[],
        constraints=[],
        missing_information=["target users", "must-have features"],
        risk_flags=[],
    )


def build_clarification(system: str, user: str) -> S.ClarificationResult:
    rounds_used = int(tag("rounds_used", user) or 0)
    can_ask_more = tag("can_ask_more", user) == "true"
    ask = rounds_used == 0 and can_ask_more
    return S.ClarificationResult(
        need_clarification=ask,
        questions=["Who are the main users of this app?", "Which features must the first version have?"] if ask else [],
        reason="first round" if ask else "enough information",
        new_profile_facts=[S.NamedValue(name="audience", value="university students")] if rounds_used else [],
        new_features=[],
        new_constraints=[],
        new_risk_flags=[],
        withdrawn_risk_flags=[],
        refined_project_name="",
        refined_idea_summary="",
        assumptions=[] if ask else ["Assumed a web app without user accounts."],
    )


def build_research_plan(system: str, user: str) -> S.ResearchPlan:
    term = tag("project", user) or "project"
    return S.ResearchPlan(
        search_term=term,
        queries=[
            S.SearchQuery(query=f"{term} management guideline", perspective="doctor", topic="routine_lifestyle", preferred_domains=[]),
            S.SearchQuery(query=f"{term} randomized trial diet", perspective="research", topic="diet", preferred_domains=[]),
            S.SearchQuery(query=f"{term} what worked experience", perspective="patient", topic="routine_lifestyle", preferred_domains=[]),
        ],
    )


def build_extraction(system: str, user: str) -> S.ExtractionResult:
    sources = SOURCE_RE.findall(user)
    evidence = []
    for index, source_type, perspective in sources:
        evidence.append(S.ExtractedEvidence(
            source_index=int(index),
            perspective=perspective,
            source_type=source_type,
            evidence_strength="unknown",
            relevant_excerpt=f"Paraphrased finding from source {index}.",
            is_direct_quote=False,
            claims_supported=[f"claim {index}"],
            limitations=[],
            patient_context=(S.PatientContext(experience_described="walked daily", is_recurring=False, context="",
                                              what_helped=["walking"], relevant_to_user=True)
                             if perspective == "patient" else None),
            sentiment="positive" if perspective == "patient" else None,
            relevance_score=0.8,
            reliability_notes="test source",
        ))
    return S.ExtractionResult(
        evidence=evidence, rejected=[], summary="What this lane says.", prevalence_note="Common.",
        evidence_gaps=[], conflicting_claims=[],
    )


def _plan(name: str, ids: list[str]) -> S.ProposedPlan:
    return S.ProposedPlan(
        name=name, summary="A plan.", daily_routine=["walk 30 min"], diet=["more vegetables"],
        medications_treatments=[], expected_timeline="weeks", prevalence_and_outlook="common, manageable",
        benefits=["simple"], drawbacks_risks=["slow"], assumptions=[], difficulty="low",
        safety_notes="Discuss with your doctor.", supporting_evidence_ids=ids, evidence_gaps=[],
    )


def build_proposer(system: str, user: str) -> S.ProposerOutput:
    ids = EVIDENCE_ID_RE.findall(user)
    if not ids:
        return S.ProposerOutput(plans=[], why_fewer_than_two="no evidence", evidence_too_thin=True)
    plans = [_plan("Plan A", ids[:1]), _plan("Plan B", ids[:1])]
    if "QUICK SESSION" in system:
        plans = plans[:1]
    return S.ProposerOutput(plans=plans, why_fewer_than_two="quick session" if len(plans) < 2 else "", evidence_too_thin=False)


def build_critic(system: str, user: str) -> S.CriticOutput:
    return S.CriticOutput(criticisms=[
        S.Criticism(
            plan_id=pid,
            points=[S.CriticismPoint(category="missing_consideration", issue="No monitoring step.", severity="low",
                                     basis="clinical_reasoning", is_verified_problem=False, evidence_ids=[],
                                     suggested_improvement="Add monitoring.")],
            overall_assessment="Reasonable.",
        )
        for pid in PLAN_ID_RE.findall(user)
    ])


def build_judgement(system: str, user: str) -> S.PerspectiveJudgement:
    criteria = list(get_settings().rubric_weights)
    scores = []
    for i, pid in enumerate(PLAN_ID_RE.findall(user)):
        value = 8.0 if i == 0 else 6.0          # the first plan of each lane wins, deterministically
        scores.append(S.PlanScore(
            plan_id=pid,
            criterion_scores=[S.CriterionScore(criterion=c, score=value, explanation="test") for c in criteria],
            key_benefits=["simple"], key_drawbacks=["slow"], confidence="medium", confidence_reason="test",
            supporting_evidence_ids=[], remaining_risks=[],
        ))
    return S.PerspectiveJudgement(
        reasoning="Plan A is better supported.", scores=scores, comparison="A over B.",
        evidence_sufficient=True, insufficiency_reason="", required_evidence=[], clarification_questions=[],
    )


def build_verification(system: str, user: str) -> S.PlanVerification:
    cited = EVIDENCE_ID_RE.findall(tag("cited_evidence", user))
    return S.PlanVerification(
        claims=[S.ClaimCheck(claim="Walking helps.", evidence_ids=cited[:1], status="verified" if cited else "unavailable",
                             notes="test", is_anecdotal=False, is_material=False)],
        overall="Well supported.", material_gaps=[],
    )


def build_narrative(system: str, user: str) -> S.ReportNarrative:
    return S.ReportNarrative(overview="Overview.", where_perspectives_agree=["walking"], where_perspectives_differ=[],
                             key_uncertainties=[], next_steps=["Ask your doctor about monitoring."])


def build_summary(system: str, user: str) -> S.OnboardingSummary:
    return S.OnboardingSummary(opening="Hi.", doctors_say="- walk", patients_say="- walk", research_says="- walk",
                               invitation="Ask me anything.")


DEFAULT_BUILDERS = {
    S.IntakeResult: build_intake,
    S.ClarificationResult: build_clarification,
    S.ResearchPlan: build_research_plan,
    S.ExtractionResult: build_extraction,
    S.ProposerOutput: build_proposer,
    S.CriticOutput: build_critic,
    S.PerspectiveJudgement: build_judgement,
    S.PlanVerification: build_verification,
    S.ReportNarrative: build_narrative,
    S.OnboardingSummary: build_summary,
}


class FakeLLM:
    """Drop-in for llm.call_structured. `overrides` maps a schema class to a builder(system, user) -> instance."""

    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []
        self.overrides: dict[type, object] = {}

    def __call__(self, schema, system_prompt, user_content, *, max_tokens=None, run_name=None):
        self.calls.append((schema.__name__, run_name))
        builder = self.overrides.get(schema) or DEFAULT_BUILDERS[schema]
        result = builder(system_prompt, user_content)
        assert isinstance(result, schema), f"builder for {schema.__name__} returned {type(result).__name__}"
        return result

    def count(self, schema_name: str) -> int:
        return sum(1 for name, _ in self.calls if name == schema_name)


# --- 3) fixtures -----------------------------------------------------------------------------------------------

@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    for module in LLM_USERS:
        monkeypatch.setattr(f"{module}.call_structured", fake)
    return fake


def fake_run_searches(queries):
    """Two canned hits per query, URLs unique per lane and query. Never fails."""
    hits = []
    for n, q in enumerate(queries):
        for i in range(2):
            hits.append(S.SearchHit(
                url=f"https://example.org/{q.perspective}/{n}/{i}",
                title=f"{q.perspective} source {n}-{i}",
                snippet=f"Snippet about {q.query} number {i}. Walking daily helped.",
                tavily_score=0.9 - 0.1 * i,
                published_at=None,
                source_type={"research": "research_paper", "doctor": "clinical_guideline", "patient": "patient_community"}[q.perspective],
                query=q.query, perspective=q.perspective, topic=q.topic,
            ))
    return hits, []


@pytest.fixture
def fake_search(monkeypatch):
    monkeypatch.setattr("ai_decision_arena.nodes.research.run_searches", fake_run_searches)
    return fake_run_searches


@pytest.fixture
def graph():
    from ai_decision_arena.graph import build_graph
    return build_graph(InMemorySaver())


@pytest.fixture
def base_state() -> dict:
    """A plausible state after intake + clarification, for node-level tests."""
    return {
        "thread_id": "t1", "mode": "full", "question": "A habit tracker app for students", "user_context": "",
        "project_name": "habit tracker app", "project_category": "mobile_app",
        "idea_summary": "The user wants a habit tracker app for students.", "project_profile": {}, "requested_features": {}, "constraints": {},
        "missing_information": [], "risk_flags": [], "withdrawn_risk_flags": [],
        "clarification_answers": {}, "assumptions": [], "clarification_round_count": 0,
        "research_retry_count": 0, "debate_round": 0, "research_focus": [], "unresolved_questions": [],
        "evidence": [], "evidence_gaps": [], "conflicting_claims": [], "research_queries": [],
        "rejected_sources": [], "perspective_summaries": {}, "active_seconds": 0.0,
    }
