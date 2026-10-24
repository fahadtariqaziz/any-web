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
    evidence: list[dict]                 # Evidence (each has a perspective)
    perspective_summaries: dict[str, str]  # perspective -> summary + prevalence note
    research_summary: str                # all perspectives, for quick printing
    evidence_gaps: list[str]
    conflicting_claims: list[dict]       # ConflictingClaim
    rejected_sources: list[dict]         # {url, title, perspective, reason}: kept for transparency
    research_retry_count: int            # +1 only when going BACK to research (first pass = 0)
    research_focus: list[str]            # what the next research pass must look for; written by the node that
                                         # sends the graph back (judge / evidence_checker), cleared by research

    # --- debate ------------------------------------------- (proposer/critic/judge)
    care_plans: list[dict]               # CarePlan, 2-3 per perspective      (proposer)
    proposer_notes: dict[str, str]       # perspective -> why fewer than 2 plans (proposer)
    proposer_lane_status: dict[str, str]  # perspective -> ok | thin | declined | no_evidence (proposer)
    criticisms: list[dict]               # Criticism, one per plan            (critic)
    scores: list[dict]                   # PlanScore, one per plan            (judge)
    verdict: dict                        # Verdict                            (judge)
    debate_round: int                    # +1 each time the proposer starts a new round

    # --- verification ------------------------------------------ (evidence_checker)
    verification_results: list[dict]     # ClaimVerification for the current winning plans
    checker_verdict: dict                # {decision, reason, gaps_by_lane, summaries}
    # (evidence[].verification_status is also written here)

    # --- output ------------------------------------------- (final_report/completion)
    final_report: dict                   # FinalReport
    onboarding_summary: dict             # OnboardingSummary, quick mode only: the chat's first answer (final_report)
    unresolved_questions: list[str]      # appended by evidence_checker, finalized by final_report
    completed_at: str
    metrics: dict                        # durations, rounds, counts (completion)

    # --- errors ------------------------------------------------ (nodes/node_wrapper.py)
    error: dict | None                   # ErrorRecord of the failure that ended the session (status "failed")
