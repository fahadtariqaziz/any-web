"""Node 9 — Final Report (the debate's outcome, the data step before the brief), and the terminal Completion node.

Final Report: Python assembles everything that is already known (the winning proposal and the alternatives with
their scores, cited evidence with verification status, Critic objections, unsupported claims, unresolved questions,
methodology), no LLM call. The human-readable parts (overview, why this solution, uncertainties, next steps) are
written from those facts only by ONE LLM call (add_narrative) that the brief writer runs in parallel with the brief.
In M4 the problem statement + solution brief becomes the document the user reviews; the data
assembled here feeds it.

Completion: sets the final status (completed / completed_with_uncertainty / failed), records metrics, saves
session + evidence + report to the app tables (db/repository.py), and never marks a run completed without a report
that was actually saved.
"""

import json
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig

from ai_decision_arena.config import get_settings
from ai_decision_arena.db.repository import save_completion
from ai_decision_arena.llm import call_structured
from ai_decision_arena.memory import remember_session
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, user_case_block
from ai_decision_arena.schemas import (
    DOMAINS,
    ErrorRecord,
    EvidenceRef,
    FinalReport,
    ProposalResult,
    ProposalScore,
    ReportNarrative,
    SolutionProposal,
)
from ai_decision_arena.state import ArenaState
from ai_decision_arena.usage import llm_cost

DISCLAIMER = (
    "This report summarises web research retrieved automatically: existing products and their users' feedback, papers "
    "and technical literature, and technical documentation and repositories. Claims are labelled by how well their "
    "sources support them. It is a starting point for planning, not a guarantee of feasibility or demand."
)

SYSTEM_PROMPT = """You write the interim report of an AI application builder for the user, in plain language.

You receive the winning solution proposal, the alternatives, their scores, how well the winner's claims were
verified, the Critic's main objections and the open questions. Write ONLY from these facts: no new facts, no
numbers that are not in the input, no products or sources that are not in the input. Keep each list item to one
sentence. overview: 4-6 sentences (the problem, the recommended solution, why, the main caveat).
next_steps: what to confirm or decide before planning the build. If there is no winner, say so and why.
""" + BUILDER_RULES


def _proposal_result(state: ArenaState, proposal: dict, is_winner: bool) -> ProposalResult:
    pid = proposal["proposal_id"]
    score = next((s for s in state.get("scores", []) if s["proposal_id"] == pid), None)
    crit = next((c for c in state.get("criticisms", []) if c["proposal_id"] == pid), {"points": []})
    evidence = {e["evidence_id"]: e for e in state.get("evidence", [])}
    checks = [v for v in state.get("verification_results", []) if v["proposal_id"] == pid]
    counts: dict[str, int] = {}
    for v in checks:
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    severity = {"high": 0, "medium": 1, "low": 2}
    objections = sorted(crit["points"], key=lambda p: severity.get(p["severity"], 3))
    return ProposalResult(
        proposal=SolutionProposal.model_validate(proposal),
        score=ProposalScore.model_validate(score) if score else None,
        is_winner=is_winner,
        key_evidence=[
            EvidenceRef(evidence_id=i, title=evidence[i]["source_title"], url=evidence[i]["source_url"],
                        verification_status=evidence[i].get("verification_status", "pending"))
            for i in proposal.get("supporting_evidence_ids", []) if i in evidence
        ],
        critic_key_objections=[f"[{p['severity']}/{p['category']}] {p['issue']}" for p in objections[:3]],
        verification_counts=counts,
        verification_notes=[f"{v['status']}: {v['claim']}" for v in checks[:6]],
    )


def _methodology(state: ArenaState) -> str:
    evidence = state.get("evidence", [])
    per_domain = ", ".join(f"{sum(1 for e in evidence if e['domain'] == d)} {d}" for d in DOMAINS)
    passes = state.get("research_retry_count", 0) + 1
    checks = state.get("verification_results", [])
    return (
        f"{len(state.get('research_queries', []))} web searches in three domains (existing apps and user feedback, research "
        f"papers, technical feasibility) over {passes} research pass(es); {len(evidence)} sources kept ({per_domain}), "
        f"{len(state.get('rejected_sources', []))} rejected with a stated reason. {state.get('debate_round', 0)} debate "
        f"round(s): a Proposer designed solutions from the evidence, a Critic challenged each against all evidence, and a "
        f"Judge scored them on a weighted rubric; the best proposal was kept. {len(checks)} factual claim(s) of the winning "
        f"proposal were checked against their cited evidence."
    )


def _compact(result: ProposalResult) -> dict:
    p = result.proposal
    return {
        "proposal_id": p.proposal_id, "name": p.name, "summary": p.summary, "problem_addressed": p.problem_addressed,
        "core_features": p.core_features[:6], "architecture": p.architecture.model_dump(), "technologies": p.technologies[:6],
        "how_it_beats_alternatives": p.how_it_beats_alternatives, "difficulty": p.difficulty,
        "score": result.score.weighted_total if result.score else None,
        "confidence": result.score.confidence if result.score else None,
        "verification_counts": result.verification_counts, "critic_key_objections": result.critic_key_objections,
    }


def needs_narrative(final_report: dict | None) -> bool:
    return bool(final_report) and not final_report.get("overview")


def add_narrative(state: ArenaState, final_report: dict) -> dict:
    """ONE LLM call writes the report's human-readable parts from the assembled facts; returns the completed report.
    Called by the brief writer in parallel with the brief parts (the brief does not use the narrative), so the
    report costs no wait of its own."""
    final = FinalReport.model_validate(final_report)
    verdict = state.get("verdict") or {}
    narrative = call_structured(
        ReportNarrative,
        SYSTEM_PROMPT,
        f"""{user_case_block(state)}
<winner>{json.dumps(_compact(final.winner), indent=1) if final.winner else "null"}</winner>
<alternatives>{json.dumps([_compact(a) for a in final.alternatives], indent=1)}</alternatives>
<verdict_reason>{verdict.get("reason", "")}</verdict_reason>
<unsupported_claims>{json.dumps(final.unsupported_claims, indent=1)}</unsupported_claims>
<unresolved_questions>{json.dumps(final.unresolved_questions, indent=1)}</unresolved_questions>""",
        max_tokens=3500,
        run_name="final_report_llm",
        effort="low",
    )
    final.overview = narrative.overview
    final.why_this_solution = narrative.why_this_solution if final.winner else []
    final.uncertainties = narrative.key_uncertainties
    final.next_steps = narrative.next_steps
    return final.model_dump(mode="json")


def final_report_node(state: ArenaState) -> dict:
    report("final_report", "assembling the winning proposal and the alternatives")
    verdict = state.get("verdict") or {}
    winner_id = verdict.get("winning_proposal_id")
    proposals = state.get("proposals", [])
    winner = next((_proposal_result(state, p, True) for p in proposals if p["proposal_id"] == winner_id), None)
    alternatives = [_proposal_result(state, p, False) for p in proposals if p["proposal_id"] != winner_id]
    checks = state.get("verification_results", [])
    unsupported = [v["claim"] for v in checks if v["status"] in ("unsupported", "contradicted")]

    unresolved = list(state.get("unresolved_questions", []))
    for q in verdict.get("clarification_questions", []):
        if q not in state.get("clarification_answers", {}) and q not in unresolved:
            unresolved.append(q)
    for c in verdict.get("material_contradictions", []):
        if f"Contradiction: {c}" not in unresolved:
            unresolved.append(f"Contradiction: {c}")

    statuses = verdict.get("domain_status", {})
    is_conditional = bool(
        winner is None
        or verdict.get("decision") != "proceed"
        or any(v != "sufficient" for v in statuses.values())
        or any(f.startswith("Unverified:") for f in unresolved)
        or verdict.get("material_contradictions")
    )
    final = FinalReport(
        original_question=state.get("question", ""),
        project_name=state.get("project_name", ""),
        confirmed_profile=state.get("project_profile", {}),
        requested_features=state.get("requested_features", {}),
        constraints=state.get("constraints", {}),
        clarifications=state.get("clarification_answers", {}),
        assumptions=state.get("assumptions", []),
        research_methodology=_methodology(state),
        overview="",                    # the narrative is written later, in parallel with the brief (add_narrative)
        winner=winner,
        alternatives=alternatives,
        no_winner_reason="" if winner else (state.get("proposer_notes") or verdict.get("reason", "No defensible proposal.")),
        why_this_solution=[],
        is_conditional=is_conditional,
        uncertainties=[],
        unsupported_claims=unsupported,
        unresolved_questions=unresolved,
        next_steps=[],
        risk_flags=state.get("risk_flags", []),
        withdrawn_risk_flags=[f"{w['flag']} ({w['reason']})" for w in state.get("withdrawn_risk_flags", [])],
        disclaimer=DISCLAIMER,
    )
    report("final_report", "report ready" + (" (conditional)" if is_conditional else ""))
    return {
        "final_report": final.model_dump(mode="json"),
        "unresolved_questions": unresolved,
        "status": "writing_brief",
        "current_node": "final_report",
    }


def completion_node(state: ArenaState, config: RunnableConfig) -> dict:
    """Terminal node: final status + metrics + save to the app tables. Not wrapped by wrap_node:
    a failed save is handled here (status failed, error recorded; the report stays in the checkpoint)."""
    final = state.get("final_report")
    if state.get("status") == "failed" or not final:
        status = "failed"                                    # never "completed" without a report
    else:
        open_issues = (state.get("brief_validation") or {}).get("open_issues")
        unfinished = [t for t in state.get("implementation_tasks", []) if t.get("status") != "done"]
        built = bool(state.get("workspace_dir"))
        build_failed = bool(state.get("build_results")) and not state["build_results"].get("passed")
        preview_down = bool(state.get("preview")) and state["preview"].get("state") != "ready"
        status = ("completed_with_uncertainty" if final.get("is_conditional") or open_issues
                  or (built and (unfinished or build_failed or preview_down)) else "completed")
    metrics = {
        "active_seconds": state.get("active_seconds", 0.0),
        "debate_rounds": state.get("debate_round", 0),
        "research_retries": state.get("research_retry_count", 0),
        "clarification_rounds": state.get("clarification_round_count", 0),
        "evidence_count": len(state.get("evidence", [])),
        "claims_checked": len(state.get("verification_results", [])),
        "started_at": state.get("started_at"),
        "llm_cost_usd": llm_cost(state),          # the builder's own model calls (metered since M11)
        "llm_calls": sum(e.get("calls", 0) for e in state.get("usage_log") or []),
        "prompt_versions": state.get("prompt_versions") or {},
    }
    if state.get("workspace_dir"):
        tasks = state.get("implementation_tasks", [])
        metrics["tasks"] = {s: sum(t.get("status") == s for t in tasks) for s in ("done", "failed", "blocked", "skipped")}
        metrics["implementation_cost_usd"] = state.get("implementation_cost_usd", 0.0)
        metrics["build_passed"] = (state.get("build_results") or {}).get("passed")
        metrics["preview_state"] = (state.get("preview") or {}).get("state")
        metrics["e2e_status"] = (state.get("e2e_results") or {}).get("status")
        metrics["review_findings"] = len((state.get("code_review") or {}).get("findings", []))
        metrics["learnings"] = len(state.get("learnings") or [])
        metrics["change_requests"] = len(state.get("change_requests", []))
    update = {
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metrics": metrics,
        "current_node": "completion",
    }

    if get_settings().persist_results:
        thread_id = config["configurable"]["thread_id"]
        try:
            save_completion(thread_id, state, status, metrics)
            report("completion", f"saved session, {len(state.get('evidence', []))} evidence"
                                 + (" and the report" if final else "") + " to the database")
            if final and (saved := remember_session(state, thread_id)):
                report("completion", f"remembered {saved} fact(s) about this user for next time")
        except Exception as exc:   # never "completed" without a saved report
            error = ErrorRecord(node="completion", operation="save_completion", category="database",
                                message=f"{type(exc).__name__}: {str(exc)[:400]}")
            report("completion", f"could not save to the database ({type(exc).__name__}); status failed")
            update |= {"status": "failed", "error": error.model_dump(mode="json")}

    report("completion", f"status: {update['status']}")
    return update
