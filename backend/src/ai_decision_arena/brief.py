"""The problem statement + solution brief, in pure Python (no LLM): references, label normalisation, markdown
rendering and the deterministic validation checks. Used by nodes/brief_writer.py and nodes/brief_validator.py.

Trust boundaries kept here:
- References (spec §4.10) are built ONLY from evidence records the brief cites by id; titles and URLs come from the
  evidence (i.e. from real search hits), never from the writer.
- "verified" is a fact owned by the Evidence Checker: an item labelled verified whose cited evidence was not
  verified is downgraded to research_backed.
- A technology is shown as mandatory only when the user required it (label user_provided).
- No appendix (user decision, 2026-10-29): every item the writer produced is on the page, in its section; the
  alternatives considered sit in section 4, integrations and user roles in section 5, validation notes at the end
  of section 9. Length is the writer's job (prompt: every extra item costs the reader; word budget 1500) and the
  validator's check (word-budget check at 10% tolerance), never the renderer's trimming.
"""

import hashlib
import re
from datetime import datetime

from pydantic import BaseModel

from ai_decision_arena.schemas import (
    CITED_LABELS,
    DOMAIN_LABELS,
    BriefContent,
    BriefItem,
    BriefReference,
    ProblemBrief,
    Risk,
    SuccessCriterion,
    TechnologyChoice,
    ValidationCheck,
)

SECTION_TITLES = {
    "project_overview": "1. Project overview",
    "problem_statement": "2. Problem statement",
    "research_findings": "3. Research findings and evidence",
    "proposed_solution": "4. Proposed solution",
    "requirements": "5. Functional and non-functional requirements",
    "architecture": "6. Proposed architecture and technology",
    "scope": "7. Scope and deliverables",
    "success_criteria": "8. Success criteria",
    "constraints_and_risks": "9. Constraints, assumptions and risks",
    "references": "10. References",
}
SECTION_KEYS = tuple(k for k in SECTION_TITLES if k != "references")

LABEL_TEXT = {
    "verified": "verified",
    "research_backed": "research",
    "user_provided": "you said",
    "recommendation": "recommended",
    "assumption": "assumption",
}
SHORT_DOMAIN = {"apps": "Existing apps and user feedback", "papers": "Papers and literature", "tech": "Technical feasibility"}

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
WORD_RE = re.compile(r"[A-Za-z0-9][\w'’.-]*")
ANNOTATION_RE = re.compile(r"_\((?:%s)\s*\)_" % "|".join(re.escape(t) for t in LABEL_TEXT.values()))
LINK_RE = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\([^)]*\)")     # [text](url), text may be "[2]"
CITED = (BriefItem, TechnologyChoice, SuccessCriterion, Risk)


# --- walking the brief -------------------------------------------------------------------------------------

def cited_objects(content: BriefContent):
    """Yield (section_key, object) for every object that carries evidence_ids, in document order."""
    def walk(section: str, value):
        if isinstance(value, CITED):
            yield section, value
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                yield from walk(section, getattr(value, name))
        elif isinstance(value, list):
            for v in value:
                yield from walk(section, v)
    for key in SECTION_KEYS:
        yield from walk(key, getattr(content, key))


def all_strings(content: BriefContent) -> list[str]:
    out: list[str] = []
    def walk(value):
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(content.model_dump(include=set(SECTION_KEYS)))
    return out


# --- normalisation + references (Python owns these facts) ---------------------------------------------------

def normalize(content: BriefContent, evidence: list[dict]) -> list[str]:
    """Fix labels in place where Python knows better. Returns what was changed (for the progress log)."""
    status = {e["evidence_id"]: e.get("verification_status", "pending") for e in evidence}
    notes: list[str] = []
    for _, obj in cited_objects(content):
        label = getattr(obj, "label", None)
        if label == "verified" and not any(status.get(i) == "verified" for i in obj.evidence_ids):
            obj.label = "research_backed"
            notes.append(f"'verified' → research_backed (no verified source): {_short(obj)}")
        if isinstance(obj, TechnologyChoice) and obj.required_by_user and obj.label != "user_provided":
            obj.required_by_user = False
            notes.append(f"{obj.name}: shown as a recommendation (the user did not require it)")
    return notes


def assemble_references(content: BriefContent, evidence: list[dict]) -> list[BriefReference]:
    """Numbered by first citation; only ids that exist in the evidence; title/URL copied from the evidence."""
    by_id = {e["evidence_id"]: e for e in evidence}
    order: dict[str, list[str]] = {}
    for section, obj in cited_objects(content):
        for eid in obj.evidence_ids:
            if eid in by_id:
                sections = order.setdefault(eid, [])
                if section not in sections:
                    sections.append(section)
    return [
        BriefReference(number=n, evidence_id=eid, title=by_id[eid]["source_title"], url=by_id[eid]["source_url"],
                       domain=by_id[eid]["domain"], source_type=by_id[eid]["source_type"],
                       verification_status=by_id[eid].get("verification_status", "pending"), cited_in=sections)
        for n, (eid, sections) in enumerate(order.items(), start=1)
    ]


# --- rendering -----------------------------------------------------------------------------------------------

WORD_BUDGET_TOLERANCE = 1.10              # det_word_budget fails only above budget × this


class _Renderer:
    def __init__(self, brief: ProblemBrief):
        self.refs = {r.evidence_id: r for r in brief.references}

    def cite(self, ids: list[str]) -> str:
        return "".join(f" [[{self.refs[i].number}]]({self.refs[i].url})" for i in ids if i in self.refs).strip()

    def tag(self, label: str, ids: list[str]) -> str:
        cites = self.cite(ids)
        return f"_({LABEL_TEXT[label]}{' ' + cites if cites else ''})_"

    def item(self, it: BriefItem) -> str:
        return f"{it.text.strip()} {self.tag(it.label, it.evidence_ids)}"

    def items(self, title: str, lines: list, cap: str = "") -> list:
        """Every item, in order (the renderer used to keep the first few here and move the rest to an appendix)."""
        return list(lines)


def _bullets(lines: list[str]) -> list[str]:
    return [f"- {line}" for line in lines]


def _inline(lines: list[str], sep: str = " · ") -> str:
    return sep.join(lines)


def render_brief_markdown(brief: ProblemBrief, alternatives: list[dict] | None = None,
                          open_issues: list[str] | None = None, word_budget: int | None = None) -> tuple[str, int]:
    """Markdown of the whole brief and the word count of sections 1-9 (the writer's budget).
    alternatives: [{name, summary, weighted_total}] of the proposals that did not win (shown in section 4).
    open_issues: the validator's unresolved notes (shown at the end of section 9).
    word_budget: accepted for the callers' sake; nothing is trimmed any more (no appendix since 2026-10-29)."""
    return _render(brief, alternatives, open_issues)


def _render(brief: ProblemBrief, alternatives: list[dict] | None, open_issues: list[str] | None) -> tuple[str, int]:
    r = _Renderer(brief)
    out: list[str] = []
    ov, ps, rf, sol = brief.project_overview, brief.problem_statement, brief.research_findings, brief.proposed_solution
    req, arch, sc, cr = brief.requirements, brief.architecture, brief.scope, brief.constraints_and_risks
    title = brief.project_overview.proposed_name.strip() or brief.project_name.strip().capitalize() or "Your project"

    out += [f"# {title}",
            f"*Problem statement and solution brief · draft {brief.revision + 1} · {_date(brief.generated_at)}*", "",
            "> Each statement says where it comes from: **verified** (checked against its source) · **research** "
            "(from the research) · **you said** · **recommended** (our recommendation) · **assumption** (not confirmed). "
            "Numbers link to the references.", ""]

    out += [f"## {SECTION_TITLES['project_overview']}", ov.description.strip(), ""]
    out += _bullets([f"**Users:** " + _inline([r.item(i) for i in r.items("Users", ov.audience, "audience")], "; "),
                     f"**Context:** {r.item(ov.context)}"]) + [""]

    out += [f"## {SECTION_TITLES['problem_statement']}", r.item(ps.statement), ""]
    lines = [f"**Who and where:** {r.item(ps.who_and_context)}"]
    lines += [f"**Today:** {r.item(i)}" for i in r.items("How users cope today", ps.current_alternatives, "current_alternatives")]
    lines += [f"**Gap:** {r.item(ps.gap)}"]
    lines += [f"**If unresolved:** {r.item(i)}" for i in r.items("Consequences", ps.consequences, "consequences")]
    lines += [f"**Indicator:** {r.item(i)}" for i in r.items("Indicators", ps.indicators, "indicators")]
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['research_findings']}"]
    for label, items in (("Existing apps and user feedback", rf.apps_and_feedback),
                         ("Papers and technical literature", rf.papers_and_literature),
                         ("Feasibility and implementations", rf.feasibility_and_implementations)):
        shown = r.items(label, [r.item(i) for i in items], "findings")
        out += ["", f"**{label}**", ""] + (_bullets(shown) if shown else ["- No usable evidence found in this domain."])
    out += ["", "**Limitations of existing solutions and the opportunity**", ""]
    out += _bullets(r.items("Limitations and opportunity", [r.item(i) for i in rf.limitations_and_opportunity], "limitations"))
    gaps = r.items("Evidence gaps", rf.evidence_gaps, "gaps")
    if gaps:
        out += ["", f"**Evidence gaps:** {_inline(gaps, '; ')}"]
    out += [""]

    out += [f"## {SECTION_TITLES['proposed_solution']}", r.item(sol.how_it_addresses_problem), ""]
    lines = [f"**First version (MVP):** {_inline(r.items('MVP features', sol.mvp_features, 'mvp'))}"]
    if sol.future_enhancements:
        lines.append(f"**Later:** {_inline(r.items('Future enhancements', sol.future_enhancements, 'future'))}")
    lines.append(f"**User journey:** {_inline(r.items('User journey (continued)', sol.user_journey, 'journey'), ' → ')}")
    lines += [f"**Why this approach:** {r.item(i)}" for i in r.items("Why this approach", sol.why_this_approach, "why")]
    if alternatives:
        lines.append("**Alternatives considered:** " + _inline([
            f"{a['name']}" + (f" (score {a['weighted_total']:.1f}/10)" if a.get("weighted_total") is not None else "")
            + f": {a['summary']}" for a in alternatives], "; "))
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['requirements']}", "", "**Functional**", ""]
    out += _bullets(r.items("Functional requirements", [r.item(i) for i in req.functional], "functional"))
    out += ["", "**Non-functional**", ""]
    out += _bullets(r.items("Non-functional requirements",
                            [f"{i.category.capitalize()}: {r.item(i)}" for i in req.non_functional], "non_functional"))
    if req.acceptance_criteria:
        out += ["", "**Acceptance criteria**", ""] + _bullets(r.items("Acceptance criteria", req.acceptance_criteria, "acceptance"))
    if req.integrations_and_data:
        out += ["", "**Integrations, data inputs and outputs**", ""] + _bullets(req.integrations_and_data)
    if req.user_roles:
        out += ["", "**User roles**", ""] + _bullets(req.user_roles)
    out += [""]

    out += [f"## {SECTION_TITLES['architecture']}", r.item(arch.overview), ""]
    comps = r.items("Components", [f"**{c.name}:** {c.responsibility}" for c in arch.components], "components")
    lines = comps + [f"**Data flow:** {arch.data_flow.strip()}"]
    techs = [f"{t.name} ({'required by you' if t.required_by_user else 'recommended'}): {t.purpose} {r.tag(t.label, t.evidence_ids)}"
             for t in arch.technologies]
    lines += [f"**Technology:** {t}" for t in r.items("Technologies", techs, "technologies")]
    lines += [f"**Decision:** {r.item(i)}" for i in r.items("Architectural decisions", arch.key_decisions, "decisions")]
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['scope']}"]
    lines = [f"**In scope:** {_inline(r.items('In scope', sc.in_scope, 'in_scope'))}",
             f"**Out of scope:** {_inline(r.items('Out of scope', sc.out_of_scope, 'out_of_scope'))}",
             f"**Deliverables:** {_inline(r.items('Deliverables', sc.deliverables, 'deliverables'))}"]
    lines += [f"**Depends on:** {r.item(i)}" for i in r.items("Dependencies", sc.dependencies, "dependencies")]
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['success_criteria']}", "", "| Outcome | Target | How it is measured |", "|---|---|---|"]
    rows, lines = [], []
    for c in brief.success_criteria:
        target = (f"{c.target} {r.tag('user_provided' if c.basis == 'user_requirement' else 'research_backed', c.evidence_ids)}"
                  if c.target else "no target yet (no baseline)")
        rows.append(f"| {_cell(c.metric)} | {_cell(target)} | {_cell(c.evaluation_method)} |")
        lines.append(f"{c.metric.strip()}: {target}. Measured by: {c.evaluation_method.strip()}")
    out += rows + [""]

    out += [f"## {SECTION_TITLES['constraints_and_risks']}"]
    lines = [f"**Constraint:** {r.item(i)}" for i in r.items("Constraints", cr.constraints, "constraints")]
    lines += [f"**Assumption:** {a}" for a in r.items("Assumptions", cr.assumptions, "assumptions")]
    lines += [f"**Open question:** {q}" for q in r.items("Open questions", cr.unresolved_questions, "questions")]
    risks = [f"**Risk ({k.category}):** {k.risk.strip()} **Mitigation:** {k.mitigation.strip()}"
             + (f" {r.cite(k.evidence_ids)}" if r.cite(k.evidence_ids) else "") for k in cr.risks]
    lines += r.items("More risks", risks, "risks")
    lines += [f"**Validation note (not resolved in this draft):** {i}" for i in (open_issues or [])]
    out += _bullets(lines) + [""]

    word_count = count_words("\n".join(out[out.index(f"## {SECTION_TITLES['project_overview']}"):]))

    out += [f"## {SECTION_TITLES['references']}"]
    if brief.references:
        out += [f"{ref.number}. [{_cell(_title(ref.title))}]({ref.url}) · {SHORT_DOMAIN.get(ref.domain, ref.domain)} · "
                f"{ref.verification_status.replace('_', ' ')}" for ref in brief.references]
        out += ["", "_Statements marked verified or research cite these sources; statements marked recommended or "
                    "assumption are the agents' judgement, not sourced facts._"]
    else:
        out += ["No sources are cited: every statement is the user's information, a recommendation or an assumption."]
    out += [""]

    return "\n".join(out).rstrip() + "\n", word_count


def count_words(markdown: str) -> int:
    """Words a reader reads: label tags, citation numbers and URLs are not counted."""
    text = URL_RE.sub(" ", LINK_RE.sub(r"\1", markdown))       # [[2]](url) -> [2]
    text = re.sub(r"\[\d+\]", " ", text)
    text = ANNOTATION_RE.sub(" ", text)                         # _(research   )_ -> nothing
    return len(WORD_RE.findall(text))


def _cell(text: str) -> str:
    return " ".join(str(text).replace("|", "/").split())


def _title(title: str, limit: int = 90) -> str:
    """Search-hit titles are sometimes several page titles glued together: keep the first, readable part."""
    title = " ".join(title.split())
    return title if len(title) <= limit else title[:limit].rsplit(" ", 1)[0] + "…"


def _date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _short(obj) -> str:
    text = getattr(obj, "text", None) or getattr(obj, "name", None) or getattr(obj, "metric", None) or getattr(obj, "risk", "")
    return text[:80]


# --- deterministic validation (spec §5, run before the LLM review) -------------------------------------------

def deterministic_checks(brief: ProblemBrief, evidence: list[dict], word_count: int, word_budget: int) -> list[ValidationCheck]:
    known = {e["evidence_id"] for e in evidence}
    known_urls = {str(e["source_url"]).rstrip("/") for e in evidence}
    checks: list[ValidationCheck] = []

    def add(check_id: str, problems: list[str], fix: str, severity: str = "high") -> None:
        checks.append(ValidationCheck(check_id=check_id, source="deterministic", passed=not problems,
                                      severity=severity if problems else "low",
                                      issue="; ".join(problems[:6]) + (f" (+{len(problems) - 6} more)" if len(problems) > 6 else ""),
                                      fix_instruction=fix if problems else ""))

    cited = list(cited_objects(brief))
    unknown = sorted({i for _, obj in cited for i in obj.evidence_ids if i not in known})
    add("det_known_evidence_ids", [f"unknown evidence id {i}" for i in unknown],
        f"Cite only ids that appear in <evidence>; remove {', '.join(unknown[:8])}.")

    uncited = [f"{s}: '{_short(o)}' is labelled {o.label} without evidence ids" for s, o in cited
               if getattr(o, "label", None) in CITED_LABELS and not [i for i in o.evidence_ids if i in known]]
    add("det_cited_labels_have_evidence", uncited,
        "Every verified / research_backed statement must cite at least one evidence id; otherwise label it "
        "recommendation, assumption or user_provided.")

    bad_targets = []
    for c in brief.success_criteria:
        has_number = bool(c.target and re.search(r"\d", c.target))
        if has_number and c.basis not in ("user_requirement", "evidence"):
            bad_targets.append(f"'{c.metric}' has numeric target {c.target!r} without a basis")
        if c.basis == "evidence" and not [i for i in c.evidence_ids if i in known]:
            bad_targets.append(f"'{c.metric}' has basis evidence but cites no known evidence id")
    add("det_targets_have_basis", bad_targets,
        "Give a numeric target only when the user's requirements or cited evidence justify it; otherwise set target to null.")

    missing = []
    if not brief.project_overview.description.strip() or not brief.project_overview.audience:
        missing.append("1. project overview (description and audience)")
    if not brief.problem_statement.statement.text.strip():
        missing.append("2. problem statement")
    rf = brief.research_findings
    if not (rf.apps_and_feedback or rf.papers_and_literature or rf.feasibility_and_implementations):
        missing.append("3. research findings")
    if not brief.proposed_solution.mvp_features:
        missing.append("4. proposed solution (MVP features)")
    if not brief.requirements.functional:
        missing.append("5. functional requirements")
    if not brief.architecture.components or not brief.architecture.technologies:
        missing.append("6. architecture (components and technologies)")
    if not brief.scope.in_scope or not brief.scope.out_of_scope:
        missing.append("7. scope (in and out of scope)")
    if not brief.success_criteria:
        missing.append("8. success criteria")
    if not brief.constraints_and_risks.risks:
        missing.append("9. risks")
    if not brief.references:
        missing.append("10. references (no known evidence id is cited anywhere)")
    add("det_sections_present", [f"missing or empty: {m}" for m in missing], "Fill every section of the brief.")

    urls = sorted({u.rstrip(".,;:/") for s in all_strings(brief) for u in URL_RE.findall(s)})
    foreign = [u for u in urls if u.rstrip("/") not in known_urls]
    add("det_no_unknown_urls", [f"URL not in the evidence: {u}" for u in foreign],
        "Do not write URLs in the text; cite evidence ids instead (the references are added automatically).")

    # "Approximately one page" (spec §4): 10% over the budget passes; the renderer already moved what it could.
    limit = int(word_budget * WORD_BUDGET_TOLERANCE)
    over = word_count - word_budget
    add("det_word_budget", [f"{word_count} words in sections 1-9, budget {word_budget} (limit {limit})"] if word_count > limit else [],
        f"Shorten sections 1-9 by about {max(over, 0)} words: at most ~20 words per item, fewer items, no repetition.",
        severity="medium")
    return checks


# --- approval ------------------------------------------------------------------------------------------------

def brief_hash(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def brief_is_approved(state: dict) -> bool:
    """True only if the user approved EXACTLY the brief in the state now (any later edit invalidates the approval).
    The planner / implementer routes check this, not only the UI."""
    digest = state.get("brief_approved_hash")
    return bool(state.get("brief_approved_at") and digest and digest == brief_hash(state.get("brief_markdown", "")))
