"""Parallel tasks (implementer_parallel): which tasks may share a step, and what keeps parallel agents apart.

Batch rule: the next task plus other READY plan tasks whose declared files overlap none of the batch's and touch no
shared manifest; fix / change tasks run alone. Each agent may not write its siblings' files; sandbox commands of one
project run one at a time; verification runs after the whole batch."""

from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.implementer import PARALLEL_NOTE, pick_batch
from ai_decision_arena.workspace.agent import protected_problem
from ai_decision_arena.workspace.paths import create_workspace
from ai_decision_arena.workspace.sandbox import workspace_lock

from tests.conftest import build_plan, tag
from tests.test_plan import run_full

MVP = '<mvp_features>["Add habits"]</mvp_features>'


def plan_with(*tasks: S.PlanTask, user: str = MVP) -> S.ImplementationPlan:
    base = build_plan("", user)
    return base.model_copy(update={"tasks": [base.tasks[0], *tasks]})


def plan_task(tid: str, files: list[str], deps=("T1",)) -> S.PlanTask:
    return S.PlanTask(id=tid, phase="P2", title=f"Task {tid}", description="x", depends_on=list(deps), files=files,
                      acceptance_criteria=["works"], verify_commands=[f"ls {files[0]}"])


def states(plan: S.ImplementationPlan, done=("T1",)) -> list[dict]:
    return [{"id": t.id, "title": t.title, "phase": t.phase, "depends_on": t.depends_on,
             "status": "done" if t.id in done else "pending", "attempts": 0, "result": None} for t in plan.tasks]


def test_batch_takes_ready_tasks_with_disjoint_files_only():
    plan = plan_with(plan_task("T2", ["src/a.js", "tests/a.test.js"]), plan_task("T3", ["src/b.js"]),
                     plan_task("T4", ["src/a.js"]),                       # overlaps T2
                     plan_task("T5", ["vite.config.js", "src/v.js"]),     # shared manifest
                     plan_task("T6", ["src/c.js"], deps=("T2",)),         # not ready
                     plan_task("T7", ["src/d.js"]))
    tasks = states(plan)
    assert [tasks[i]["id"] for i in pick_batch(tasks, plan, 3)] == ["T2", "T3", "T7"]
    assert [tasks[i]["id"] for i in pick_batch(tasks, plan, 2)] == ["T2", "T3"]
    assert [tasks[i]["id"] for i in pick_batch(tasks, plan, 1)] == ["T2"]


def test_scaffold_shared_files_and_fix_tasks_run_alone():
    plan = plan_with(plan_task("T2", ["src/a.js"]), plan_task("T3", ["src/b.js"]))
    assert [t for t in pick_batch(states(plan, done=()), plan, 3)] == [0]          # T1 writes package.json
    tasks = states(plan)
    tasks.insert(1, {"id": "F1", "title": "Fix the build", "phase": "fix", "depends_on": [], "status": "pending",
                     "attempts": 0, "result": None,
                     "spec": plan_task("F1", ["src/a.js"], deps=()).model_copy(update={"phase": "fix"}).model_dump()})
    assert [tasks[i]["id"] for i in pick_batch(tasks, plan, 3)] == ["F1"]


def test_independent_tasks_run_in_one_step_and_cannot_touch_each_other(graph, fake_llm, fake_search, monkeypatch):
    monkeypatch.setattr(get_settings(), "implementer_parallel", 3)
    fake_llm.overrides[S.ImplementationPlan] = lambda system, user: plan_with(
        plan_task("T2", ["src/habits.js"]), plan_task("T3", ["src/streaks.js"]), user=user)
    state = run_full(graph, "parallel-ok")
    tasks = {t["id"]: t for t in state["implementation_tasks"]}
    assert all(t["status"] == "done" for t in tasks.values())
    assert tasks["T2"]["result"]["parallel_with"] == ["T3"] and tasks["T3"]["result"]["parallel_with"] == ["T2"]
    calls = {c["task"]: c for c in fake_llm.agent.calls}
    assert calls["T2"]["protected"] == frozenset({"src/streaks.js"}) and calls["T3"]["protected"] == frozenset({"src/habits.js"})
    assert PARALLEL_NOTE.strip()[:40] in calls["T2"]["prompt"] and "src/streaks.js" in tag("parallel_tasks", calls["T2"]["prompt"])
    assert calls["T1"]["protected"] == frozenset() and "<parallel_tasks>" not in calls["T1"]["prompt"]


def test_protected_files_can_be_read_but_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "generated_projects_dir", tmp_path)
    ws = create_workspace("protect")
    protected = frozenset({"src/b.js"})
    assert protected_problem(ws, "Write", {"file_path": str(ws.app / "src" / "b.js")}, protected)
    assert protected_problem(ws, "Edit", {"file_path": "src/b.js"}, protected)
    assert protected_problem(ws, "Read", {"file_path": str(ws.app / "src" / "b.js")}, protected) is None
    assert protected_problem(ws, "Write", {"file_path": str(ws.app / "src" / "a.js")}, protected) is None
    assert protected_problem(ws, "Write", {"file_path": "src/b.js"}, frozenset()) is None


def test_one_command_lock_per_project(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "generated_projects_dir", tmp_path)
    a, b = create_workspace("lock-a"), create_workspace("lock-b")
    assert workspace_lock(a) is workspace_lock(create_workspace("lock-a")) and workspace_lock(a) is not workspace_lock(b)
