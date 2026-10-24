"""ArenaState: the shared state that flows through the LangGraph graph.

Design rules:
- Each field has ONE owner node that writes it (see comments). Other nodes only read it.
- Nested items are stored as plain dicts (Pydantic model.model_dump(mode="json")).
  Plain JSON keeps checkpoints in PostgreSQL simple and readable, and the API can
  return them directly. Nodes re-validate with Model.model_validate(d) when reading.
- No raw web pages here: only short, structured Evidence records.
- No reducers yet: the MVP graph is sequential, so only one node writes at a time.
"""

from typing import TypedDict

from ai_decision_arena.schemas import WorkflowStatus


class ArenaState(TypedDict, total=False):
    # --- session ---------------------------------------------------- (API / intake)
    thread_id: str
    mode: str                            # "full" (admin view: every pause) | "quick" (patient chat: fast settings,
                                         # ends with onboarding_summary). Set by the API.
    status: WorkflowStatus               # editor warns on typos like "complete"
    current_node: str                    # last node that ran, for the frontend
    started_at: str                      # ISO time, set by intake
    user_id: str                      # anonymous browser id (X-User-Id), "" without one. Set by the API.
    user_memories: list[str]          # long-term memory loaded when the session starts (memory.py). Set by the API.
    active_seconds: float                # time spent inside nodes (pauses excluded); added by the error wrapper

    # --- case understanding -------------------------------------------- (intake)
    question: str                        # the user's original text, never rewritten
    user_context: str                    # optional extra context from the form
    project_name: str                  # e.g. "type 2 diabetes" (as the user frames it; clarification may refine it)
    project_category: str              # a ProjectCategory value, e.g. "metabolic_endocrine"
    idea_summary: str                    # neutral restatement (used for research queries; clarification may refine it)
    project_profile: dict[str, str]       # e.g. {"age": "42", "medications": "metformin"}
    requested_features: dict[str, str]             # e.g. {"fatigue": "most afternoons"}
    constraints: dict[str, str]          # e.g. {"diet": "vegetarian", "budget": "low-cost"}
    missing_information: list[str]
    risk_flags: list[str]                 # ACTIVE signs that may need urgent care (clarification appends / withdraws)
    withdrawn_risk_flags: list[dict]      # {"flag", "reason"}: contradicted by a later answer; kept for the record (clarification)

    # --- clarification ------------------------------------------ (clarification)
    need_clarification: bool
    clarification_questions: list[str]   # questions currently pending
    clarification_reason: str            # Claude's reason for asking / not asking
    clarification_answers: dict[str, str]  # question -> user's answer (all rounds)
    assumptions: list[str]               # recorded when we stop asking
    clarification_round_count: int       # one user-input round = +1 (not per question)

    # --- research ----------------------------------------------------- (research)
    research_queries: list[str]
    evidence: list[dict]                 # Evidence (each has a domain)
    domain_summaries: dict[str, str]  # domain -> summary + prevalence note
    research_summary: str                # all domains, for quick printing
    evidence_gaps: list[str]
    conflicting_claims: list[dict]       # ConflictingClaim
    rejected_sources: list[dict]         # {url, title, domain, reason}: kept for transparency
    research_retry_count: int            # +1 only when going BACK to research (first pass = 0)
    research_focus: list[str]            # what the next research pass must look for; written by the node that
                                         # sends the graph back (judge / evidence_checker), cleared by research

    # --- debate ------------------------------------------- (proposer/critic/judge)
    proposals: list[dict]                # SolutionProposal, 2-3 per round        (proposer)
    proposer_notes: str                  # why fewer than 2 proposals             (proposer)
    proposer_status: str                 # ok | thin | declined | no_evidence     (proposer)
    criticisms: list[dict]               # Criticism, one per proposal            (critic)
    scores: list[dict]                   # ProposalScore, one per proposal        (judge)
    verdict: dict                        # Verdict                                (judge)
    debate_round: int                    # +1 each time the proposer starts a new round

    # --- verification ------------------------------------------ (evidence_checker)
    verification_results: list[dict]     # ClaimVerification for the winning proposal
    checker_verdict: dict                # {decision, reason, material_gaps, summary, claims_checked}
    # (evidence[].verification_status is also written here)

    # --- output ------------------------------------------- (final_report/completion)
    final_report: dict                   # FinalReport: the debate's outcome (data step before the brief)
    unresolved_questions: list[str]      # appended by evidence_checker / final_report / brief_validator

    # --- problem brief -------------------------------------------- (brief_writer / brief_validator)
    brief: dict                          # ProblemBrief (sections 4.1-4.9 + Python-assembled references)  (brief_writer)
    brief_markdown: str                  # rendered brief: main part (~1 page) + appendix                  (brief_writer;
                                         #   brief_validator re-renders it when open issues remain)
    brief_revision_count: int            # rewrites asked by the validator for the current brief             (brief_validator;
                                         #   reset to 0 when it sends the graph back to clarification)
    brief_validation: dict               # BriefValidation of the latest draft                                (brief_validator)

    # --- brief review (the user) -------------------------------- (await_brief_review / brief_review_router)
    brief_feedback: list[dict]           # one entry per review reply: {round, action, target, feedback, at};
                                         #   the router adds resolved_target to the last entry                    (both)
    brief_review_round_count: int        # change requests so far (approvals not counted)                        (await_brief_review)
    brief_review_route: str              # approved | wording | requirements | research | proposal              (brief_review_router)
    brief_approved_at: str | None        # ISO time of the approval                                             (brief_review_router)
    brief_approved_hash: str | None      # sha256 of the approved brief_markdown: a later edit invalidates it    (brief_review_router)

    # --- implementation plan ------------------------------- (planner / await_plan_review / plan_review_router)
    implementation_plan: dict            # ImplementationPlan                                                    (planner)
    plan_markdown: str                   # rendered plan                                                         (planner)
    plan_revision_count: int             # rewrites asked by the user                                            (planner)
    implementation_tasks: list[dict]     # {id, title, phase, depends_on, status, attempts, result}: the coder's work list
                                         #   (planner creates it; the implementer updates it, M8)
    models_used: dict[str, str]          # node -> model actually used (after the availability check)            (planner)
    plan_feedback: list[dict]            # {round, action, feedback, at} per review reply                        (await_plan_review)
    plan_review_route: str               # approved | changes                                                    (plan_review_router)
    plan_approved_at: str | None         #                                                                       (plan_review_router)
    plan_approved_hash: str | None       # sha256 of the approved plan_markdown                                  (plan_review_router)
    completed_at: str
    metrics: dict                        # durations, rounds, counts (completion)

    # --- errors ------------------------------------------------ (nodes/node_wrapper.py)
    error: dict | None                   # ErrorRecord of the failure that ended the session (status "failed")
