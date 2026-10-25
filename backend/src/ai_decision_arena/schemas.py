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
    "writing_brief",
    "validating_brief",
    "awaiting_brief_review",
    "planning",
    "awaiting_plan_review",
    "implementing",
    "completed",
    "completed_with_uncertainty",
    "failed",
]

# The three research domains every solution is built from. Research runs one lane per domain in parallel; the
# proposals, the critique and the brief may cite evidence from any domain.
Domain = Literal["apps", "papers", "tech"]
DOMAINS: tuple[Domain, ...] = ("apps", "papers", "tech")
DOMAIN_LABELS: dict[str, str] = {
    "apps": "Existing apps and user feedback (reviews, app stores, forums, product documentation)",
    "papers": "Research papers and technical literature (arXiv, ACM, IEEE, journals, authoritative reports)",
    "tech": "Technical feasibility and implementations (repositories, libraries, frameworks, APIs, official docs)",
}

SourceType = Literal[
    "review_site",           # G2, Capterra, Trustpilot, Product Hunt, AlternativeTo
    "app_store",             # Apple App Store, Google Play, extension stores
    "community_discussion",  # Reddit, Hacker News, Stack Overflow, forums, GitHub discussions
    "product_docs",          # a product's own help centre, pricing or feature pages
    "research_paper",        # arXiv, ACM, IEEE, Springer, journals, preprints
    "technical_docs",        # MDN, framework / library / API documentation, cloud docs
    "source_repository",     # GitHub, GitLab, npm, PyPI, Hugging Face
    "article_or_blog",       # Medium, dev.to, company blogs, tech news
    "other",
]

EvidenceStrength = Literal[
    "peer_reviewed",            # published paper, survey, conference proceedings
    "official_documentation",   # vendor / maintainer documentation, standards
    "maintained_repository",    # active open-source project with real usage
    "aggregated_reviews",       # many user reviews or ratings summarised
    "expert_article",           # practitioner write-up with checkable detail
    "anecdotal",                # one or a few individual reports
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

ProjectCategory = Literal[
    "web_app",          # browser application with accounts / data (dashboards, tools, marketplaces)
    "website",          # mostly content: landing page, portfolio, small business site, blog
    "mobile_app",       # iOS / Android
    "saas",             # subscription product for many customers
    "internal_tool",    # for one team or company
    "api_service",      # backend / API without its own UI
    "ai_agent",         # chatbot, assistant, automation driven by an LLM
    "game",
    "other",
]

EVIDENCE_ID_PATTERN = r"^ev_\d{3,}$"                       # ev_001, ev_002, ...
PROPOSAL_ID_PATTERN = r"^proposal_[a-c]$"                # proposal_a, proposal_b, proposal_c


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
    """Output of the Intake node: the user's app or website idea, normalized. Nothing invented."""

    is_app_request: bool = Field(
        description="False if the input does not describe something to build (an app, website, tool, service, game, "
                    "automation or API): e.g. a general question, small talk, or a request for advice."
    )
    project_name: str = Field(
        description='A short working name taken from the user\'s words, lowercase, e.g. "habit tracker app", '
                    '"bakery website with online orders". Never invent a brand name.'
    )
    project_category: ProjectCategory
    idea_summary: str = Field(description="One or two neutral sentences restating what the user wants to build and for "
                                          "whom. Do not add features or goals they did not mention.")
    project_profile: list[NamedValue] = Field(
        description="Facts the user EXPLICITLY stated about the project: target audience, platform, timeline, budget, "
                    "team, existing assets, business model. Never guess. Empty list if none.",
    )
    requested_features: list[NamedValue] = Field(
        description="Features or capabilities the user EXPLICITLY asked for: feature -> the details they gave. "
                    "Empty list if none.",
    )
    constraints: list[NamedValue] = Field(
        description="Limits the user EXPLICITLY stated: technology preferences, hosting, budget, deadline, compliance, "
                    "integrations that must be used, things to avoid. Empty list if none.",
    )
    missing_information: list[str] = Field(
        description="Important unknowns that would change the solution (who the users are, the problem they face today, "
                    "must-have features, platform, constraints, what success looks like). Most important first, at most 8.",
    )
    risk_flags: list[str] = Field(
        description="Aspects the user stated that carry legal, safety, privacy or compliance risk (payments, health or "
                    "financial data, minors, scraping, user-generated content, regulated domains). Only what the user "
                    "said. Empty list if none.",
    )


# ---------------------------------------------------------------------------
# Clarification
# ---------------------------------------------------------------------------

class WithdrawnRiskFlag(BaseModel):
    flag: str = Field(description="The EXACT text of a flag listed in <risk_flags>, copied character for character.")
    reason: str = Field(description='Which later answer of the user contradicts the flag, e.g. \'user answered "no personal data is stored"\'.')


class ClarificationResult(BaseModel):
    """Output of the Clarification node: do we need to ask the user something?"""

    need_clarification: bool = Field(
        description="True if answers could materially change the research or the solution. In the FIRST round this is "
                    "normally true: ask the standard 4-6 questions that are not yet answered."
    )
    questions: list[str] = Field(
        description="The questions to ask, at most 6, one topic each, specific to this idea. MUST be non-empty when "
                    "need_clarification is true; empty list otherwise.",
    )
    reason: str = Field(description="Why these questions matter, or why no questions are needed.")
    new_profile_facts: list[NamedValue] = Field(
        description="Project facts newly confirmed by the user's answers (audience, platform, timeline, budget, team, "
                    "business model...). Empty list if none.",
    )
    new_features: list[NamedValue] = Field(
        description="Features newly requested or confirmed by the user's answers: feature -> details. Empty list if none.",
    )
    new_constraints: list[NamedValue] = Field(
        description="Constraints newly confirmed by the user's answers. Empty list if none.",
    )
    new_risk_flags: list[str] = Field(
        description="Risky aspects revealed by the answers (payments, personal or health data, minors, scraping, "
                    "regulated domains), stated as the user said them. Empty list if none.",
    )
    withdrawn_risk_flags: list[WithdrawnRiskFlag] = Field(
        description="Flags from <risk_flags> whose FACTUAL PREMISE a later answer of the user directly contradicts. "
                    "When in doubt, keep the flag. Empty list if none.",
    )
    refined_project_name: str = Field(
        description='The project named more precisely because of the answers (e.g. "habit tracker app for students" '
                    'instead of "habit app"), lowercase. Empty string if the answers do not make it more precise.',
    )
    refined_idea_summary: str = Field(
        description="One or two neutral sentences restating the idea INCLUDING what the answers revealed. "
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

# What each search is trying to learn. Every topic belongs to ONE domain (TOPICS_BY_DOMAIN); the key topic of a
# domain is always searched on the first pass.
ResearchTopic = Literal[
    # apps: existing applications and user feedback
    "existing_solutions",        # which products solve this today, for whom
    "user_complaints",           # what users dislike, missing features, limitations
    "must_have_features",        # what users expect any solution to have
    "pricing_and_adoption",      # business models, pricing, who uses it
    # papers: research papers and technical literature
    "problem_background",        # the underlying problem, its causes and measurements
    "established_approaches",    # methods and designs shown to work
    "known_limitations",         # where approaches fail, open questions
    # tech: feasibility and existing implementations
    "libraries_and_frameworks",  # reusable components, SDKs, starter kits
    "apis_and_integrations",     # third-party services, data sources, auth, payments
    "architecture_patterns",     # reference architectures and trade-offs
    "feasibility_and_risks",     # technical limits, costs, dependencies, security
]
TOPICS_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "apps": ("existing_solutions", "user_complaints", "must_have_features", "pricing_and_adoption"),
    "papers": ("problem_background", "established_approaches", "known_limitations"),
    "tech": ("libraries_and_frameworks", "apis_and_integrations", "architecture_patterns", "feasibility_and_risks"),
}
KEY_TOPIC: dict[str, str] = {"apps": "user_complaints", "papers": "established_approaches", "tech": "feasibility_and_risks"}


class FeedbackContext(BaseModel):
    """Extra detail for review, app-store and community sources: what a user of an existing product reported."""

    product: str = Field(description="The product or app the feedback is about, as named in the source; empty if unnamed.")
    feedback_type: Literal["complaint", "praise", "feature_request", "workaround", "mixed"]
    experience_described: str = Field(description="The specific experience being reported.")
    is_recurring: bool = Field(description="True only if several independent people report it; False for one anecdote.")
    context: str = Field(description="Situation it happened in (platform, plan, use case), if stated.")
    relevant_to_idea: bool


class Evidence(BaseModel):
    """One structured piece of research. Never fabricated: every field comes from a retrieved source."""

    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    domain: Domain
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
    feedback_context: FeedbackContext | None = None
    sentiment: Literal["positive", "negative", "mixed", "neutral"] | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    reliability_notes: str = ""
    verification_status: VerificationStatus = "pending"


class SearchQuery(BaseModel):
    query: str = Field(description="Short web search query (keywords, not a full sentence), under 300 characters.")
    domain: Domain = Field(description="Which research domain this search serves.")
    topic: ResearchTopic = Field(description="Must be one of the topics of that domain.")
    preferred_domains: list[str] = Field(
        description='Well-known websites specific to this idea worth preferring, e.g. ["producthunt.com"]. At most 3, '
                    'only sites you are confident about; empty list if unsure. The standard sites of each domain are '
                    'added automatically.',
    )

    @model_validator(mode="after")
    def topic_belongs_to_domain(self) -> "SearchQuery":
        allowed = TOPICS_BY_DOMAIN[self.domain]
        if self.topic not in allowed:
            raise ValueError(f"topic {self.topic!r} is not a {self.domain!r} topic; use one of {list(allowed)}")
        return self


class ResearchPlan(BaseModel):
    """Output of query planning (LLM): searches for all three domains."""

    search_term: str = Field(description='The condition as a search term, e.g. "type 2 diabetes".')
    queries: list[SearchQuery] = Field(min_length=3, description="Grouped by domain, most important topic first.")

    @model_validator(mode="after")
    def every_perspective_covered(self) -> "ResearchPlan":
        present = {q.domain for q in self.queries}
        missing = [p for p in DOMAINS if p not in present]
        if missing:
            raise ValueError(f"queries must cover every domain; missing: {missing}")
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
    domain: Domain
    topic: ResearchTopic


class SearchFailure(BaseModel):
    query: str
    domain: Domain
    error_type: str
    message: str = Field(max_length=300)
    retryable: bool


class ExtractedEvidence(BaseModel):
    """LLM output for one KEPT source. URL/title/date are NOT here: Python copies them from
    the real search hit via source_index, so Claude cannot invent or alter a source."""

    source_index: int = Field(ge=0, description="Index of the <source> this evidence comes from.")
    domain: Domain = Field(
        description="Normally the domain given. Change it only if the source clearly belongs elsewhere "
                    "(e.g. a GitHub repository found by an apps search is 'tech'; a forum thread about a product is 'apps')."
    )
    source_type: SourceType = Field(description="Correct the given type if it is wrong.")
    evidence_strength: EvidenceStrength = Field(description="Best guess from the snippet; 'unknown' if unclear.")
    relevant_excerpt: str = Field(description="Verbatim quote from the snippet, or a faithful paraphrase. At most ~400 characters.")
    is_direct_quote: bool = Field(description="True only if relevant_excerpt is copied word-for-word from the snippet.")
    claims_supported: list[str] = Field(description="At most 3 short claims THIS snippet itself supports. No outside knowledge.")
    limitations: list[str] = Field(description="At most 3 short limitations stated in the snippet. Empty list if none.")
    feedback_context: FeedbackContext | None = Field(description="Required for review_site, app_store and community_discussion "
                                                                 "sources that report a user's experience; null otherwise.")
    sentiment: Literal["positive", "negative", "mixed", "neutral"] | None = Field(
        description="Tone of the feedback, for review / app-store / community sources; null otherwise."
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
    """LLM output of evidence extraction over the search hits of ONE domain."""

    evidence: list[ExtractedEvidence] = Field(description="Kept sources only.")
    rejected: list[RejectedSource] = Field(description="Every source not kept, with a reason.")
    summary: str = Field(
        description="Neutral summary of what the kept sources say about the problem, existing solutions and their "
                    "limitations, established approaches and technical feasibility, at most ~150 words."
    )
    opportunity_note: str = Field(
        description="One sentence: the clearest opportunity to do better than existing alternatives according to "
                    "the kept sources. 'Not covered by these sources' if none say."
    )
    evidence_gaps: list[str] = Field(description="Topics of this domain (see the topic list) that no kept source covers. Empty list if none.")
    conflicting_claims: list[ExtractedConflict] = Field(description="Where kept sources disagree. Empty list if none.")


class ConflictingClaim(BaseModel):
    """Two or more evidence records that disagree."""

    topic: str
    evidence_ids: list[str] = Field(min_length=2)
    description: str


# ---------------------------------------------------------------------------
# Debate: Proposer → Critic → Judge (2-3 solution proposals built from ALL the evidence)
# ---------------------------------------------------------------------------

class ArchitectureSketch(BaseModel):
    """High-level architecture of one proposal. Use "none" when a part is not needed."""

    frontend: str = Field(description='E.g. "Next.js web app", "React Native app", or "none" for an API-only service.')
    backend: str = Field(description='E.g. "FastAPI service", "serverless functions", "none (static site)".')
    database: str = Field(description='E.g. "PostgreSQL", "browser localStorage", "none".')
    external_services: list[str] = Field(description="Third-party APIs or services (payments, auth, email, maps...). Empty list if none.")
    ai_components: str = Field(description='LLM / ML parts only if the idea needs them, e.g. "none" or "Claude for summaries".')


class ProposedSolution(BaseModel):
    """LLM output: one way of building the user's idea, grounded in the evidence.
    proposal_id and round are assigned by Python afterwards (see SolutionProposal)."""

    name: str = Field(description='Short descriptive name, e.g. "Offline-first PWA calculator with history".')
    summary: str = Field(description="What this solution is and how it addresses the user's problem, 2-3 sentences.")
    problem_addressed: str = Field(description="The specific problem or gap it targets, from the user's requirements and the evidence.")
    target_users: str = Field(description="Who it is for, as the user and the evidence describe them.")
    core_features: list[str] = Field(description="Features essential for the first version (MVP), 3-8 items.")
    future_features: list[str] = Field(description="Enhancements that can wait. Empty list if none.")
    user_journey: list[str] = Field(description="The key steps a user takes, 3-7 items.")
    architecture: ArchitectureSketch
    technologies: list[str] = Field(description='Technology choices with a short reason each, e.g. "React (large ecosystem; user prefers it)".')
    how_it_beats_alternatives: str = Field(description="How it does better than the existing products in the evidence, naming the gaps it closes.")
    benefits: list[str]
    drawbacks_risks: list[str]
    assumptions: list[str] = Field(description="Things assumed about the user or the project because they were not stated.")
    difficulty: Level = Field(description="How hard the MVP is to build.")
    feasibility_notes: str = Field(description="Technical feasibility within the user's constraints: dependencies, limits, costs.")
    security_privacy_notes: str = Field(description="Data handled, auth, compliance; 'none needed' if nothing sensitive.")
    supporting_evidence_ids: list[str] = Field(description="ONLY ids from the evidence given, e.g. ['ev_003'].")
    evidence_gaps: list[str] = Field(description="What this solution relies on that the evidence does not cover. Empty list if none.")


class ProposerOutput(BaseModel):
    """LLM output of the Proposer: all proposals at once."""

    proposals: list[ProposedSolution] = Field(
        description="2-3 meaningfully different solutions. Only 1 if the requirements and evidence allow a single defensible "
                    "approach. Empty list if the evidence is too thin to propose anything."
    )
    why_fewer_than_two: str = Field(description="Explanation when fewer than 2 proposals are returned; empty string otherwise.")
    evidence_too_thin: bool = Field(
        description="True if you returned fewer than 2 proposals BECAUSE the evidence is insufficient (a follow-up search "
                    "could help). False if the evidence is fine but the requirements allow only one approach."
    )


class SolutionProposal(ProposedSolution):
    """A proposal as stored in state: ProposedSolution + identity assigned by Python."""

    proposal_id: str = Field(pattern=PROPOSAL_ID_PATTERN)
    round: int = Field(ge=1, description="Debate round that produced this proposal.")


CriticismCategory = Literal[
    "unsupported_claim",
    "contradicts_evidence",
    "copies_existing_app",          # no real improvement over the alternatives users complain about
    "missing_requirement",          # a user requirement is not covered
    "ignores_constraint",           # platform, budget, timeline, tech preference, compliance
    "infeasible",                   # cannot be built as described within the constraints
    "scope_too_large",              # the first version is too big to build and verify
    "security_privacy_risk",
    "weak_assumption",
    "better_alternative",
    "missing_consideration",
]


class CriticismPoint(BaseModel):
    category: CriticismCategory
    issue: str
    severity: Level
    basis: Literal["evidence", "engineering_judgement"] = Field(
        description="'evidence' only when backed by evidence_ids; otherwise 'engineering_judgement'."
    )
    is_verified_problem: bool = Field(description="True = demonstrated problem, False = possible risk.")
    evidence_ids: list[str] = Field(description="Evidence ids that back this point. Empty list if none.")
    suggested_improvement: str = Field(description="Actionable fix for the proposal, or empty string.")


class Criticism(BaseModel):
    """The Critic's assessment of ONE proposal (also the output schema of one Critic call)."""

    proposal_id: str = Field(pattern=PROPOSAL_ID_PATTERN)
    points: list[CriticismPoint] = Field(description="Meaningful weaknesses only, at most 6. Empty list if the proposal is sound.")
    overall_assessment: str


class CriterionScore(BaseModel):
    criterion: str = Field(description='Rubric key, e.g. "requirements_alignment".')
    score: float = Field(ge=0, le=10)
    explanation: str


class ProposalScore(BaseModel):
    """The Judge's scores for ONE proposal. weighted_total is computed in Python, not by the LLM."""

    proposal_id: str = Field(pattern=PROPOSAL_ID_PATTERN)
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


class DomainCoverage(BaseModel):
    domain: Domain
    status: Literal["sufficient", "insufficient", "no_evidence"]
    note: str = Field(description="One sentence: what this domain's evidence did or did not establish.")


class ProposalJudgement(BaseModel):
    """LLM output of the Judge: all proposals compared in ONE call. The winner and the routing decision are
    computed in Python (see nodes/judge.py).

    `reasoning` is the FIRST field on purpose (chain of thought): structured output is written in field order,
    so Claude thinks the proposals through before it commits to any score."""

    reasoning: str = Field(description="Think step by step BEFORE scoring, 3-8 short sentences: for each proposal its main "
                                       "strength, its main weakness (Critic points, evidence), and how it fits this user.")
    scores: list[ProposalScore] = Field(description="One entry per proposal given.")
    comparison: str = Field(description="Why the proposals rank the way they do, 2-4 sentences.")
    evidence_sufficient: bool = Field(description="True if the evidence lets you defend a best solution for THIS user.")
    insufficiency_reason: str = Field(description="Why the evidence is insufficient; empty string if sufficient.")
    required_evidence: list[str] = Field(description="What a follow-up search should look for. Empty list if sufficient.")
    domain_coverage: list[DomainCoverage] = Field(description="One entry per research domain (apps, papers, tech).")
    material_contradictions: list[str] = Field(
        description="Contradictions between the user's requirements, the proposals or the evidence that must be resolved "
                    "before planning. Empty list if none."
    )
    clarification_questions: list[str] = Field(
        description="Questions for the USER whose answers would change which proposal wins. At most 2; empty list if none."
    )

    @model_validator(mode="after")
    def scores_are_complete(self) -> "ProposalJudgement":
        ids = [s.proposal_id for s in self.scores]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate proposal_id in scores: {ids}")
        expected = expected_rubric_criteria()
        for s in self.scores:
            got = [c.criterion for c in s.criterion_scores]
            if sorted(got) != sorted(expected):
                raise ValueError(
                    f"{s.proposal_id}: criterion_scores must contain exactly these criteria once each: "
                    f"{sorted(expected)}; got {got}"
                )
        if not self.evidence_sufficient and not self.insufficiency_reason.strip():
            raise ValueError("evidence_sufficient is false but insufficiency_reason is empty.")
        return self


class Verdict(BaseModel):
    """The Judge's routing decision, assembled in Python. Drives the conditional edge after the Judge node."""

    decision: JudgeDecision
    reason: str
    winning_proposal_id: str | None = Field(default=None, description="The proposal with the highest weighted_total.")
    domain_status: dict[str, str] = Field(default_factory=dict, description="domain -> sufficient | insufficient | no_evidence")
    required_evidence: list[str] = Field(default_factory=list, description="What Research should look for next.")
    material_contradictions: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verification and the interim report (the problem brief replaces the report in M4)
# ---------------------------------------------------------------------------

CheckedStatus = Literal["verified", "partially_supported", "unsupported", "contradicted", "irrelevant", "unavailable"]


class ClaimCheck(BaseModel):
    """LLM output: one factual claim of a proposal, checked against the evidence it cites."""

    claim: str = Field(description="The claim as the proposal states it, shortened if long.")
    evidence_ids: list[str] = Field(description="Ids the proposal cites for this claim. Empty list if it cites none.")
    status: CheckedStatus
    notes: str = Field(description="One sentence: what the cited excerpt actually says, and why this status.")
    is_anecdotal: bool = Field(description="True if the only support is individual user reports.")
    is_material: bool = Field(description="True if the proposal's core design would change were this claim wrong.")


class ProposalVerification(BaseModel):
    """LLM output of the Evidence Checker for ONE proposal."""

    claims: list[ClaimCheck] = Field(description="Checkable factual claims, most important first, at most 10.")
    overall: str = Field(description="Two sentences: how well the proposal is supported by its evidence.")
    material_gaps: list[str] = Field(
        description="For each MATERIAL claim that is unsupported, contradicted or unavailable: what a follow-up "
                    "search should look for. Empty list if none."
    )

    @model_validator(mode="after")
    def gaps_match_failures(self) -> "ProposalVerification":
        failing = [c for c in self.claims if c.is_material and c.status in ("unsupported", "contradicted", "unavailable")]
        if failing and not self.material_gaps:
            raise ValueError("material claims failed verification but material_gaps is empty: say what a follow-up search should find.")
        return self


class ClaimVerification(BaseModel):
    """Evidence Checker result for one factual claim, as stored in state."""

    claim: str
    proposal_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    status: VerificationStatus
    notes: str = Field(description="Why this status.")
    is_anecdotal: bool = False
    is_material: bool = False


class EvidenceRef(BaseModel):
    evidence_id: str
    title: str
    url: HttpUrl
    verification_status: VerificationStatus


class ProposalResult(BaseModel):
    """One proposal as it appears in the report: the proposal plus what the Critic, Judge and Checker said about it."""

    proposal: SolutionProposal
    score: ProposalScore | None = None
    is_winner: bool = False
    key_evidence: list[EvidenceRef] = Field(default_factory=list)
    critic_key_objections: list[str] = Field(default_factory=list)
    verification_counts: dict[str, int] = Field(default_factory=dict, description="status -> number of claims")
    verification_notes: list[str] = Field(default_factory=list)


class ReportNarrative(BaseModel):
    """LLM output: the human-readable parts of the interim report. Everything else is assembled in Python."""

    overview: str = Field(description="4-6 plain-language sentences: the problem, the recommended solution, why, and the "
                                      "main caveat. No new facts, no numbers that are not in the input.")
    why_this_solution: list[str] = Field(description="Why the winner beats the alternatives, 2-5 points. Empty list if there is no winner.")
    key_uncertainties: list[str] = Field(description="What remains unknown or weakly supported, at most 6.")
    next_steps: list[str] = Field(description="What to confirm or decide before planning the build, at most 6.")


class FinalReport(BaseModel):
    """Interim report (M3): the debate's outcome. The problem statement + solution brief (M4) becomes the document
    the user reviews; the data assembled here feeds that brief."""

    generated_at: datetime = Field(default_factory=utc_now)
    original_question: str
    project_name: str
    confirmed_profile: dict[str, str]
    requested_features: dict[str, str]
    constraints: dict[str, str]
    clarifications: dict[str, str]
    assumptions: list[str] = Field(default_factory=list)
    research_methodology: str
    overview: str
    winner: ProposalResult | None = Field(description="None when no proposal could be defended.")
    alternatives: list[ProposalResult] = Field(default_factory=list)
    no_winner_reason: str = ""
    why_this_solution: list[str] = Field(default_factory=list)
    is_conditional: bool = Field(description="True if the recommendation depends on unconfirmed assumptions or unverified claims.")
    uncertainties: list[str]
    unsupported_claims: list[str]
    unresolved_questions: list[str]
    next_steps: list[str]
    risk_flags: list[str]
    withdrawn_risk_flags: list[str] = Field(default_factory=list, description='"flag (reason)" for flags later answers contradicted.')
    disclaimer: str


# ---------------------------------------------------------------------------
# Problem statement + solution brief (spec §4) and its validation (spec §5)
# ---------------------------------------------------------------------------

# Every statement in the brief says where it comes from. Python downgrades "verified" when none of the cited
# evidence was verified by the Evidence Checker; "verified" / "research_backed" must cite evidence.
ClaimLabel = Literal[
    "verified",          # backed by evidence the Evidence Checker verified
    "research_backed",   # backed by retrieved evidence (not individually verified)
    "user_provided",     # the user said it (question, answers, constraints)
    "recommendation",    # the agents' recommendation
    "assumption",        # assumed because it is unknown
]
CITED_LABELS = ("verified", "research_backed")


class BriefItem(BaseModel):
    """One labelled statement of the brief."""

    text: str = Field(description="One sentence, at most ~20 words. No URLs, no evidence ids in the text.")
    label: ClaimLabel
    evidence_ids: list[str] = Field(description="Ids from <evidence> that support it; REQUIRED for verified / research_backed. "
                                                "Empty list if none.")


class ProjectOverview(BaseModel):
    """§4.1"""

    proposed_name: str = Field(description="A name only if the user gave one or a plain descriptive one fits; empty string otherwise. "
                                           "Never invent a brand.")
    description: str = Field(description="What the project is, 1-2 sentences.")
    audience: list[BriefItem] = Field(description="Intended users, stakeholders and target audience, 1-3 items.")
    context: BriefItem = Field(description="The domain and context in which the problem occurs.")


class ProblemStatement(BaseModel):
    """§4.2: specific, concise and SOLUTION-NEUTRAL (no feature or technology named as the answer)."""

    statement: BriefItem = Field(description="The specific problem or unmet need, 1-2 sentences, solution-neutral.")
    who_and_context: BriefItem = Field(description="Who experiences it and in what situation.")
    current_alternatives: list[BriefItem] = Field(description="How users handle it today / existing alternatives, 1-3 items.")
    gap: BriefItem = Field(description="The gap between the current situation and the desired outcome.")
    consequences: list[BriefItem] = Field(description="Practical consequences of leaving it unresolved, 1-2 items.")
    indicators: list[BriefItem] = Field(description="Supporting evidence or measurable indicators, only from the evidence. Empty list if none.")


class ResearchFindings(BaseModel):
    """§4.3"""

    apps_and_feedback: list[BriefItem] = Field(description="Findings from existing apps and user feedback, 1-3 items.")
    papers_and_literature: list[BriefItem] = Field(description="Findings from papers and technical literature, 0-3 items "
                                                               "(empty list if the evidence has none).")
    feasibility_and_implementations: list[BriefItem] = Field(description="Findings from feasibility, open-source and docs, 1-3 items.")
    limitations_and_opportunity: list[BriefItem] = Field(description="Limitations of existing solutions and the opportunity, 1-3 items.")
    evidence_gaps: list[str] = Field(description="What the research could NOT establish, short phrases. Empty list if none.")


class ProposedSolutionSection(BaseModel):
    """§4.4"""

    how_it_addresses_problem: BriefItem = Field(description="How the recommended app addresses the problem, 1-2 sentences.")
    mvp_features: list[str] = Field(description="Essential first-version features (main user-facing capabilities), 3-8 short items.")
    future_enhancements: list[str] = Field(description="Features that can wait. Empty list if none.")
    user_journey: list[str] = Field(description="Key steps of the main workflow, 3-6 short steps.")
    why_this_approach: list[BriefItem] = Field(description="Why it beats the alternatives considered (name them), 1-3 items.")


class NonFunctionalRequirement(BriefItem):
    category: Literal["performance", "security", "privacy", "reliability", "accessibility", "scalability", "usability",
                      "maintainability", "compliance", "other"]


class Requirements(BaseModel):
    """§4.5"""

    functional: list[BriefItem] = Field(description="What the system must do, 3-8 items.")
    non_functional: list[NonFunctionalRequirement] = Field(description="Relevant quality requirements, 2-6 items.")
    integrations_and_data: list[str] = Field(description="Integrations, data inputs and outputs. Empty list if none.")
    user_roles: list[str] = Field(description="User roles where applicable. Empty list if a single anonymous role.")
    acceptance_criteria: list[str] = Field(description="Testable acceptance criteria for the critical requirements "
                                                       "(Given/When/Then or a checkable statement), 0-5 items.")


class Component(BaseModel):
    name: str = Field(description='E.g. "Frontend", "Backend API", "Database", "Payments (Stripe)".')
    responsibility: str = Field(description="What it is responsible for, one sentence.")


class TechnologyChoice(BaseModel):
    name: str
    purpose: str = Field(description="What it is used for and why, one short sentence.")
    label: ClaimLabel = Field(description="user_provided ONLY if the user asked for it; otherwise research_backed / "
                                          "verified (with evidence) or recommendation.")
    evidence_ids: list[str] = Field(description="Ids that support the choice. Empty list if none.")
    required_by_user: bool = Field(description="True ONLY if the user required this technology. Everything else is a "
                                               "recommendation, never mandatory.")


class ArchitectureSection(BaseModel):
    """§4.6"""

    overview: BriefItem = Field(description="The recommended high-level architecture, 1-2 sentences.")
    components: list[Component] = Field(description="Major components (frontend, backend, database, external services, "
                                                    "AI components) that this project needs, 2-6 items.")
    data_flow: str = Field(description="How components communicate and data flows, 1-2 sentences.")
    technologies: list[TechnologyChoice] = Field(description="Recommended technologies, 2-6 items.")
    key_decisions: list[BriefItem] = Field(description="Important architectural decisions and trade-offs, 1-3 items.")


class ScopeSection(BaseModel):
    """§4.7"""

    in_scope: list[str] = Field(description="What the initial implementation includes, 2-6 items.")
    out_of_scope: list[str] = Field(description="Important exclusions, 1-5 items.")
    deliverables: list[str] = Field(description="Expected deliverables (application, services, documentation...), 1-5 items.")
    dependencies: list[BriefItem] = Field(description="External services, datasets, APIs or infrastructure needed. Empty list if none.")


class SuccessCriterion(BaseModel):
    """§4.8: never invent numerical targets without a baseline."""

    metric: str = Field(description="What is measured, e.g. 'share of test calculations that return the correct result'.")
    target: str | None = Field(description="Target value ONLY when the user's requirements or the evidence justify it; "
                                           "null otherwise.")
    basis: Literal["user_requirement", "evidence", "none"] = Field(
        description="Where the target comes from. 'none' when target is null."
    )
    evaluation_method: str = Field(description="How it will be measured, one short sentence.")
    evidence_ids: list[str] = Field(description="Required when basis is 'evidence'. Empty list otherwise.")


class Risk(BaseModel):
    risk: str
    category: Literal["implementation", "security", "privacy", "operational", "legal", "adoption", "other"]
    mitigation: str
    evidence_ids: list[str] = Field(description="Ids that support the risk. Empty list if none.")


class ConstraintsAndRisks(BaseModel):
    """§4.9"""

    constraints: list[BriefItem] = Field(description="Technical, financial, regulatory, resource and timeline constraints. "
                                                     "Confirmed ones are user_provided. Empty list if none known.")
    assumptions: list[str] = Field(description="Assumptions made because information is missing (kept apart from the "
                                               "confirmed requirements). Empty list if none.")
    unresolved_questions: list[str] = Field(description="Open questions and dependencies to settle. Empty list if none.")
    risks: list[Risk] = Field(description="Main implementation, security, privacy and operational risks with mitigations, 2-5 items.")


# The writer fills the brief in THREE structured calls: the whole schema in one call exceeds the API's size limit
# for strict structured output ("compiled grammar is too large"; the limit grows with the number of objects).
class BriefPartOne(BaseModel):
    """LLM output, brief call 1: sections 4.1-4.4."""

    project_overview: ProjectOverview
    problem_statement: ProblemStatement
    research_findings: ResearchFindings
    proposed_solution: ProposedSolutionSection


class BriefPartTwo(BaseModel):
    """LLM output, brief call 2: sections 4.5-4.6."""

    requirements: Requirements
    architecture: ArchitectureSection


class BriefPartThree(BaseModel):
    """LLM output, brief call 3: sections 4.7-4.9."""

    scope: ScopeSection
    success_criteria: list[SuccessCriterion] = Field(description="2-5 measurable outcomes that show the problem is solved.")
    constraints_and_risks: ConstraintsAndRisks

    @model_validator(mode="after")
    def targets_need_a_basis(self) -> "BriefPartThree":
        for c in self.success_criteria:
            if c.target and c.target.strip() and c.basis == "none":
                raise ValueError(f"success criterion {c.metric!r} has target {c.target!r} but basis 'none': "
                                 "set target to null, or give the basis (user_requirement / evidence).")
        return self


BRIEF_PARTS: tuple[type[BaseModel], ...] = (BriefPartOne, BriefPartTwo, BriefPartThree)


class BriefContent(BriefPartOne, BriefPartTwo, BriefPartThree):
    """Sections 4.1-4.9 (the three writer calls combined). Section 4.10 (references) is assembled by Python from the
    evidence ids cited here, so the writer cannot invent a source."""


class BriefReference(BaseModel):
    """§4.10: one source, assembled by Python from an evidence record."""

    number: int = Field(ge=1)
    evidence_id: str
    title: str
    url: HttpUrl
    domain: Domain
    source_type: SourceType
    verification_status: VerificationStatus
    cited_in: list[str] = Field(default_factory=list, description="Section keys that cite it.")


class ProblemBrief(BriefContent):
    """The brief as stored in state: the writer's sections + Python-assembled references and identity."""

    project_name: str
    revision: int = Field(ge=0, description="0 = first draft; +1 per revision.")
    references: list[BriefReference] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


BriefCheckId = Literal[
    "problem_clear_and_consistent",         # 1. clearly stated, consistent with the clarified requirements
    "solution_not_a_copy",                  # 2. addresses the problem rather than copying existing apps
    "recommendations_supported",            # 3. supported by research or labelled as assumptions
    "technically_plausible",                # 4. features and architecture plausible within the constraints
    "scope_separates_mvp",                  # 5. essential vs optional
    "success_criteria_measurable",          # 6. measurable, no fabricated targets
    "risks_and_questions_disclosed",        # 7. risks, dependencies, unresolved questions
    "claims_have_sources",                  # 8. research claims have sources
    "concise_consistent_readable",          # 9. concise, consistent, understandable
]
BRIEF_CHECK_IDS: tuple[str, ...] = BriefCheckId.__args__


class BriefCheck(BaseModel):
    check_id: BriefCheckId
    passed: bool
    severity: Level = Field(description="How much a failure matters: high = the brief misleads or cannot be planned from; "
                                        "low = polish. Use 'low' when passed.")
    issue: str = Field(description="What is wrong, citing the section, at most 2 short sentences. Empty string when passed.")
    fix_instruction: str = Field(description="Concrete instruction for the writer, one sentence. Empty string when passed.")


class BriefReview(BaseModel):
    """LLM output of the Brief Validator: the nine checks of spec §5."""

    checks: list[BriefCheck] = Field(description="Exactly one entry per check id, in the given order.")
    needs_user_input: bool = Field(
        description="True ONLY if critical information is missing or the requirements contradict each other so that "
                    "no rewrite can fix it without asking the user."
    )
    clarification_questions: list[str] = Field(description="When needs_user_input: at most 2 questions for the user. Empty list otherwise.")
    summary: str = Field(description="Two sentences: overall quality and the most important fix, if any.")

    @model_validator(mode="after")
    def one_entry_per_check(self) -> "BriefReview":
        got = [c.check_id for c in self.checks]
        if sorted(got) != sorted(BRIEF_CHECK_IDS):
            raise ValueError(f"checks must contain each of these ids exactly once: {list(BRIEF_CHECK_IDS)}; got {got}")
        if self.needs_user_input and not [q for q in self.clarification_questions if q.strip()]:
            raise ValueError("needs_user_input is true but clarification_questions is empty.")
        return self


class ValidationCheck(BaseModel):
    """One check result as stored: deterministic (Python) or LLM."""

    check_id: str
    source: Literal["deterministic", "llm"]
    passed: bool
    severity: Level
    issue: str = ""
    fix_instruction: str = ""


class BriefValidation(BaseModel):
    """Validator result, assembled in Python. Drives the edge after brief_validator."""

    verdict: Literal["approve", "revise", "clarify"]
    reason: str
    revision: int = Field(ge=0, description="The brief revision that was validated.")
    brief_generated_at: datetime | None = Field(default=None, description="generated_at of the validated draft: a "
                                                "validation applies to exactly that draft.")
    checks: list[ValidationCheck] = Field(default_factory=list)
    word_count: int = 0
    word_budget: int = 0
    clarification_questions: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list, description="Failed checks the brief goes forward with (no revision left).")
    llm_summary: str = ""
    validated_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# User review of the brief (spec §6)
# ---------------------------------------------------------------------------

# Where a change request goes: a misunderstanding of the requirements → clarification; a research or proposal
# quality issue → research / proposer; wording → brief_writer.
ReviewTarget = Literal["requirements", "research", "proposal", "wording"]


class BriefReviewReply(BaseModel):
    """What the user sends back when the graph is paused for the brief review."""

    action: Literal["approve", "request_changes"]
    feedback: str = Field(default="", max_length=4000, description="Required for request_changes: what to change or add.")
    target: Literal["auto", "requirements", "research", "proposal", "wording"] = Field(
        default="auto", description="Where the change should go; auto = the system decides from the feedback."
    )

    @model_validator(mode="after")
    def changes_need_feedback(self) -> "BriefReviewReply":
        if self.action == "request_changes" and len(self.feedback.strip()) < 3:
            raise ValueError("Describe the change you want (feedback is required to request changes).")
        return self


class FeedbackRouting(BaseModel):
    """LLM output: which step must handle the user's change request (only when the user chose target=auto)."""

    reasoning: str = Field(description="One or two sentences: what the user is asking for and which step can do it.")
    target: ReviewTarget = Field(
        description="requirements = the brief misunderstood what the user wants (audience, features, platform, constraints); "
                    "research = facts, sources or evidence are missing or wrong; proposal = the recommended solution "
                    "itself should change (different approach, architecture, feature set); wording = the content is right "
                    "but the text should be clearer, shorter, reordered, or a detail added or removed."
    )


# ---------------------------------------------------------------------------
# Implementation plan (spec §7): written by the planner (Opus) from the APPROVED brief
# ---------------------------------------------------------------------------

TASK_ID_PATTERN = r"^T\d{1,2}$"                         # T1 ... T99
MAX_PLAN_TASKS = 40

# What the sandbox (M7) will run: commands are argv lists, never shell strings. Python checks every command of the
# plan against this BEFORE approval; the sandbox enforces it again at run time.
ALLOWED_EXECUTABLES = ("npm", "npx", "pnpm", "node", "python", "python3", "uv", "pip", "pytest", "git", "ls", "cat",
                       "mkdir", "cp", "mv", "rm")
FORBIDDEN_COMMANDS = (("git", "push"), ("git", "remote"), ("npm", "publish"), ("pnpm", "publish"), ("npm", "login"),
                      ("pip", "upload"), ("uv", "publish"))
SHELL_METACHARACTERS = ("&&", "||", ";", "|", ">", "<", "`", "$(", "${", "&")


def command_problems(command: str, *, shell_operators: bool = True) -> list[str]:
    """Why a plan command would be refused (empty list = allowed). Pure Python, shared with the sandbox.
    shell_operators=False: the command came as an argv LIST (no shell anywhere), so ';' or '|' inside an argument
    (python3 -c "a; b") is just text; plan commands are strings and always get the check."""
    import shlex

    problems: list[str] = []
    if shell_operators and any(m in command for m in SHELL_METACHARACTERS):
        problems.append(f"{command!r}: shell operators are not allowed (one plain command per entry)")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return problems + [f"{command!r}: cannot be parsed ({exc})"]
    if not argv:
        return problems + ["empty command"]
    if argv[0] not in ALLOWED_EXECUTABLES:
        problems.append(f"{command!r}: '{argv[0]}' is not an allowed executable ({', '.join(ALLOWED_EXECUTABLES)})")
    if any(tuple(argv[:2]) == f for f in FORBIDDEN_COMMANDS):
        problems.append(f"{command!r}: publishing or pushing is not allowed")
    for arg in argv[1:]:
        values = [arg, arg.split("=", 1)[1]] if "=" in arg else [arg]      # --prefix=/tmp is a path too
        if any(v.startswith(("/", "~")) or ".." in v.split("/") for v in values):
            problems.append(f"{command!r}: paths must stay inside the project (no absolute paths, '~' or '..')")
            break
    if argv[0] == "rm" and any(a in ("-rf", "-fr", "-r", "-R") for a in argv[1:]) and any(a in (".", "*", "./") for a in argv[1:]):
        problems.append(f"{command!r}: deleting the whole project is not allowed")
    return problems


def path_problems(path: str) -> list[str]:
    if not path.strip() or path.startswith(("/", "~")) or ".." in path.split("/") or "\\" in path:
        return [f"file {path!r}: must be a relative path inside the project (no '/', '~', '..' or backslashes)"]
    return []


class PlanPhase(BaseModel):
    id: str = Field(description='Short id, e.g. "P1".')
    name: str = Field(description='E.g. "Project setup", "Calculation engine", "UI", "Offline and release".')
    goal: str = Field(description="What is true when the phase is done, one sentence.")


class PlanTask(BaseModel):
    """One step for the coding agent: small enough to implement and verify in one go."""

    id: str = Field(description='"T1", "T2", ... in execution order.')
    phase: str = Field(description="Id of its phase.")
    title: str = Field(description="Imperative, e.g. 'Implement the tokenizer and shunting-yard evaluator'.")
    description: str = Field(description="What to build and how, 2-5 sentences: modules, functions, data, edge cases. "
                                         "Enough that the coder makes no architectural decision.")
    depends_on: list[str] = Field(description="Ids of tasks that must be done first. Empty list if none.")
    files: list[str] = Field(description="Relative paths it creates or changes, e.g. 'src/engine.js'.")
    acceptance_criteria: list[str] = Field(description="Checkable outcomes, 1-4 items.")
    verify_commands: list[str] = Field(description="Commands that prove it works, run from the project root, e.g. "
                                                   "'npm test -- engine', 'node --test tests/engine.test.js'. 1-3 items, "
                                                   "each ONE plain command (no &&, pipes or redirects).")


class FeatureCoverage(BaseModel):
    feature: str = Field(description="An MVP feature of the approved brief, copied as written.")
    task_ids: list[str] = Field(description="The tasks that implement it.")


class PlanCommands(BaseModel):
    """How the build check (M9) installs, tests, builds and previews the generated app."""

    install: list[str] = Field(description="E.g. ['npm install']. Empty list if nothing to install.")
    test: list[str] = Field(description="E.g. ['npm test']. At least one.")
    build: list[str] = Field(description="E.g. ['npm run build']. Empty list if there is no build step.")
    dev: str = Field(description="Command that starts the dev server; it must listen on the port in the PORT "
                                 "environment variable, e.g. 'npm run dev'.")


class ImplementationPlan(BaseModel):
    """LLM output of the Planner: a Claude-Code-style plan from the approved brief. Python checks ids, the dependency
    graph, files and commands (validators below: call_structured retries with the exact problem)."""

    summary: str = Field(description="What will be built and how, 2-4 sentences, consistent with the approved brief.")
    tech_stack: list[str] = Field(description="Each choice with its reason, e.g. 'Vite (fast dev server, no framework needed)'.")
    project_structure: list[str] = Field(description="Main files and folders, each 'path: purpose'.")
    dependencies: list[str] = Field(description="Packages with purpose, e.g. 'vitest: unit tests'. Empty list if none.")
    architecture: str = Field(description="Components, responsibilities and data flow, 3-6 sentences.")
    data_model: str = Field(description="Database / storage design (tables, keys, local storage shape), or 'none'.")
    api_endpoints: list[str] = Field(description="'METHOD /path: purpose'. Empty list if there is no backend API.")
    frontend_components: list[str] = Field(description="'Name: responsibility'. Empty list if there is no UI.")
    backend_services: list[str] = Field(description="'Name: responsibility'. Empty list if there is no backend.")
    integrations: list[str] = Field(description="External services and how they are used. Empty list if none.")
    ai_components: str = Field(description="Models, agents or tools the app itself uses, ONLY if the brief needs them; "
                                           "otherwise 'none'.")
    phases: list[PlanPhase] = Field(description="2-6 phases in order.")
    tasks: list[PlanTask] = Field(description=f"All tasks in execution order, at most {MAX_PLAN_TASKS}; small and "
                                              "independently verifiable. The first task scaffolds the project and its "
                                              "test runner.")
    feature_coverage: list[FeatureCoverage] = Field(description="One entry per MVP feature of the approved brief.")
    testing_strategy: list[str] = Field(description="Unit / integration / end-to-end tests and what each covers, 2-5 items.")
    commands: PlanCommands
    risks_and_decisions: list[str] = Field(description="Technical risks and decisions settled here (with the choice made) "
                                                       "or still to confirm, 1-6 items.")

    @model_validator(mode="after")
    def plan_is_executable(self) -> "ImplementationPlan":
        import re

        problems: list[str] = []
        ids = [t.id for t in self.tasks]
        phase_ids = {p.id for p in self.phases}
        if not self.tasks:
            problems.append("the plan has no tasks")
        if len(self.tasks) > MAX_PLAN_TASKS:
            problems.append(f"{len(self.tasks)} tasks; at most {MAX_PLAN_TASKS}: merge small ones")
        if len(ids) != len(set(ids)):
            problems.append(f"task ids must be unique: {ids}")
        bad_ids = [i for i in ids if not re.match(TASK_ID_PATTERN, i)]
        if bad_ids:
            problems.append(f"task ids must look like T1, T2...: {bad_ids}")
        position = {tid: n for n, tid in enumerate(ids)}
        for t in self.tasks:
            if t.phase not in phase_ids:
                problems.append(f"{t.id}: unknown phase {t.phase!r} (phases: {sorted(phase_ids)})")
            for dep in t.depends_on:
                if dep not in position:
                    problems.append(f"{t.id}: depends on unknown task {dep!r}")
                elif position[dep] >= position[t.id]:
                    problems.append(f"{t.id}: depends on {dep}, which comes later or is itself; list tasks in "
                                    "execution order (dependencies first)")
            if not t.acceptance_criteria:
                problems.append(f"{t.id}: needs at least one acceptance criterion")
            if not t.verify_commands:
                problems.append(f"{t.id}: needs at least one verify command")
            for f in t.files:
                problems += [f"{t.id}: {p}" for p in path_problems(f)]
            for c in t.verify_commands:
                problems += [f"{t.id}: {p}" for p in command_problems(c)]
        cmds = self.commands
        if not cmds.test:
            problems.append("commands.test needs at least one command")
        for c in [*cmds.install, *cmds.test, *cmds.build, cmds.dev]:
            problems += [f"commands: {p}" for p in command_problems(c)]
        for cov in self.feature_coverage:
            unknown = [i for i in cov.task_ids if i not in position]
            if not cov.task_ids or unknown:
                problems.append(f"feature {cov.feature!r}: task_ids must name existing tasks (unknown: {unknown})")
        if problems:
            raise ValueError("The plan cannot be executed as written:\n- " + "\n- ".join(problems[:15]))
        return self


class PlanReviewReply(BaseModel):
    """What the user sends back when the graph is paused for the plan review."""

    action: Literal["approve", "request_changes"]
    feedback: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def changes_need_feedback(self) -> "PlanReviewReply":
        if self.action == "request_changes" and len(self.feedback.strip()) < 3:
            raise ValueError("Describe the change you want (feedback is required to request changes).")
        return self


class ErrorRecord(BaseModel):
    """Safe error info. Never put API keys or full request payloads here."""

    node: str
    operation: str
    category: Literal["llm_unavailable", "database", "invalid_input", "unknown"]
    message: str = Field(max_length=500, description="Shown to the user, e.g. the Claude API error of each model.")
    occurred_at: datetime = Field(default_factory=utc_now)
