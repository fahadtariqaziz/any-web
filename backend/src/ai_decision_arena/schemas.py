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


class ErrorRecord(BaseModel):
    """Safe error info. Never put API keys or full request payloads here."""

    node: str
    operation: str
    category: Literal["llm_unavailable", "database", "invalid_input", "unknown"]
    message: str = Field(max_length=500, description="Shown to the user, e.g. the Claude API error of each model.")
    occurred_at: datetime = Field(default_factory=utc_now)
