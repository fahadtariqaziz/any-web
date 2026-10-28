"""Node 6 — Judge: score every proposal on the rubric in ONE call, pick the strongest, and check its claims.

Python then:
- computes weighted totals from the configured rubric weights (never trusts LLM math),
- picks the winner (highest weighted total),
- consolidates the winner's claim check (made by the critic's pool; nodes/claim_check.py): stores one
  ClaimVerification per claim and sets evidence[].verification_status (the separate Evidence Checker node was
  folded in here on 2026-10-29: one "decide" step, one routing decision instead of two),
- makes the ONE routing decision by combining sufficiency, contradictions, questions, the winner's material
  evidence gaps AND the loop limits.

Writes (owner): scores, verdict, verification_results, checker_verdict, evidence[].verification_status,
research_retry_count (+1 when sending the graph back to research or clarification), research_focus (when looping),
unresolved_questions (questions it could not ask, gaps it could not research), status, current_node.
"""

import json

from ai_decision_arena.config import RUBRIC_DESCRIPTIONS, get_settings
from ai_decision_arena.limits import loops_allowed
from ai_decision_arena.llm import call_structured
from ai_decision_arena.nodes.claim_check import consolidate
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, criticisms_block, evidence_block, proposals_block, user_case_block
from ai_decision_arena.schemas import DOMAINS, ProposalJudgement, ProposalScore, Verdict
from ai_decision_arena.state import ArenaState

MAX_QUESTIONS = 2

SYSTEM_PROMPT = """You are the Judge agent of an AI application builder. You compare ALL the proposed solutions and decide which
one best fits the user's requirements and the evidence.

First write your step-by-step reasoning (the `reasoning` field), then score every proposal on each rubric criterion
from 0 to 10 with a one-sentence explanation. The weighted total and the winner are computed by the system
afterwards; do not compute them yourself.

<rubric>
{rubric}
</rubric>

Consider: the user's requirements and constraints, each proposal, the Critic's points (a verified problem weighs
more than a possible risk), and the evidence (strength, relevance, gaps, conflicts). Scores are a reasoning aid,
not truth: explain them. Reward solutions that address the gaps users complain about and whose technology choices
are backed by evidence; penalise copies of existing apps, unsupported claims, and a first version that cannot be
built as described.

evidence_sufficient: true only if the evidence lets you defend a best solution for this user. If not, say why and
list required_evidence a follow-up search should find (at most 4 items).
domain_coverage: for each research domain (apps, papers, tech), whether its evidence was sufficient, insufficient
or absent, in one sentence each.
material_contradictions: contradictions between the user's requirements, the proposals or the evidence that must be
resolved before planning; empty if none.
clarification_questions: at most 2, and ONLY if the user's answer would change which proposal wins; otherwise empty.
""" + BUILDER_RULES


def _rubric_text() -> str:
    weights = get_settings().rubric_weights
    return "\n".join(
        f"- {name} (weight {weight:.2f}): {RUBRIC_DESCRIPTIONS.get(name, '')}" for name, weight in weights.items()
    )


def weighted_total(score: ProposalScore, weights: dict[str, float]) -> float:
    return round(sum(weights.get(c.criterion, 0.0) * c.score for c in score.criterion_scores), 2)


def _criterion(score: ProposalScore, name: str) -> float:
    return next((c.score for c in score.criterion_scores if c.criterion == name), 0.0)


def _domain_status_defaults(state: ArenaState, sufficient: bool) -> dict[str, str]:
    evidence = state.get("evidence", [])
    return {d: ("sufficient" if sufficient else "insufficient") if any(e["domain"] == d for e in evidence) else "no_evidence"
            for d in DOMAINS}


def _checker_verdict(decision: str, reason: str, check: dict) -> dict:
    """The claim-check summary the API and the report show (same shape as the former Evidence Checker node's)."""
    return {"decision": decision, "reason": reason, "material_gaps": check["material_gaps"], "summary": check["summary"],
            "claims_checked": check["claims_checked"]}


def judge_node(state: ArenaState) -> dict:
    weights = get_settings().rubric_weights
    proposals = state.get("proposals", [])
    known_evidence = {e["evidence_id"] for e in state.get("evidence", [])}
    can_debate, can_research, can_clarify, blocked = loops_allowed(state)
    update: dict = {"current_node": "judge"}
    reasons: list[str] = []

    # --- Nothing to judge: the Proposer returned no proposals ---------------------------------
    if not proposals:
        kind = state.get("proposer_status", "no_evidence")
        note = state.get("proposer_notes", "") or ""
        required = ["Usable sources about this idea: existing solutions and what their users complain about, "
                    "established approaches, and technical feasibility."]
        reasons.append(f"No proposals ({kind}). {note[:300]}".strip())
        if kind in ("thin", "no_evidence") and can_research:
            decision, status_text = "request_more_research", "researching"
            update["research_retry_count"] = state.get("research_retry_count", 0) + 1
            update["research_focus"] = required
            reasons.append("Running a focused follow-up search before judging.")
        else:
            decision, status_text = "insufficient_evidence", "reporting"
            reasons.append(f"Cannot propose a solution with the evidence available and no loop is possible "
                           f"({', '.join(blocked) or 'proposer declined'}).")
        update["scores"] = []
        update["verdict"] = Verdict(decision=decision, reason="\n".join(reasons), winning_proposal_id=None,
                                    domain_status=_domain_status_defaults(state, sufficient=False),
                                    required_evidence=required).model_dump(mode="json")
        update["verification_results"] = []
        update["checker_verdict"] = _checker_verdict("proceed", "No winning proposal to verify.",
                                                     {"material_gaps": [], "summary": "", "claims_checked": 0})
        update["status"] = status_text
        report("judge", f"decision: {decision}; no proposals to score")
        return update

    # --- One call scores every proposal -------------------------------------------------------
    report("judge", f"scoring {len(proposals)} proposal(s) on the rubric")
    user_content = f"""{user_case_block(state)}
{proposals_block(proposals)}
{criticisms_block(state.get("criticisms", []))}
{evidence_block(state.get("evidence", []), max_excerpt_chars=200)}
<evidence_gaps>{json.dumps(state.get("evidence_gaps", []), indent=1)}</evidence_gaps>
<conflicting_claims>{json.dumps(state.get("conflicting_claims", []), indent=1)}</conflicting_claims>"""
    out = call_structured(
        ProposalJudgement,
        SYSTEM_PROMPT.replace("{rubric}", _rubric_text()),
        user_content,
        max_tokens=7000,
        run_name="judge_llm",
    )

    ids = {p["proposal_id"] for p in proposals}
    scores: list[ProposalScore] = []
    for s in out.scores:
        if s.proposal_id not in ids:
            continue   # the LLM scored a proposal that does not exist: ignore
        s.weighted_total = weighted_total(s, weights)
        s.supporting_evidence_ids = [eid for eid in s.supporting_evidence_ids if eid in known_evidence]
        scores.append(s)
    unscored = sorted(ids - {s.proposal_id for s in scores})
    # Highest weighted total wins; ties go to the better-evidenced proposal.
    winner = max(scores, key=lambda s: (s.weighted_total, _criterion(s, "evidence_quality"))).proposal_id if scores else None

    # --- The winner's claims against the evidence it cites (Python; the critic's pool made the check) -----------
    check = consolidate(state, winner)
    gaps = check["material_gaps"]

    domain_status = _domain_status_defaults(state, sufficient=out.evidence_sufficient)
    for c in out.domain_coverage:
        domain_status[c.domain] = c.status
    questions: list[str] = []
    for q in out.clarification_questions:
        if q.strip() and q.strip().lower() not in {x.lower() for x in questions}:
            questions.append(q.strip())
    questions = questions[:MAX_QUESTIONS]
    contradictions = [c.strip() for c in out.material_contradictions if c.strip()]
    required = list(out.required_evidence)
    sufficient = out.evidence_sufficient and winner is not None
    if not sufficient and not required:
        required = [out.insufficiency_reason or "More evidence needed to defend a best solution."]
    reasons.append(out.comparison + (f" Unscored proposals: {unscored}." if unscored else ""))
    if contradictions:
        reasons.append("Material contradictions: " + "; ".join(contradictions))

    # --- Routing: Python has the final say, bounded by the loop limits -----------------------
    if contradictions and not questions and can_clarify:
        questions = [f"The research found a contradiction to resolve: {c} Which should we follow?" for c in contradictions[:MAX_QUESTIONS]]
    checker_decision, checker_reason = "proceed", "All material claims are supported."
    if sufficient and not contradictions and gaps and can_research:
        decision, status_text = "request_more_research", "researching"
        update["research_retry_count"] = state.get("research_retry_count", 0) + 1
        update["research_focus"] = list(gaps)
        checker_decision = decision
        checker_reason = ("Material claims of the winning proposal are not supported by the cited evidence: one "
                          "focused research pass.")
        reasons.append(f"A defensible best solution exists ({winner}), but {len(gaps)} material claim(s) of it are "
                       "unverified: running a focused follow-up search.")
    elif sufficient and not contradictions:
        decision, status_text = "proceed", "reporting"
        reasons.append(f"A defensible best solution exists ({winner}).")
    elif questions and can_clarify:
        decision, status_text = "request_clarification", "debating"
        update["research_retry_count"] = state.get("research_retry_count", 0) + 1
        update["research_focus"] = required + ["The user just answered the Judge's follow-up questions "
                                               "(see <clarification_answers>): re-check what those answers change."]
        reasons.append("The user's answers would change the outcome: asking before continuing.")
    elif not sufficient and can_research:
        decision, status_text = "request_more_research", "researching"
        update["research_retry_count"] = state.get("research_retry_count", 0) + 1
        update["research_focus"] = list(required)
        reasons.append("The evidence is insufficient: running a focused follow-up search.")
    elif sufficient:
        decision, status_text = "proceed", "reporting"
        reasons.append("Contradictions remain but no clarification loop is possible: continuing with them recorded.")
    else:
        decision, status_text = "insufficient_evidence", "reporting"
        reasons.append(f"Evidence remains insufficient and the loop limits are reached ({', '.join(blocked) or 'no loop possible'}): "
                       "continuing with the uncertainty stated.")
    if gaps and checker_decision == "proceed":
        checker_reason = (f"Unverified material claims remain ({'; '.join(blocked) or 'no loop possible'}); "
                          "continuing with them listed as unresolved.")

    update["scores"] = [s.model_dump(mode="json") for s in scores]
    update["verdict"] = Verdict(
        decision=decision,
        reason="\n".join(reasons),
        winning_proposal_id=winner,
        domain_status=domain_status,
        required_evidence=required if not sufficient else [],
        material_contradictions=contradictions,
        clarification_questions=questions if decision == "request_clarification" else [],
    ).model_dump(mode="json")
    update["verification_results"] = check["verification_results"]
    update["evidence"] = check["evidence"]
    update["checker_verdict"] = _checker_verdict(checker_decision, checker_reason, check)
    unresolved = list(state.get("unresolved_questions", []))
    if questions and decision != "request_clarification":
        # Not asked (fast path or no clarification round left): the brief lists them, the user's review answers them.
        unresolved += [f"Question for you: {q}" for q in questions if f"Question for you: {q}" not in unresolved]
    if gaps and decision in ("proceed", "insufficient_evidence"):
        # Not researched (fast path or no research pass left): the brief lists them, never hidden.
        unresolved += [f"Unverified: {g}" for g in gaps if f"Unverified: {g}" not in unresolved]
    if unresolved != list(state.get("unresolved_questions", [])):
        update["unresolved_questions"] = unresolved
    update["status"] = status_text
    report("judge", f"decision: {decision}; winner: {winner}")
    return update
