"""Pydantic models: the data contract shared by all agents.

Why Pydantic? A TypedDict only *describes* a dict. Pydantic *validates* it:
wrong types, missing fields or out-of-range numbers raise a ValidationError
instead of silently flowing into the next agent.

Field descriptions matter: Claude fills these models through structured output,
and the descriptions become part of its instructions.

Rules for models Claude fills (LLM output schemas):
- List fields are REQUIRED (no default). With structured output Claude often omits optional
  fields, so a defaulted list can silently come back empty. Required + "empty list if none"
  forces an explicit answer.
- Size limits go in the DESCRIPTION (and Python trims), not in max_length: a max_length
  violation would trigger a costly retry.
- Cross-field rules live in @model_validator, so call_structured() can retry with feedback.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

# ---------------------------------------------------------------------------
# Fixed vocabularies (Literal = only these exact strings are allowed)
# ---------------------------------------------------------------------------

WorkflowStatus = Literal[
    "intake",
    "awaiting_clarification",
    "researching",
    "debating",
    "verifying",
    "reporting",
    "completed",
    "completed_with_uncertainty",
    "failed",
]

# The three lenses every answer is built from. Research, debate and the final report are
# organised per perspective, and the user always gets one best plan per perspective.
Perspective = Literal["research", "doctor", "patient"]
PERSPECTIVES: tuple[Perspective, ...] = ("research", "doctor", "patient")
PERSPECTIVE_LABELS: dict[str, str] = {
    "research": "Research perspective (papers, studies, systematic reviews)",
    "doctor": "Doctor perspective (clinical guidelines, hospital and medical-reference sites)",
    "patient": "Patient perspective (real-world experiences from forums, Reddit, reviews)",
}

SourceType = Literal[
    "research_paper",        # journals, PubMed, Cochrane, preprints
    "clinical_guideline",    # WHO, CDC, NICE, NHS, professional societies (ADA, AHA, ...)
    "medical_reference",     # Mayo Clinic, Cleveland Clinic, MedlinePlus, MSD Manuals, doctor-reviewed sites
    "patient_community",     # Reddit, patient forums, drug reviews written by patients
    "health_article",        # health news, blogs, general articles
    "other",
]

EvidenceStrength = Literal[
    "systematic_review_or_meta_analysis",
    "randomized_trial",
    "observational_study",
    "clinical_guideline",
    "expert_or_reference",   # textbook-style reference, doctor-reviewed article
    "anecdotal",             # one or a few personal reports
    "unknown",
]

VerificationStatus = Literal[
    "pending",               # not checked yet (set by Research)
    "verified",
    "partially_supported",
    "unsupported",
    "contradicted",
    "irrelevant",
    "unavailable",
]

JudgeDecision = Literal[
    "proceed",
    "request_more_research",
    "request_clarification",
    "insufficient_evidence",
]

Level = Literal["low", "medium", "high"]

ConditionCategory = Literal[
    "metabolic_endocrine",      # diabetes, thyroid, obesity
    "cardiovascular",           # hypertension, heart disease
    "respiratory",              # asthma, COPD
    "digestive",                # IBS, GERD, Crohn's
    "musculoskeletal",          # arthritis, back pain
    "neurological",             # migraine, epilepsy
    "mental_health",            # depression, anxiety
    "dermatological",           # eczema, acne, psoriasis
    "infectious",               # flu, hepatitis
    "autoimmune_allergic",      # lupus, allergies
    "reproductive_urinary",     # PCOS, kidney disease
    "cancer",
    "other",
]

EVIDENCE_ID_PATTERN = r"^ev_\d{3,}$"                       # ev_001, ev_002, ...
PLAN_ID_PATTERN = r"^(research|doctor|patient)_[a-c]$"     # research_a, doctor_b, patient_c


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

class NamedValue(BaseModel):
    """A name/value pair. Used instead of dict[str, str] because a fixed object shape
    works more reliably with structured output; the node converts the list to a dict."""

    name: str = Field(description='Short snake_case key, e.g. "age", "diagnosed_since", "medications", "fatigue".')
    value: str = Field(description="What the user said, kept close to their wording.")


class IntakeResult(BaseModel):
    """Output of the Intake node: the user's health concern, normalized. Nothing invented."""

    is_health_concern: bool = Field(
        description="False if the input is not about a health condition, symptom, treatment or recovery."
    )
    condition_name: str = Field(
        description='The condition as the user frames it, lowercase, e.g. "diabetes", "type 2 diabetes", '
                    '"migraine". If only symptoms were given, describe them briefly, '
                    'e.g. "recurring morning headaches (undiagnosed)".'
    )
    condition_category: ConditionCategory
    case_summary: str = Field(description="One or two neutral sentences restating the user's situation. Do not add facts.")
    health_profile: list[NamedValue] = Field(
        description="Facts the user EXPLICITLY stated about themselves: age, sex, when diagnosed, current "
                    "medications, other conditions, lifestyle, goals. Never guess. Empty list if none.",
    )
    symptoms: list[NamedValue] = Field(
        description="Symptoms the user EXPLICITLY mentioned: symptom -> details (when, how often, how bad). "
                    "Empty list if none.",
    )
    constraints: list[NamedValue] = Field(
        description="Limits the user EXPLICITLY stated: allergies, dietary restrictions (vegetarian, halal...), "
                    "budget, country, preferences such as 'no injections'. Empty list if none.",
    )
    missing_information: list[str] = Field(
        description="Important unknowns that would change the guidance (type or stage, how long, current "
                    "treatment, other conditions, age group, goals). Most important first, at most 8.",
    )
    red_flags: list[str] = Field(
        description="Symptoms the user stated that may need urgent medical care (e.g. chest pain, confusion, "
                    "vomiting with very high blood sugar). Only what the user said. Empty list if none.",
    )


# ---------------------------------------------------------------------------
# Clarification
# ---------------------------------------------------------------------------

class WithdrawnRedFlag(BaseModel):
    flag: str = Field(description="The EXACT text of a flag listed in <red_flags>, copied character for character.")
    reason: str = Field(description='Which later answer of the user contradicts the flag, e.g. \'user answered "yes weekly" to insulin use\'.')


class ClarificationResult(BaseModel):
    """Output of the Clarification node: do we need to ask the user something?"""

    need_clarification: bool = Field(
        description="True if answers could materially change the guidance. In the FIRST round this is "
                    "normally true: ask the standard 5-6 questions that are not yet answered."
    )
    questions: list[str] = Field(
        description="The questions to ask, at most 6, one topic each. MUST be non-empty when "
                    "need_clarification is true; empty list otherwise.",
    )
    reason: str = Field(description="Why these questions matter, or why no questions are needed.")
    new_profile_facts: list[NamedValue] = Field(
        description="Profile facts newly confirmed by the user's answers (age, diagnosis, medications, goals...). "
                    "Empty list if none.",
    )
    new_symptoms: list[NamedValue] = Field(
        description="Symptoms newly confirmed by the user's answers: symptom -> details. Empty list if none.",
    )
    new_constraints: list[NamedValue] = Field(
        description="Constraints newly confirmed by the user's answers. Empty list if none.",
    )
    new_red_flags: list[str] = Field(
        description="Symptoms revealed by the answers that may need urgent care (e.g. possible DKA signs, chest pain, "
                    "confusion), stated as the user said them. Empty list if none.",
    )
    withdrawn_red_flags: list[WithdrawnRedFlag] = Field(
        description="Flags from <red_flags> whose FACTUAL PREMISE a later answer of the user directly contradicts "
                    "(e.g. flag 'no insulin reported', user now says 'yes weekly'). Never withdraw a flag because a "
                    "symptom seems mild or unlikely. When in doubt, keep it. Empty list if none.",
    )
    refined_condition_name: str = Field(
        description='The condition named more precisely because of the answers (e.g. "type 1 diabetes" instead of '
                    '"diabetes"), lowercase. Empty string if the answers do not make it more precise.',
    )
    refined_case_summary: str = Field(
        description="One or two neutral sentences restating the user's situation INCLUDING what the answers revealed. "
                    "Empty string if nothing material changed. Do not add facts.",
    )
    assumptions: list[str] = Field(
        description="When need_clarification is false: explicit assumptions for info that is still missing. "
                    "Empty list when asking.",
    )

    @model_validator(mode="after")
    def questions_match_decision(self) -> "ClarificationResult":
        # Raising here makes call_structured() retry with this message as feedback.
        if self.need_clarification and not self.questions:
            raise ValueError("need_clarification is true but questions is empty: provide the questions to ask.")
        return self


class ClarificationAnswers(BaseModel):
    """What the user sends back when the graph is paused for clarification."""

    answers: dict[str, str] = Field(description="question -> answer. An empty answer means 'skipped'.")


# ---------------------------------------------------------------------------
# Research evidence
# ---------------------------------------------------------------------------

# What each search is trying to learn. Every perspective covers the same topics.
ResearchTopic = Literal[
    "overview_prevalence",      # what the condition is, how common or rare, typical course
    "routine_lifestyle",        # daily routine, exercise, sleep, monitoring habits
    "diet",                     # what to eat / avoid
    "medications_treatment",    # medicines, therapies, procedures people use
    "progress_timeline",        # how long until improvement is typically seen
    "risks_warning_signs",      # complications, side effects, when to seek care
]


class PatientContext(BaseModel):
    """Extra detail for patient-community sources (Reddit, forums, reviews)."""

    experience_described: str = Field(description="The specific experience being reported.")
    is_recurring: bool = Field(description="True only if several independent people report it; False for one anecdote.")
    context: str = Field(description="Situation it happened in (age, how long diagnosed, treatments), if stated.")
    what_helped: list[str] = Field(default_factory=list)
    relevant_to_user: bool


class Evidence(BaseModel):
    """One structured piece of research. Never fabricated: every field comes from a retrieved source."""

    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    perspective: Perspective
    source_title: str
    source_url: HttpUrl
    source_type: SourceType
    evidence_strength: EvidenceStrength = "unknown"
    published_at: datetime | None = Field(default=None, description="Only if the source states it. Never guess.")
    retrieved_at: datetime = Field(default_factory=utc_now)
    relevant_excerpt: str = Field(max_length=2000, description="Short excerpt or faithful summary, not the whole page.")
    is_direct_quote: bool = Field(description="True if relevant_excerpt is copied verbatim, False if paraphrased.")
    claims_supported: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    patient_context: PatientContext | None = None
    sentiment: Literal["positive", "negative", "mixed", "neutral"] | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    reliability_notes: str = ""
    verification_status: VerificationStatus = "pending"


class SearchQuery(BaseModel):
    query: str = Field(description="Short web search query (keywords, not a full sentence), under 300 characters.")
    perspective: Perspective = Field(description="Which perspective this search serves.")
    topic: ResearchTopic
    preferred_domains: list[str] = Field(
        description='Condition-specific official domains to prefer, e.g. ["diabetes.org"]. At most 3, only '
                    'well-known organisations you are confident about; empty list if unsure. '
                    'General medical sites are added automatically.',
    )


class ResearchPlan(BaseModel):
    """Output of query planning (LLM): searches for all three perspectives."""

    search_term: str = Field(description='The condition as a search term, e.g. "type 2 diabetes".')
    queries: list[SearchQuery] = Field(min_length=3, description="Grouped by perspective, most important topic first.")

    @model_validator(mode="after")
    def every_perspective_covered(self) -> "ResearchPlan":
        present = {q.perspective for q in self.queries}
        missing = [p for p in PERSPECTIVES if p not in present]
        if missing:
            raise ValueError(f"queries must cover every perspective; missing: {missing}")
        return self


class SearchHit(BaseModel):
    """One raw-ish Tavily result, before Claude turns it into Evidence. Snippet only, never the full page."""

    url: str
    title: str
    snippet: str = Field(max_length=2000)
    tavily_score: float
    published_at: str | None = None    # only if Tavily returned one
    source_type: SourceType            # from the domain heuristic; may be corrected later
    query: str
    perspective: Perspective
    topic: ResearchTopic


class SearchFailure(BaseModel):
    query: str
    perspective: Perspective
    error_type: str
    message: str = Field(max_length=300)
    retryable: bool


class ExtractedEvidence(BaseModel):
    """LLM output for one KEPT source. URL/title/date are NOT here: Python copies them from
    the real search hit via source_index, so Claude cannot invent or alter a source."""

    source_index: int = Field(ge=0, description="Index of the <source> this evidence comes from.")
    perspective: Perspective = Field(
        description="Normally the perspective given. Change it only if the source clearly belongs elsewhere "
                    "(e.g. a forum thread found by a clinical search is 'patient')."
    )
    source_type: SourceType = Field(description="Correct the given type if it is wrong.")
    evidence_strength: EvidenceStrength = Field(description="Best guess from the snippet; 'unknown' if unclear.")
    relevant_excerpt: str = Field(description="Verbatim quote from the snippet, or a faithful paraphrase. At most ~400 characters.")
    is_direct_quote: bool = Field(description="True only if relevant_excerpt is copied word-for-word from the snippet.")
    claims_supported: list[str] = Field(description="At most 3 short claims THIS snippet itself supports. No outside knowledge.")
    limitations: list[str] = Field(description="At most 3 short limitations stated in the snippet. Empty list if none.")
    patient_context: PatientContext | None = Field(description="Required for patient_community sources; null otherwise.")
    sentiment: Literal["positive", "negative", "mixed", "neutral"] | None = Field(
        description="Tone toward the approach discussed, for patient sources; null otherwise."
    )
    relevance_score: float = Field(ge=0.0, le=1.0, description="How useful for THIS user's situation.")
    reliability_notes: str = Field(description="ONE short sentence: study type, sample size, vendor bias, age, anecdote...")


class RejectedSource(BaseModel):
    source_index: int = Field(ge=0)
    reason: str = Field(description='A few words, e.g. "irrelevant", "supplement marketing", "about type 1, user has type 2".')


class ExtractedConflict(BaseModel):
    topic: str
    source_indexes: list[int] = Field(min_length=2)
    description: str


class ExtractionResult(BaseModel):
    """LLM output of evidence extraction over the search hits of ONE perspective."""

    evidence: list[ExtractedEvidence] = Field(description="Kept sources only.")
    rejected: list[RejectedSource] = Field(description="Every source not kept, with a reason.")
    summary: str = Field(
        description="Neutral summary of what the kept sources say about routine, diet, medications, "
                    "timeline and outlook, at most ~150 words."
    )
    prevalence_note: str = Field(
        description="How common or rare the condition is according to the kept sources, one sentence. "
                    "'Not covered by these sources' if none say."
    )
    evidence_gaps: list[str] = Field(description="Topics (routine, diet, medications, timeline, prevalence) no kept source covers. Empty list if none.")
    conflicting_claims: list[ExtractedConflict] = Field(description="Where kept sources disagree. Empty list if none.")


class ConflictingClaim(BaseModel):
    """Two or more evidence records that disagree."""

    topic: str
    evidence_ids: list[str] = Field(min_length=2)
    description: str


# ---------------------------------------------------------------------------
# Debate: Proposer → Critic → Judge (each works per perspective)
# ---------------------------------------------------------------------------

class ProposedPlan(BaseModel):
    """LLM output: one way of managing the condition, built from ONE perspective's evidence.
    plan_id and perspective are assigned by Python afterwards (see CarePlan)."""

    name: str = Field(description='Short descriptive name, e.g. "Low-carb diet with daily walking and metformin".')
    summary: str = Field(description="What this approach is and how it addresses the user's situation, 2-3 sentences.")
    daily_routine: list[str] = Field(description="Concrete routine elements reported in the evidence (exercise, monitoring, sleep...).")
    diet: list[str] = Field(description="Dietary guidance reported in the evidence. Respect the user's constraints.")
    medications_treatments: list[str] = Field(
        description="Medicines/therapies AS REPORTED in the evidence, labelled 'commonly prescribed', 'reported by "
                    "patients', etc. Never invent doses. Empty list if the evidence names none."
    )
    expected_timeline: str = Field(description="How long until progress is typically seen, per the evidence; 'not covered by evidence' if unknown.")
    prevalence_and_outlook: str = Field(description="Is the condition common or rare, and the general outlook, per this perspective's evidence.")
    benefits: list[str]
    drawbacks_risks: list[str]
    assumptions: list[str] = Field(description="Things assumed about the user because they were not stated.")
    difficulty: Level = Field(description="How hard this plan is to follow day to day.")
    safety_notes: str = Field(description="Interactions, who should avoid it, when to see a doctor. Never advise stopping prescribed medication.")
    supporting_evidence_ids: list[str] = Field(description="ONLY ids from the evidence given, e.g. ['ev_003'].")
    evidence_gaps: list[str] = Field(description="What this plan relies on that the evidence does not cover. Empty list if none.")


class ProposerOutput(BaseModel):
    """LLM output of the Proposer for ONE perspective."""

    plans: list[ProposedPlan] = Field(
        description="2-3 meaningfully different plans. Only 1 if the evidence genuinely supports a single approach. "
                    "Empty list if the evidence is too thin to build any plan."
    )
    why_fewer_than_two: str = Field(description="Explanation when fewer than 2 plans are returned; empty string otherwise.")
    evidence_too_thin: bool = Field(
        description="True if you returned fewer than 2 plans BECAUSE the evidence is insufficient (a follow-up search "
                    "could help). False if the evidence is fine but the situation allows only one safe approach, or none "
                    "(e.g. an emergency that needs care before any plan)."
    )


class CarePlan(ProposedPlan):
    """A proposal as stored in state: ProposedPlan + identity assigned by Python."""

    plan_id: str = Field(pattern=PLAN_ID_PATTERN)
    perspective: Perspective
    round: int = Field(ge=1, description="Debate round that produced this plan.")


CriticismCategory = Literal[
    "safety_risk",
    "unsupported_claim",
    "contradicts_evidence",
    "anecdotal_only",
    "outdated_guidance",
    "not_fit_for_user",            # ignores the user's profile, symptoms or constraints
    "missing_consideration",
    "hard_to_follow",
    "interaction_or_contraindication",
    "better_alternative",
]


class CriticismPoint(BaseModel):
    category: CriticismCategory
    issue: str
    severity: Level
    basis: Literal["evidence", "clinical_reasoning"] = Field(
        description="'evidence' only when backed by evidence_ids; otherwise 'clinical_reasoning'."
    )
    is_verified_problem: bool = Field(description="True = demonstrated problem, False = possible risk.")
    evidence_ids: list[str] = Field(description="Evidence ids that back this point. Empty list if none.")
    suggested_improvement: str = Field(description="Actionable fix for the plan, or empty string.")


class Criticism(BaseModel):
    """The Critic's assessment of ONE plan."""

    plan_id: str = Field(pattern=PLAN_ID_PATTERN)
    points: list[CriticismPoint] = Field(description="Meaningful weaknesses only, at most 6. Empty list if the plan is sound.")
    overall_assessment: str


class CriticOutput(BaseModel):
    """LLM output of the Critic for ONE perspective (all its plans)."""

    criticisms: list[Criticism] = Field(description="Exactly one entry per plan given.")


class CriterionScore(BaseModel):
    criterion: str = Field(description='Rubric key, e.g. "fit_to_user".')
    score: float = Field(ge=0, le=10)
    explanation: str


class PlanScore(BaseModel):
    """The Judge's scores for ONE plan. weighted_total is computed in Python, not by the LLM."""

    plan_id: str = Field(pattern=PLAN_ID_PATTERN)
    criterion_scores: list[CriterionScore] = Field(description="One entry per rubric criterion, in rubric order.")
    weighted_total: float | None = Field(default=None, ge=0, le=10)
    key_benefits: list[str]
    key_drawbacks: list[str]
    confidence: Level
    confidence_reason: str
    supporting_evidence_ids: list[str] = Field(description="Evidence ids the score relies on. Empty list if none.")
    remaining_risks: list[str] = Field(description="Open risks and assumptions. Empty list if none.")


def expected_rubric_criteria() -> set[str]:
    # Imported lazily: config loads .env, and schemas should stay importable without it.
    from ai_decision_arena.config import get_settings

    return set(get_settings().rubric_weights)


class PerspectiveJudgement(BaseModel):
    """LLM output of the Judge for ONE perspective. The routing decision is made in Python
    by combining the three perspectives (see nodes/judge.py).

    `reasoning` is the FIRST field on purpose (chain of thought): structured output is written in field order,
    so Claude thinks the plans through before it commits to any score."""

    reasoning: str = Field(description="Think step by step BEFORE scoring, 3-6 short sentences: for each plan its main "
                                       "strength, its main weakness (Critic points, evidence), and how it fits this user.")
    scores: list[PlanScore] = Field(description="One entry per plan given.")
    comparison: str = Field(description="Why the plans rank the way they do, 2-4 sentences.")
    evidence_sufficient: bool = Field(
        description="True if this perspective's evidence supports a defensible best plan for THIS user."
    )
    insufficiency_reason: str = Field(description="Why the evidence is insufficient; empty string if sufficient.")
    required_evidence: list[str] = Field(description="What a follow-up search should look for. Empty list if sufficient.")
    clarification_questions: list[str] = Field(
        description="Questions for the USER whose answers would change the ranking. Empty list if none."
    )

    @model_validator(mode="after")
    def scores_are_complete(self) -> "PerspectiveJudgement":
        ids = [s.plan_id for s in self.scores]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate plan_id in scores: {ids}")
        expected = expected_rubric_criteria()
        for s in self.scores:
            got = [c.criterion for c in s.criterion_scores]
            if sorted(got) != sorted(expected):
                raise ValueError(
                    f"{s.plan_id}: criterion_scores must contain exactly these criteria once each: "
                    f"{sorted(expected)}; got {got}"
                )
        if not self.evidence_sufficient and not self.insufficiency_reason.strip():
            raise ValueError("evidence_sufficient is false but insufficiency_reason is empty.")
        return self


class Verdict(BaseModel):
    """The Judge's routing decision, assembled in Python from the three PerspectiveJudgements.
    Drives the conditional edge after the Judge node."""

    decision: JudgeDecision
    reason: str
    winning_plan_ids: dict[str, str] = Field(
        default_factory=dict, description="perspective -> plan_id with the highest weighted_total."
    )
    perspective_status: dict[str, str] = Field(
        default_factory=dict,
        description="perspective -> 'sufficient' | 'insufficient' | 'no_plans' (nothing to judge, research may help) "
                    "| 'declined' (Proposer deliberately returned no plan, e.g. emergency; research will not help).",
    )
    required_evidence: list[str] = Field(default_factory=list, description="What Research should look for next.")
    clarification_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verification, report, errors (Phase 6)
# ---------------------------------------------------------------------------

CheckedStatus = Literal["verified", "partially_supported", "unsupported", "contradicted", "irrelevant", "unavailable"]


class ClaimCheck(BaseModel):
    """LLM output: one factual claim of a plan, checked against the evidence it cites."""

    claim: str = Field(description="The claim as the plan states it, shortened if long.")
    evidence_ids: list[str] = Field(description="Ids the plan cites for this claim. Empty list if it cites none.")
    status: CheckedStatus
    notes: str = Field(description="One sentence: what the cited excerpt actually says, and why this status.")
    is_anecdotal: bool = Field(description="True if the only support is individual patient reports.")
    is_material: bool = Field(description="True if the plan's core guidance would change were this claim wrong.")


class PlanVerification(BaseModel):
    """LLM output of the Evidence Checker for ONE plan."""

    claims: list[ClaimCheck] = Field(description="Checkable factual claims, most important first, at most 10.")
    overall: str = Field(description="Two sentences: how well the plan is supported by its evidence.")
    material_gaps: list[str] = Field(
        description="For each MATERIAL claim that is unsupported, contradicted or unavailable: what a follow-up "
                    "search should look for. Empty list if none."
    )

    @model_validator(mode="after")
    def gaps_match_failures(self) -> "PlanVerification":
        failing = [c for c in self.claims if c.is_material and c.status in ("unsupported", "contradicted", "unavailable")]
        if failing and not self.material_gaps:
            raise ValueError("material claims failed verification but material_gaps is empty: say what a follow-up search should find.")
        return self


class ClaimVerification(BaseModel):
    """Evidence Checker result for one factual claim, as stored in state."""

    claim: str
    plan_id: str | None = None
    perspective: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    status: VerificationStatus
    notes: str = Field(description="Why this status. For rejected evidence, the reason it was rejected.")
    is_anecdotal: bool = False
    is_material: bool = False


class EvidenceRef(BaseModel):
    evidence_id: str
    title: str
    url: HttpUrl
    verification_status: VerificationStatus


class PerspectiveResult(BaseModel):
    """One of the three answers the user receives: the best plan of a perspective."""

    perspective: Perspective
    plan: CarePlan | None = Field(description="None when the perspective produced no defensible plan.")
    score: PlanScore | None = None
    key_evidence: list[EvidenceRef] = Field(default_factory=list)
    critic_key_objections: list[str] = Field(default_factory=list)
    verification_counts: dict[str, int] = Field(default_factory=dict, description="status -> number of claims")
    verification_notes: list[str] = Field(default_factory=list)
    unavailable_reason: str = Field(default="", description="Why there is no plan, when plan is None.")


class ReportNarrative(BaseModel):
    """LLM output: the human-readable parts of the final report. Everything else is assembled in Python."""

    overview: str = Field(description="4-6 plain-language sentences for the user: what the three perspectives say, "
                                      "where they agree, the main caveat. No new facts.")
    where_perspectives_agree: list[str] = Field(description="Points the research, doctor and patient plans share. Empty list if none.")
    where_perspectives_differ: list[str] = Field(description="Where they differ or disagree, and why. Empty list if none.")
    key_uncertainties: list[str] = Field(description="What remains unknown or weakly supported, at most 6.")
    next_steps: list[str] = Field(description="Questions to bring to a doctor and things to monitor, at most 6. Never prescribe.")


class OnboardingSummary(BaseModel):
    """LLM output, patient chat only: the short message that ends onboarding and opens the chat."""

    opening: str = Field(description="One warm sentence in the second person saying you now understand their health "
                                     "situation; name the condition and one personal detail they shared.")
    doctors_say: str = Field(description="Markdown bullet list, 3-7 bullets plus sub-bullets for examples: the concrete "
                                         "advice a doctor would give this patient (what, how much, how often, what to "
                                         "track). Empty string if there is no doctor plan.")
    patients_say: str = Field(description="Markdown bullet list, 3-7 bullets plus sub-bullets for examples: the concrete "
                                          "things other people with this condition do (specific foods, times, amounts, "
                                          "habits). Empty string if there is no patient plan.")
    research_says: str = Field(description="Markdown bullet list, 3-7 bullets plus sub-bullets for examples: specific "
                                           "findings of studies (what was tried, how much, what changed), in plain "
                                           "words. Empty string if there is no research plan.")
    invitation: str = Field(description="One sentence inviting them to talk about diet, daily routine, how they feel, "
                                        "medicines or doctor visits.")


class FinalReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    original_question: str
    condition_name: str
    confirmed_profile: dict[str, str]
    symptoms: dict[str, str]
    constraints: dict[str, str]
    clarifications: dict[str, str]
    assumptions: list[str] = Field(default_factory=list)
    research_methodology: str
    overview: str
    perspectives: list[PerspectiveResult] = Field(description="Research, doctor and patient results, in that order.")
    where_perspectives_agree: list[str]
    where_perspectives_differ: list[str]
    is_conditional: bool = Field(description="True if the guidance depends on unconfirmed assumptions or unverified claims.")
    uncertainties: list[str]
    unsupported_claims: list[str]
    unresolved_questions: list[str]
    next_steps: list[str] = Field(description="E.g. questions to bring to a doctor, what to monitor.")
    red_flags: list[str]
    withdrawn_red_flags: list[str] = Field(default_factory=list, description='"flag (reason)" for flags later answers contradicted.')
    disclaimer: str


class ErrorRecord(BaseModel):
    """Safe error info. Never put API keys or full request payloads here."""

    node: str
    operation: str
    category: Literal["llm_unavailable", "database", "invalid_input", "unknown"]
    message: str = Field(max_length=500, description="Shown to the user, e.g. the Claude API error of each model.")
    occurred_at: datetime = Field(default_factory=utc_now)
