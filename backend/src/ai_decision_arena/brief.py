"""The problem statement + solution brief, in pure Python (no LLM): references, label normalisation, markdown
rendering and the deterministic validation checks. Used by nodes/brief_writer.py and nodes/brief_validator.py.

Trust boundaries kept here:
- References (spec §4.10) are built ONLY from evidence records the brief cites by id; titles and URLs come from the
  evidence (i.e. from real search hits), never from the writer.
- "verified" is a fact owned by the Evidence Checker: an item labelled verified whose cited evidence was not
  verified is downgraded to research_backed.
- A technology is shown as mandatory only when the user required it (label user_provided).
- The one-page budget is enforced by the renderer first: each list shows its first few items in the main part and
  the rest moves to the appendix; when the page is still over budget, the caps shrink level by level (never below
  the floors: the MVP, the scope and the user journey always stay in the main part). Only a brief that is too long
  at the smallest caps fails the word-budget check (and costs a rewrite).
"""

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

# How many items of each list the main part shows; the rest goes to the appendix.
MAIN_CAPS = {
    "audience": 3, "current_alternatives": 3, "consequences": 2, "indicators": 2,
    "findings": 2, "limitations": 2, "gaps": 3,
    "mvp": 6, "future": 4, "journey": 6, "why": 2,
    "functional": 4, "non_functional": 3, "acceptance": 3,
    "components": 5, "technologies": 5, "decisions": 2,
    "in_scope": 5, "out_of_scope": 4, "deliverables": 4, "dependencies": 3,
    "success": 4, "constraints": 4, "assumptions": 3, "questions": 3, "risks": 3,
}
# What always stays in the main part, however tight the page (spec §4: prioritise problem, evidence, solution,
# essential features, architecture, success criteria). Every other list keeps at least one item.
CAP_FLOORS = {"mvp": 6, "journey": 6, "in_scope": 5, "functional": 3, "success": 2, "components": 3, "risks": 2}
CAP_LEVELS = (1.0, 0.75, 0.5, 0.0)       # tried in order until sections 1-9 fit the word budget


def caps_at(level: float) -> dict[str, int]:
    return {k: min(n, max(CAP_FLOORS.get(k, 1), round(n * level))) for k, n in MAIN_CAPS.items()}


class _Renderer:
    def __init__(self, brief: ProblemBrief, caps: dict[str, int]):
        self.caps = caps
        self.refs = {r.evidence_id: r for r in brief.references}
        self.appendix: list[tuple[str, list[str]]] = []

    def cite(self, ids: list[str]) -> str:
        return "".join(f" [[{self.refs[i].number}]]({self.refs[i].url})" for i in ids if i in self.refs).strip()

    def tag(self, label: str, ids: list[str]) -> str:
        cites = self.cite(ids)
        return f"_({LABEL_TEXT[label]}{' ' + cites if cites else ''})_"

    def item(self, it: BriefItem) -> str:
        return f"{it.text.strip()} {self.tag(it.label, it.evidence_ids)}"

    def split(self, title: str, lines: list[str], cap: str) -> list[str]:
        n = self.caps[cap]
        if len(lines) > n:
            self.appendix.append((title, [self.item(x) if isinstance(x, BriefItem) else x for x in lines[n:]]))
        return lines[:n]


def _bullets(lines: list[str]) -> list[str]:
    return [f"- {line}" for line in lines]


def _inline(lines: list[str], sep: str = " · ") -> str:
    return sep.join(lines)


def render_brief_markdown(brief: ProblemBrief, alternatives: list[dict] | None = None,
                          open_issues: list[str] | None = None, word_budget: int | None = None) -> tuple[str, int]:
    """Markdown of the whole brief and the word count of sections 1-9 (the one-page budget).
    alternatives: [{name, summary, weighted_total}] of the proposals that did not win (appendix B).
    word_budget: shrink the main-part caps level by level until sections 1-9 fit (overflow → appendix)."""
    for level in CAP_LEVELS:
        markdown, words = _render(brief, alternatives, open_issues, caps_at(level))
        if word_budget is None or words <= word_budget:
            break
    return markdown, words


def _render(brief: ProblemBrief, alternatives: list[dict] | None, open_issues: list[str] | None,
            caps: dict[str, int]) -> tuple[str, int]:
    r = _Renderer(brief, caps)
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
    out += _bullets([f"**Users:** " + _inline([r.item(i) for i in r.split("Users", ov.audience, "audience")], "; "),
                     f"**Context:** {r.item(ov.context)}"]) + [""]

    out += [f"## {SECTION_TITLES['problem_statement']}", r.item(ps.statement), ""]
    lines = [f"**Who and where:** {r.item(ps.who_and_context)}"]
    lines += [f"**Today:** {r.item(i)}" for i in r.split("How users cope today", ps.current_alternatives, "current_alternatives")]
    lines += [f"**Gap:** {r.item(ps.gap)}"]
    lines += [f"**If unresolved:** {r.item(i)}" for i in r.split("Consequences", ps.consequences, "consequences")]
    lines += [f"**Indicator:** {r.item(i)}" for i in r.split("Indicators", ps.indicators, "indicators")]
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['research_findings']}"]
    for label, items in (("Existing apps and user feedback", rf.apps_and_feedback),
                         ("Papers and technical literature", rf.papers_and_literature),
                         ("Feasibility and implementations", rf.feasibility_and_implementations)):
        shown = r.split(label, [r.item(i) for i in items], "findings")
        out += [f"**{label}**"] + (_bullets(shown) if shown else ["- No usable evidence found in this domain."])
    out += ["**Limitations of existing solutions and the opportunity**"]
    out += _bullets(r.split("Limitations and opportunity", [r.item(i) for i in rf.limitations_and_opportunity], "limitations"))
    gaps = r.split("Evidence gaps", rf.evidence_gaps, "gaps")
    if gaps:
        out += [f"**Evidence gaps:** {_inline(gaps, '; ')}"]
    out += [""]

    out += [f"## {SECTION_TITLES['proposed_solution']}", r.item(sol.how_it_addresses_problem), ""]
    lines = [f"**First version (MVP):** {_inline(r.split('MVP features', sol.mvp_features, 'mvp'))}"]
    if sol.future_enhancements:
        lines.append(f"**Later:** {_inline(r.split('Future enhancements', sol.future_enhancements, 'future'))}")
    lines.append(f"**User journey:** {_inline(r.split('User journey (continued)', sol.user_journey, 'journey'), ' → ')}")
    lines += [f"**Why this approach:** {r.item(i)}" for i in r.split("Why this approach", sol.why_this_approach, "why")]
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['requirements']}", "**Functional**"]
    out += _bullets(r.split("Functional requirements", [r.item(i) for i in req.functional], "functional"))
    out += ["**Non-functional**"]
    out += _bullets(r.split("Non-functional requirements",
                            [f"{i.category.capitalize()}: {r.item(i)}" for i in req.non_functional], "non_functional"))
    if req.acceptance_criteria:
        out += ["**Acceptance criteria**"] + _bullets(r.split("Acceptance criteria", req.acceptance_criteria, "acceptance"))
    if req.integrations_and_data:
        r.appendix.append(("Integrations, data inputs and outputs", req.integrations_and_data))
    if req.user_roles:
        r.appendix.append(("User roles", req.user_roles))
    out += [""]

    out += [f"## {SECTION_TITLES['architecture']}", r.item(arch.overview), ""]
    comps = r.split("Components", [f"**{c.name}:** {c.responsibility}" for c in arch.components], "components")
    lines = comps + [f"**Data flow:** {arch.data_flow.strip()}"]
    techs = [f"{t.name} ({'required by you' if t.required_by_user else 'recommended'}): {t.purpose} {r.tag(t.label, t.evidence_ids)}"
             for t in arch.technologies]
    lines += [f"**Technology:** {t}" for t in r.split("Technologies", techs, "technologies")]
    lines += [f"**Decision:** {r.item(i)}" for i in r.split("Architectural decisions", arch.key_decisions, "decisions")]
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['scope']}"]
    lines = [f"**In scope:** {_inline(r.split('In scope', sc.in_scope, 'in_scope'))}",
             f"**Out of scope:** {_inline(r.split('Out of scope', sc.out_of_scope, 'out_of_scope'))}",
             f"**Deliverables:** {_inline(r.split('Deliverables', sc.deliverables, 'deliverables'))}"]
    lines += [f"**Depends on:** {r.item(i)}" for i in r.split("Dependencies", sc.dependencies, "dependencies")]
    out += _bullets(lines) + [""]

    out += [f"## {SECTION_TITLES['success_criteria']}", "| Outcome | Target | How it is measured |", "|---|---|---|"]
    rows = []
    for c in brief.success_criteria:
        target = (f"{c.target} {r.tag('user_provided' if c.basis == 'user_requirement' else 'research_backed', c.evidence_ids)}"
                  if c.target else "no target yet (no baseline)")
        rows.append(f"| {_cell(c.metric)} | {_cell(target)} | {_cell(c.evaluation_method)} |")
    out += r.split("More success criteria", rows, "success") + [""]

    out += [f"## {SECTION_TITLES['constraints_and_risks']}"]
    lines = [f"**Constraint:** {r.item(i)}" for i in r.split("Constraints", cr.constraints, "constraints")]
    lines += [f"**Assumption:** {a}" for a in r.split("Assumptions", cr.assumptions, "assumptions")]
    lines += [f"**Open question:** {q}" for q in r.split("Open questions", cr.unresolved_questions, "questions")]
    risks = [f"**Risk ({k.category}):** {k.risk.strip()} **Mitigation:** {k.mitigation.strip()}"
             + (f" {r.cite(k.evidence_ids)}" if r.cite(k.evidence_ids) else "") for k in cr.risks]
    lines += r.split("More risks", risks, "risks")
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

    appendix = [(f"A{n}. {title}", _bullets(lines)) for n, (title, lines) in enumerate(r.appendix, start=1)]
    if alternatives:
        appendix.append(("B. Alternatives considered", _bullets([
            f"**{a['name']}**" + (f" (score {a['weighted_total']:.1f}/10)" if a.get("weighted_total") is not None else "")
            + f": {a['summary']}" for a in alternatives])))
    if open_issues:
        appendix.append(("C. Validation notes (not resolved in this draft)", _bullets(open_issues)))
    if appendix:
        out += ["---", "## Appendix", ""]
        for title_, lines in appendix:
            out += [f"### {title_}"] + lines + [""]
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

    over = word_count - word_budget
    add("det_word_budget", [f"{word_count} words in sections 1-9, budget {word_budget}"] if over > 0 else [],
        f"Shorten sections 1-9 by about {max(over, 0)} words: one sentence per item, fewer items, no repetition.",
        severity="medium")
    return checks
