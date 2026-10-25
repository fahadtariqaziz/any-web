"""Shared test fixtures: no network, no database, no real API keys.

- Environment defaults are set BEFORE the package is imported, so Settings never needs backend/.env and never
  touches the real database (DATABASE_URL points at a port nobody listens on; PERSIST_RESULTS=false).
- `fake_llm` replaces `llm.call_structured` in every module that imported it by name. The fake builds a VALID
  instance of the requested Pydantic schema from the prompt text (plan ids, evidence ids, source indexes), so the
  nodes' own Python (id filtering, weighted totals, routing) runs for real while Claude is never called.
- `fake_search` replaces the Tavily call with canned hits, one small set per query.
- `graph` builds the real graph on an InMemorySaver.
"""

import os
import re

# --- 1) environment first (before any ai_decision_arena import) -------------------------------------------
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
os.environ.setdefault("TAVILY_API_KEY", "test-key-not-used")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["PERSIST_RESULTS"] = "false"
os.environ["CHECK_INS_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "postgresql://test:test@127.0.0.1:1/never_connected"
# Generated projects of the pipeline tests go to a throwaway folder, never the repo's generated_projects/.
import tempfile  # noqa: E402
os.environ["GENERATED_PROJECTS_DIR"] = tempfile.mkdtemp(prefix="ai-builder-tests-")

import pytest  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from ai_decision_arena import schemas as S  # noqa: E402
from ai_decision_arena.config import get_settings  # noqa: E402
from ai_decision_arena.pricing import Tokens  # noqa: E402
from ai_decision_arena.usage import record  # noqa: E402

# Modules that call call_structured by name (one list for tests, evals and fake_api: evals.LLM_USERS).
from ai_decision_arena.evals import LLM_USERS  # noqa: E402

PROPOSAL_ID_RE = re.compile(r'<proposal id="(proposal_[a-c])"')
EVIDENCE_ID_RE = re.compile(r'<item id="(ev_\d+)"')
SOURCE_RE = re.compile(r'<source index="(\d+)" type="([a-z_]+)" domain="([a-z]+)"')


def tag(name: str, text: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    return m.group(1).strip() if m else ""


# --- 2) builders: one valid instance per schema, derived from the prompt --------------------------------------

def build_intake(system: str, user: str) -> S.IntakeResult:
    question = tag("question", user)
    return S.IntakeResult(
        is_app_request=True,
        project_name=question.lower()[:40] or "untitled project",
        project_category="other",
        idea_summary=f"The user wrote: {question}",
        project_profile=[],
        requested_features=[],
        constraints=[],
        missing_information=["target users", "must-have features"],
        risk_flags=[],
    )


def build_clarification(system: str, user: str) -> S.ClarificationResult:
    rounds_used = int(tag("rounds_used", user) or 0)
    can_ask_more = tag("can_ask_more", user) == "true"
    ask = rounds_used == 0 and can_ask_more
    return S.ClarificationResult(
        need_clarification=ask,
        questions=["Who are the main users of this app?", "Which features must the first version have?"] if ask else [],
        reason="first round" if ask else "enough information",
        new_profile_facts=[S.NamedValue(name="audience", value="university students")] if rounds_used else [],
        new_features=[],
        new_constraints=[],
        new_risk_flags=[],
        withdrawn_risk_flags=[],
        refined_project_name="",
        refined_idea_summary="",
        assumptions=[] if ask else ["Assumed a web app without user accounts."],
    )


def build_research_plan(system: str, user: str) -> S.ResearchPlan:
    term = tag("project", user) or "project"
    return S.ResearchPlan(
        search_term=term,
        queries=[
            S.SearchQuery(query=f"{term} reviews complaints", domain="apps", topic="user_complaints", preferred_domains=[]),
            S.SearchQuery(query=f"{term} study approaches", domain="papers", topic="established_approaches", preferred_domains=[]),
            S.SearchQuery(query=f"{term} open source implementation", domain="tech", topic="feasibility_and_risks", preferred_domains=[]),
        ],
    )


def build_extraction(system: str, user: str) -> S.ExtractionResult:
    sources = SOURCE_RE.findall(user)
    evidence = []
    for index, source_type, domain in sources:
        evidence.append(S.ExtractedEvidence(
            source_index=int(index),
            domain=domain,
            source_type=source_type,
            evidence_strength="unknown",
            relevant_excerpt=f"Paraphrased finding from source {index}.",
            is_direct_quote=False,
            claims_supported=[f"claim {index}"],
            limitations=[],
            feedback_context=(S.FeedbackContext(product="SomeApp", feedback_type="complaint",
                                                experience_described="sync keeps failing", is_recurring=False,
                                                context="", relevant_to_idea=True)
                              if domain == "apps" else None),
            sentiment="negative" if domain == "apps" else None,
            relevance_score=0.8,
            reliability_notes="test source",
        ))
    return S.ExtractionResult(
        evidence=evidence, rejected=[], summary="What this domain says.", opportunity_note="Nobody does offline well.",
        evidence_gaps=[], conflicting_claims=[],
    )


def _solution(name: str, ids: list[str]) -> S.ProposedSolution:
    return S.ProposedSolution(
        name=name, summary="A solution.", problem_addressed="Students lose track of their habits.", target_users="students",
        core_features=["track habits", "daily reminder"], future_features=["sharing"], user_journey=["open the app", "tick a habit"],
        architecture=S.ArchitectureSketch(frontend="Next.js", backend="none (static)", database="localStorage",
                                          external_services=[], ai_components="none"),
        technologies=["Next.js (user prefers it)"], how_it_beats_alternatives="Works offline.", benefits=["simple"],
        drawbacks_risks=["no sync"], assumptions=[], difficulty="low", feasibility_notes="Feasible.",
        security_privacy_notes="none needed", supporting_evidence_ids=ids, evidence_gaps=[],
    )


def build_proposer(system: str, user: str) -> S.ProposerOutput:
    ids = EVIDENCE_ID_RE.findall(user)
    if not ids:
        return S.ProposerOutput(proposals=[], why_fewer_than_two="no evidence", evidence_too_thin=True)
    proposals = [_solution("Lean first version", ids[:1]), _solution("Differentiated product", ids[:1])]
    if "QUICK SESSION" in system:
        proposals = proposals[:1]
    return S.ProposerOutput(proposals=proposals, why_fewer_than_two="quick session" if len(proposals) < 2 else "",
                            evidence_too_thin=False)


def build_critic(system: str, user: str) -> S.Criticism:
    ids = PROPOSAL_ID_RE.findall(user)
    return S.Criticism(
        proposal_id=ids[0] if ids else "proposal_a",
        points=[S.CriticismPoint(category="missing_consideration", issue="No onboarding step.", severity="low",
                                 basis="engineering_judgement", is_verified_problem=False, evidence_ids=[],
                                 suggested_improvement="Add a first-run guide.")],
        overall_assessment="Reasonable.",
    )


def build_judgement(system: str, user: str) -> S.ProposalJudgement:
    criteria = list(get_settings().rubric_weights)
    scores = []
    for i, pid in enumerate(PROPOSAL_ID_RE.findall(user)):
        value = 8.0 if i == 0 else 6.0          # the first proposal wins, deterministically
        scores.append(S.ProposalScore(
            proposal_id=pid,
            criterion_scores=[S.CriterionScore(criterion=c, score=value, explanation="test") for c in criteria],
            key_benefits=["simple"], key_drawbacks=["no sync"], confidence="medium", confidence_reason="test",
            supporting_evidence_ids=[], remaining_risks=[],
        ))
    return S.ProposalJudgement(
        reasoning="Proposal A is better supported.", scores=scores, comparison="A over B.",
        evidence_sufficient=True, insufficiency_reason="", required_evidence=[],
        domain_coverage=[S.DomainCoverage(domain=d, status="sufficient", note="covered") for d in S.DOMAINS],
        material_contradictions=[], clarification_questions=[],
    )


def build_verification(system: str, user: str) -> S.ProposalVerification:
    cited = EVIDENCE_ID_RE.findall(tag("cited_evidence", user))
    return S.ProposalVerification(
        claims=[S.ClaimCheck(claim="Users complain about sync.", evidence_ids=cited[:1],
                             status="verified" if cited else "unavailable", notes="test", is_anecdotal=False, is_material=False)],
        overall="Well supported.", material_gaps=[],
    )


def build_narrative(system: str, user: str) -> S.ReportNarrative:
    return S.ReportNarrative(overview="Overview.", why_this_solution=["works offline"], key_uncertainties=[],
                             next_steps=["Confirm the platform."])


def _item(text: str, label: str = "recommendation", ids: list[str] | None = None) -> S.BriefItem:
    return S.BriefItem(text=text, label=label, evidence_ids=ids or [])


def build_brief(system: str, user: str) -> S.BriefContent:
    """A complete, valid brief citing the first evidence ids of the prompt (labelled research_backed)."""
    ids = EVIDENCE_ID_RE.findall(user)
    cited = ids[:1]
    rb = "research_backed" if cited else "assumption"
    return S.BriefContent(
        project_overview=S.ProjectOverview(proposed_name="", description="A habit tracker for students.",
                                           audience=[_item("University students", "user_provided")],
                                           context=_item("Self-organisation during term time.", "assumption")),
        problem_statement=S.ProblemStatement(
            statement=_item("Students lose track of daily habits.", rb, cited),
            who_and_context=_item("Students with irregular schedules.", "user_provided"),
            current_alternatives=[_item("Generic habit apps with sync problems.", rb, cited)],
            gap=_item("No simple offline option.", rb, cited),
            consequences=[_item("Habits are abandoned.", "assumption")], indicators=[]),
        research_findings=S.ResearchFindings(
            apps_and_feedback=[_item("Users complain about sync.", rb, cited)], papers_and_literature=[],
            feasibility_and_implementations=[_item("Static web apps can work offline.", rb, cited)],
            limitations_and_opportunity=[_item("Offline-first is underserved.", rb, cited)], evidence_gaps=["pricing"]),
        proposed_solution=S.ProposedSolutionSection(
            how_it_addresses_problem=_item("An offline-first tracker removes the sync failure.", "recommendation"),
            mvp_features=["track habits", "daily reminder", "streaks"], future_enhancements=["sharing"],
            user_journey=["open the app", "tick a habit", "see the streak"],
            why_this_approach=[_item("Simpler than the alternatives.", "recommendation")]),
        requirements=S.Requirements(
            functional=[_item("Users can add and tick habits.", "user_provided")],
            non_functional=[S.NonFunctionalRequirement(text="Works offline.", label="recommendation", evidence_ids=[],
                                                       category="reliability")],
            integrations_and_data=[], user_roles=[], acceptance_criteria=["Ticking a habit updates the streak."]),
        architecture=S.ArchitectureSection(
            overview=_item("A static single-page app storing data in the browser.", "recommendation"),
            components=[S.Component(name="Frontend", responsibility="UI and storage.")],
            data_flow="Everything stays in the browser.",
            technologies=[S.TechnologyChoice(name="Next.js", purpose="UI framework.", label="recommendation",
                                             evidence_ids=[], required_by_user=False)],
            key_decisions=[_item("No backend in the first version.", "recommendation")]),
        scope=S.ScopeSection(in_scope=["habit tracking"], out_of_scope=["accounts"], deliverables=["web app"], dependencies=[]),
        success_criteria=[S.SuccessCriterion(metric="Habits ticked per week", target=None, basis="none",
                                             evaluation_method="Local usage counter.", evidence_ids=[])],
        constraints_and_risks=S.ConstraintsAndRisks(
            constraints=[], assumptions=["No accounts."], unresolved_questions=["Is mobile needed?"],
            risks=[S.Risk(risk="Data loss when the browser is cleared.", category="operational",
                          mitigation="Export button.", evidence_ids=[])]),
    )


def build_brief_review(system: str, user: str) -> S.BriefReview:
    return S.BriefReview(
        checks=[S.BriefCheck(check_id=c, passed=True, severity="low", issue="", fix_instruction="") for c in S.BRIEF_CHECK_IDS],
        needs_user_input=False, clarification_questions=[], summary="Good brief.",
    )


def build_plan(system: str, user: str) -> S.ImplementationPlan:
    """A small valid plan covering the MVP features listed in <mvp_features>."""
    import json as _json
    mvp = _json.loads(tag("mvp_features", user) or "[]")
    return S.ImplementationPlan(
        summary="A static habit tracker.", tech_stack=["Vite (fast dev server)"], project_structure=["src/main.js: entry"],
        dependencies=["vitest: tests"], architecture="One page, local storage.", data_model="localStorage: habits[]",
        api_endpoints=[], frontend_components=["HabitList: shows habits"], backend_services=[], integrations=[],
        ai_components="none",
        phases=[S.PlanPhase(id="P1", name="Setup", goal="Project runs."), S.PlanPhase(id="P2", name="Features", goal="MVP works.")],
        tasks=[
            S.PlanTask(id="T1", phase="P1", title="Scaffold the project", description="Vite + vitest.", depends_on=[],
                       files=["package.json", "src/main.js"], acceptance_criteria=["npm test passes"],
                       verify_commands=["ls package.json src/main.js"]),
            S.PlanTask(id="T2", phase="P2", title="Habit tracking", description="Add and tick habits.", depends_on=["T1"],
                       files=["src/habits.js"], acceptance_criteria=["ticking updates streak"],
                       verify_commands=["ls src/habits.js"]),
        ],
        feature_coverage=[S.FeatureCoverage(feature=f, task_ids=["T2"]) for f in mvp],
        testing_strategy=["unit tests with vitest"],
        commands=S.PlanCommands(install=[], test=["ls package.json"], build=[],
                                dev="python3 -m http.server {port} --bind 127.0.0.1"),     # a real server, no npm
        risks_and_decisions=["localStorage can be cleared"],
    )


def build_plan_extension(system: str, user: str) -> S.PlanExtension:
    """New work on a built app: one task after the highest built id, covering every MVP feature with it."""
    import json as _json
    mvp = _json.loads(tag("mvp_features", user) or "[]")
    built = _json.loads(tag("built_plan", user))
    next_id = f"T{max(int(t['id'][1:]) for t in built['tasks']) + 1}"
    base = build_plan(system, user)
    return S.PlanExtension(**base.model_dump(exclude={"phases", "tasks", "feature_coverage", "summary"}),
                           summary="The habit tracker plus the requested change.", phases=[],
                           tasks=[S.PlanTask(id=next_id, phase=built["tasks"][-1]["phase"], title="The bigger change",
                                             description="Add what the user asked for.", depends_on=[built["tasks"][-1]["id"]],
                                             files=["src/extra.js"], acceptance_criteria=["the new feature works"],
                                             verify_commands=["ls src/extra.js"])],
                           feature_coverage=[S.FeatureCoverage(feature=f, task_ids=[next_id]) for f in mvp])


DEFAULT_BUILDERS = {
    S.PlanExtension: build_plan_extension,
    S.IntakeResult: build_intake,
    S.ClarificationResult: build_clarification,
    S.ResearchPlan: build_research_plan,
    S.ExtractionResult: build_extraction,
    S.ProposerOutput: build_proposer,
    S.Criticism: build_critic,
    S.ProposalJudgement: build_judgement,
    S.ProposalVerification: build_verification,
    S.ReportNarrative: build_narrative,
    S.BriefPartOne: lambda system, user: S.BriefPartOne(**build_brief(system, user).model_dump(include=set(S.BriefPartOne.model_fields))),
    S.BriefPartTwo: lambda system, user: S.BriefPartTwo(**build_brief(system, user).model_dump(include=set(S.BriefPartTwo.model_fields))),
    S.BriefPartThree: lambda system, user: S.BriefPartThree(**build_brief(system, user).model_dump(include=set(S.BriefPartThree.model_fields))),
    S.BriefReview: build_brief_review,
    S.ImplementationPlan: build_plan,
    S.FeedbackRouting: lambda system, user: S.FeedbackRouting(reasoning="test", target="wording"),
}


class FakeLLM:
    """Drop-in for llm.call_structured. `overrides` maps a schema class to a builder(system, user) -> instance."""

    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []
        self.overrides: dict[type, object] = {}
        self.kwargs: list[dict] = []

    def __call__(self, schema, system_prompt, user_content, *, max_tokens=None, run_name=None, model=None,
                 effort=None, timeout=None):
        self.calls.append((schema.__name__, run_name))
        # Billed-looking usage, so the metering path (usage.py, node_wrapper) runs offline too: $0.004 on Sonnet.
        record(model or get_settings().anthropic_model, Tokens(input=1000, output=200))
        self.kwargs.append({"schema": schema, "model": model, "effort": effort, "timeout": timeout, "user": user_content})
        # A runtime subclass (e.g. plan.plan_schema_for) uses its base class's builder, then its own validators run.
        base = next(c for c in schema.__mro__ if c in self.overrides or c in DEFAULT_BUILDERS)
        builder = self.overrides.get(base) or DEFAULT_BUILDERS[base]
        result = builder(system_prompt, user_content)
        if not isinstance(result, schema):
            result = schema.model_validate(result.model_dump())
        return result

    def count(self, schema_name: str) -> int:
        return sum(1 for name, _ in self.calls if name == schema_name)


def finish_session(graph, config, answer: str = "x", review: dict | None = None, max_pauses: int = 12) -> dict:
    """Drive a paused session to the end: answer every clarification round with `answer`, reply to every brief review
    with `review` (default: approve), approve every plan. Returns the final state values."""
    from langgraph.types import Command
    for _ in range(max_pauses):
        snapshot = graph.get_state(config)
        if not snapshot.next:
            return dict(snapshot.values)
        payload = snapshot.interrupts[0].value
        if payload["type"] == "clarification":
            reply = {"answers": {q: answer for q in payload["questions"]}}
        elif payload["type"] == "plan_review":
            reply = {"action": "approve"}
        elif payload["type"] == "change_request":
            reply = {"action": "finish"}
        else:
            reply = review or {"action": "approve"}
        graph.invoke(Command(resume=reply), config)
    raise AssertionError("session did not finish")


# --- 3) fixtures -----------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def process_manager():
    """A fresh dev-server manager per test (in-memory registry); every server it started is stopped afterwards."""
    from ai_decision_arena.workspace.processes import MemoryRuntimeStore, ProcessManager, set_manager
    manager = ProcessManager(store=MemoryRuntimeStore())
    set_manager(manager)
    yield manager
    manager.stop_all()
    set_manager(None)


@pytest.fixture
def auto_loops(monkeypatch):
    """The thorough mode: the judge / checker / validator may send the graph back by themselves (AUTO_LOOPS=true)."""
    monkeypatch.setattr(get_settings(), "auto_loops", True)


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    for module in LLM_USERS:
        monkeypatch.setattr(f"{module}.call_structured", fake)
    # The planner checks its model against GET /v1/models: no network in tests.
    monkeypatch.setattr("ai_decision_arena.nodes.planner.resolve_model", lambda wanted: (wanted, ""))
    monkeypatch.setattr("ai_decision_arena.nodes.implementer.resolve_model", lambda wanted: (wanted, ""))
    agent = FakeAgent()
    monkeypatch.setattr("ai_decision_arena.nodes.implementer.run_agent_task", agent)
    fake.agent = agent
    return fake


class FakeAgent:
    """Stands in for the Claude Agent SDK: writes the files listed in <task> (unless told to skip a task), costs
    $0.01 per attempt. The implementer's verify commands then run for REAL in the sandbox (`ls <files>`)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.skip: set[str] = set()          # task ids whose files are NOT written (verify fails)
        self.fail_once: set[str] = set()     # task ids that fail only their first attempt
        self.writes: dict[str, list[str]] = {}   # extra files to write per task id (e.g. a fix task that fixes the build)

    def __call__(self, ws, prompt, system_append, *, model, label):
        import json as _json
        from ai_decision_arena.workspace.agent import AgentRun
        task = _json.loads(tag("task", prompt))
        self.calls.append({"task": task["id"], "model": model, "prompt": prompt, "system": system_append})
        attempt = sum(c["task"] == task["id"] for c in self.calls)
        if task["id"] not in self.skip and not (task["id"] in self.fail_once and attempt == 1):
            for name in task["files"]:
                path = ws.app / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"// {task['id']}: {name}\n")
        for name in self.writes.get(task["id"], []):
            path = ws.app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"// {task['id']}: {name}\n")
        return AgentRun(ok=True, subtype="success", num_turns=3, cost_usd=0.01, final_text=f"did {task['id']}")


SOURCE_TYPE_BY_DOMAIN = {"apps": "review_site", "papers": "research_paper", "tech": "source_repository"}


def fake_run_searches(queries):
    """Two canned hits per query, URLs unique per domain and query. Never fails."""
    hits = []
    for n, q in enumerate(queries):
        for i in range(2):
            hits.append(S.SearchHit(
                url=f"https://example.org/{q.domain}/{n}/{i}",
                title=f"{q.domain} source {n}-{i}",
                snippet=f"Snippet about {q.query} number {i}. Users say offline sync keeps failing.",
                tavily_score=0.9 - 0.1 * i,
                published_at=None,
                source_type=SOURCE_TYPE_BY_DOMAIN[q.domain],
                query=q.query, domain=q.domain, topic=q.topic,
            ))
    return hits, []


@pytest.fixture
def fake_search(monkeypatch):
    monkeypatch.setattr("ai_decision_arena.nodes.research.run_searches", fake_run_searches)
    return fake_run_searches


@pytest.fixture
def graph():
    from ai_decision_arena.graph import build_graph
    return build_graph(InMemorySaver())


@pytest.fixture
def base_state() -> dict:
    """A plausible state after intake + clarification, for node-level tests."""
    return {
        "thread_id": "t1", "mode": "full", "question": "A habit tracker app for students", "user_context": "",
        "project_name": "habit tracker app", "project_category": "mobile_app",
        "idea_summary": "The user wants a habit tracker app for students.", "project_profile": {}, "requested_features": {}, "constraints": {},
        "missing_information": [], "risk_flags": [], "withdrawn_risk_flags": [],
        "clarification_answers": {}, "assumptions": [], "clarification_round_count": 0,
        "research_retry_count": 0, "debate_round": 0, "research_focus": [], "unresolved_questions": [],
        "evidence": [], "evidence_gaps": [], "conflicting_claims": [], "research_queries": [],
        "rejected_sources": [], "domain_summaries": {}, "active_seconds": 0.0,
    }
