"""Node 10 — Brief Writer: the one-page problem statement + solution brief (spec §4).

Python gathers the facts (clarified requirements, the winning proposal and the alternatives, the Critic's points,
the Judge's verdict, the verified claims, all the evidence); the LLM writes sections 4.1-4.9 with every statement
labelled (verified / research_backed / user_provided / recommendation / assumption) and cited by evidence id, in
THREE structured calls (the whole schema in one call exceeds the API's strict-output size limit): sections 1-4
first, then 5-6 and 7-9 in parallel, both given sections 1-4 so the brief stays consistent. Then Python:
- fixes labels it knows better (brief.normalize: "verified" needs a verified source; only user-required technology
  is mandatory),
- assembles section 4.10, the references, from the cited ids (titles and URLs from the evidence records),
- renders the markdown (main part ~1 page, overflow to the appendix).

On a revision the writer also gets its previous draft and what to change: the validator's failed checks with their
fix instructions (verdict "revise"), or the user's change request when the review routed it to "wording". The
draft number (`revision`) only grows within a session; a draft written after a research / proposal loop starts from
the new facts (no previous draft), but keeps counting.

Writes (owner): brief, brief_markdown, status, current_node.
"""

import json

from langsmith.utils import ContextThreadPoolExecutor

from ai_decision_arena.brief import assemble_references, normalize, render_brief_markdown
from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, criticisms_block, evidence_block, user_case_block
from ai_decision_arena.schemas import BriefContent, BriefPartOne, BriefPartThree, BriefPartTwo, ProblemBrief
from ai_decision_arena.state import ArenaState

SYSTEM_PROMPT = """You are the Brief Writer of an AI application builder. Write the problem statement and solution brief
the user will review before any planning or code: about ONE page, grounded in the user's clarified requirements and
the research, for technical and non-technical readers.

You receive the user's requirements, the winning solution proposal (selected by a Judge after a Critic reviewed it),
the alternatives, the Critic's points on the winner, the Judge's verdict, which of the winner's claims were checked
against their sources, and all the evidence. Write ONLY from these facts.

Sections (fill every one):
1. project_overview: a name only if the user gave one (else a plain descriptive one or empty), what the project is,
   the intended users / stakeholders, the domain and context.
2. problem_statement: the specific problem or unmet need, who has it and where, how they cope today (existing
   alternatives), the gap to the desired outcome, the consequences of leaving it unresolved, indicators from the
   evidence. SOLUTION-NEUTRAL: describe the problem before any feature or technology; never name the proposed app,
   a feature or a technology as the answer in this section.
3. research_findings: the most relevant findings per research domain (existing apps and user feedback; papers and
   literature; feasibility, open-source implementations and docs), the limitations of existing solutions and the
   opportunity, and evidence_gaps (what the research could not establish).
4. proposed_solution: how the recommended app addresses the problem, the MVP features (the user-facing
   capabilities of the first version) vs future enhancements, the key user journey, and why this approach beats
   the alternatives considered (name them).
5. requirements: functional; non-functional (performance, security, privacy, reliability, accessibility,
   scalability as relevant); integrations / data inputs and outputs and user roles where they apply; testable
   acceptance criteria for the critical requirements when there is enough information.
6. architecture: the high-level architecture, its components and their responsibilities (only the parts this
   project needs: frontend, backend, database, external services, AI components), how data flows, recommended
   technologies with the reason, key decisions and trade-offs. A technology is required_by_user ONLY when the user
   asked for it; every other choice is a recommendation, never mandatory.
7. scope: what the first implementation includes, important exclusions, deliverables, external dependencies.
8. success_criteria: measurable outcomes that show the problem is solved, each with how it is measured. Give a
   target value ONLY when the user's requirements or the cited evidence justify it (basis user_requirement /
   evidence); otherwise target = null and basis = "none". NEVER invent a number without a baseline.
9. constraints_and_risks: constraints (confirmed ones are user_provided), assumptions (kept apart from confirmed
   requirements), unresolved questions (cover every item of <unresolved_questions> and the Judge's contradictions,
   concisely, without duplicates), the main implementation / security / privacy / operational risks with
   mitigations.
The references section is added automatically from the evidence ids you cite: never write URLs, source titles or
evidence ids inside the text.

Labels (every statement has one):
- verified: supported by evidence marked checked="verified" (cite it).
- research_backed: supported by other evidence (cite it).
- user_provided: the user said it (question, answers, profile, constraints). No citation needed.
- recommendation: your (the agents') recommendation. No citation needed.
- assumption: assumed because it is unknown. No citation needed.
verified and research_backed MUST cite at least one evidence id from <evidence>; if you cannot cite one, use
recommendation or assumption instead. Cite only ids that appear in <evidence>.

Style: one sentence per item, at most ~20 words. The list sizes in the field descriptions are LIMITS, not targets:
use the low end. Items beyond what fits the page are moved to an appendix the user must still read, so every extra
item costs the reader; never repeat a point in two sections (e.g. the MVP features are not listed again as
requirements or scope in other words).
Aim for about {word_target} words for sections 1-9 together (hard limit about {word_budget}). Plain language, no marketing tone, no
repetition between sections.
""" + BUILDER_RULES

PART_NOTE = {
    BriefPartOne: "\nThis call writes sections 1-4 ONLY (the fields of the output schema); sections 5-9 are written "
                  "separately from the same facts.",
    BriefPartTwo: "\nThis call writes sections 5-6 ONLY. <sections_1_to_4> were already written: stay consistent with "
                  "them (same MVP, same audience) and do not repeat them.",
    BriefPartThree: "\nThis call writes sections 7-9 ONLY. <sections_1_to_4> were already written: stay consistent with "
                    "them (in_scope = the MVP features) and do not repeat them.",
}
PART_MAX_TOKENS = {BriefPartOne: 5000, BriefPartTwo: 4000, BriefPartThree: 4000}

REVISION_NOTE = """
This is a REVISION. <previous_draft> is your last draft and <validation_issues> lists what the validator found.
Fix every issue that concerns the sections of this call (follow each fix_instruction), keep what was fine, and do
not introduce new unsupported claims."""

USER_REVISION_NOTE = """
This is a REVISION requested by the USER while reviewing the brief. <previous_draft> is the draft they reviewed and
<validation_issues> holds their change request (the last item of <brief_feedback>). Apply it in the sections of this
call where it belongs, keep everything else as it was, and keep the labels honest: a fact the user states is
user_provided; never invent evidence to satisfy the request."""


def brief_alternatives(state: ArenaState) -> list[dict]:
    """The proposals that did not win, as the appendix shows them."""
    report_alts = (state.get("final_report") or {}).get("alternatives", [])
    return [{"name": a["proposal"]["name"], "summary": a["proposal"]["summary"],
             "weighted_total": (a.get("score") or {}).get("weighted_total"),
             "critic_key_objections": a.get("critic_key_objections", [])[:2]} for a in report_alts]


def _winner(state: ArenaState) -> dict | None:
    winner_id = (state.get("verdict") or {}).get("winning_proposal_id")
    return next((p for p in state.get("proposals", []) if p["proposal_id"] == winner_id), None)


def revision_mode(state: ArenaState) -> str | None:
    """"validator" (verdict revise), "user" (the review routed a change request to wording), or None (fresh draft)."""
    if not state.get("brief"):
        return None
    if (state.get("brief_validation") or {}).get("verdict") == "revise" and state.get("current_node") == "brief_validator":
        return "validator"
    if state.get("current_node") == "brief_review_router" and state.get("brief_review_route") == "wording":
        return "user"
    return None


def _issues(state: ArenaState, mode: str) -> list[dict]:
    if mode == "user":
        last = state["brief_feedback"][-1]
        return [{"check": "user_change_request", "issue": last["feedback"],
                 "fix_instruction": "Apply the user's change request."}]
    return [{"check": c["check_id"], "issue": c["issue"], "fix_instruction": c["fix_instruction"]}
            for c in state["brief_validation"]["checks"] if not c["passed"]]


def _user_content(state: ArenaState, mode: str | None, part: type, first: BriefPartOne | None = None) -> str:
    winner = _winner(state)
    verdict = state.get("verdict") or {}
    winner_id = winner["proposal_id"] if winner else None
    checks = [{"claim": v["claim"], "status": v["status"], "evidence_ids": v.get("evidence_ids", [])}
              for v in state.get("verification_results", []) if v.get("proposal_id") == winner_id]
    body = {k: v for k, v in (winner or {}).items() if k not in ("round",)}
    content = f"""{user_case_block(state)}
<winning_proposal>{json.dumps(body, indent=1) if winner else "null (no proposal could be defended: write the brief around the problem and say so)"}</winning_proposal>
<alternatives>{json.dumps(brief_alternatives(state), indent=1)}</alternatives>
{criticisms_block([c for c in state.get("criticisms", []) if c["proposal_id"] == winner_id])}
<judge_verdict>{json.dumps({"reason": verdict.get("reason", ""), "domain_status": verdict.get("domain_status", {}),
                            "material_contradictions": verdict.get("material_contradictions", [])}, indent=1)}</judge_verdict>
<claim_checks>{json.dumps(checks, indent=1)}</claim_checks>
<domain_summaries>{json.dumps(state.get("domain_summaries", {}), indent=1)}</domain_summaries>
<evidence_gaps>{json.dumps(state.get("evidence_gaps", []), indent=1)}</evidence_gaps>
<unresolved_questions>{json.dumps(state.get("unresolved_questions", []), indent=1)}</unresolved_questions>
{evidence_block(state.get("evidence", []), max_excerpt_chars=250)}"""
    if first is not None:
        content += f"\n<sections_1_to_4>{json.dumps(first.model_dump(mode='json'), indent=1)}</sections_1_to_4>"
    if mode:
        previous = ProblemBrief.model_validate(state["brief"]).model_dump(mode="json", include=set(part.model_fields))
        content += f"""
<previous_draft>{json.dumps(previous, indent=1)}</previous_draft>
<validation_issues>{json.dumps(_issues(state, mode), indent=1)}</validation_issues>"""
    return content


def brief_writer_node(state: ArenaState) -> dict:
    settings = get_settings()
    mode = revision_mode(state)
    revision = state["brief"]["revision"] + 1 if state.get("brief") else 0
    if mode == "validator":
        failed = sum(1 for c in state["brief_validation"]["checks"] if not c["passed"])
        report("brief_writer", f"revising the brief (draft {revision + 1}) to fix {failed} issue(s) the validator found")
    elif mode == "user":
        report("brief_writer", f"revising the brief (draft {revision + 1}) with your change request")
    else:
        report("brief_writer", "writing the problem statement and solution brief")

    system = SYSTEM_PROMPT.replace("{word_budget}", str(settings.brief_word_budget)).replace(
        "{word_target}", str(int(settings.brief_word_budget * 0.8)))
    system += {"validator": REVISION_NOTE, "user": USER_REVISION_NOTE}.get(mode or "", "")

    def write(part: type, first: BriefPartOne | None = None):
        return call_structured(part, system + PART_NOTE[part], _user_content(state, mode, part, first),
                               max_tokens=PART_MAX_TOKENS[part], run_name=f"brief_writer_{part.__name__}")

    first = write(BriefPartOne)
    report("brief_writer", "sections 1-4 written; writing requirements, architecture, scope, success criteria and risks")
    with ContextThreadPoolExecutor(max_workers=2) as pool:
        second, third = pool.map(lambda part: write(part, first), (BriefPartTwo, BriefPartThree))
    content = BriefContent(**first.model_dump(), **second.model_dump(), **third.model_dump())

    evidence = state.get("evidence", [])
    for note in normalize(content, evidence):
        report("brief_writer", f"label fixed: {note}")
    brief = ProblemBrief(**content.model_dump(), project_name=state.get("project_name", ""), revision=revision,
                         references=assemble_references(content, evidence))
    markdown, words = render_brief_markdown(brief, brief_alternatives(state), word_budget=settings.brief_word_budget)
    report("brief_writer", f"brief drafted: {words} words in sections 1-9, {len(brief.references)} reference(s)")
    return {
        "brief": brief.model_dump(mode="json"),
        "brief_markdown": markdown,
        "status": "validating_brief",
        "current_node": "brief_writer",
    }
