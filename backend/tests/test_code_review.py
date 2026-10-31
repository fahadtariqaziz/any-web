"""M13: code review + project learnings (nodes/code_review.py). Diffs against the last review's snapshot, Python's
trust boundary on findings, the fix task for HIGH findings (capped), learnings fed to later tasks, the env switch.
The reviewer is the conftest FakeLLM (overrides per test); the coding agent is the FakeAgent."""

import pytest

from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes import code_review as R
from ai_decision_arena.workspace.paths import create_workspace

from tests.conftest import tag
from tests.test_delivery import reply, to_preview


def test_changes_are_diffs_new_files_and_deletions_source_first():
    before = {"src/a.js": "one\ntwo\n", "src/gone.js": "x\n", "README.md": "hi\n"}
    after = {"src/a.js": "one\nTWO\n", "src/a.test.js": "test\n", "package.json": "{}\n", "README.md": "hi\n",
             "src/new.js": "export const n = 1;\n"}
    ch = R.collect_changes(before, after, 10_000)
    assert ch["files"] == ["src/a.js", "src/new.js", "package.json", "src/a.test.js"]      # source, config, tests
    assert ch["deleted"] == ["src/gone.js"] and "README.md" not in ch["files"]
    assert '<file path="src/a.js" change="modified">' in ch["text"] and "-two\n+TWO" in ch["text"]
    assert '<file path="src/new.js" change="new">\nexport const n = 1;' in ch["text"]
    assert "<deleted>src/gone.js</deleted>" in ch["text"]
    whole = R.collect_changes(before, after, 10_000, full={"src/a.js"})
    assert 'change="modified (whole file: an earlier finding is open on it)">\none\nTWO\n' in whole["text"]
    capped = R.collect_changes({}, {"src/big.js": "x" * 900, "src/small.js": "y"}, 400)
    assert capped["files"] == ["src/small.js"] and capped["omitted"] == ["src/big.js"]


def test_read_texts_skips_locks_builder_config_and_binaries(tmp_path):
    ws = create_workspace("rv-texts", tmp_path)
    (ws.app / "src").mkdir()
    (ws.app / "src" / "main.js").write_text("ok")
    (ws.app / "package-lock.json").write_text("{}")
    (ws.app / "playwright.config.mjs").write_text("// builder")
    (ws.app / "logo.png").write_bytes(b"\x89PNG\x00\xff\xfe")
    (ws.app / "node_modules").mkdir()
    (ws.app / "node_modules" / "dep.js").write_text("dep")
    assert R.read_texts(ws) == {"src/main.js": "ok"}


def test_learnings_are_deduplicated_and_capped():
    old = [{"rule": "Store money as integer cents.", "source": "F1", "at": "t", "round": 1}]
    new = [{"rule": "store money as integer cents", "source": "F2", "at": "t", "round": 2},
           {"rule": "Validate dates on the server.", "source": "x", "at": "t", "round": 2}]
    merged = R.merge_learnings(old, new, cap=5)
    assert [m["rule"] for m in merged] == ["Store money as integer cents.", "Validate dates on the server."]
    assert len(R.merge_learnings(old, new, cap=1)) == 1


def finding(file: str, severity: str = "high", title: str = "Negative amounts are accepted") -> S.ReviewFinding:
    return S.ReviewFinding(severity=severity, category="bug", file=file, line=3, title=title,
                           detail="Adding -5 lowers the total.", fix="Reject amounts <= 0.")


class FakeReviewer:
    """Round 1: a HIGH finding on a shown file, a LOW one on a file that was not shown, one learning.
    Later rounds: what `later` says (default: nothing found)."""

    def __init__(self, later=None):
        self.users: list[str] = []
        self.later = later

    def __call__(self, system, user):
        self.users.append(user)
        if len(self.users) == 1:
            return S.CodeReviewOutput(summary="One real bug.", findings=[finding("src/habits.js"),
                                      finding("src/invented.js", "low", "Not shown")],
                                      learnings=[S.ProjectLearning(rule="Validate habit names in src/habits.js before saving.",
                                                                   source="Negative amounts are accepted")])
        if self.later:
            return self.later(user)
        return S.CodeReviewOutput(summary="Fixed.", findings=[], learnings=[])


@pytest.fixture
def compound(monkeypatch):
    monkeypatch.setattr(get_settings(), "compound_engineering", True)


def test_high_finding_becomes_a_fix_task_and_the_learning_reaches_later_tasks(graph, fake_llm, fake_search, compound):
    reviewer = FakeReviewer()
    fake_llm.overrides[S.CodeReviewOutput] = reviewer
    fake_llm.agent.writes = {"F1": ["src/habits.js"]}
    fake_llm.agent.contents = {"F1": {"src/habits.js": "// F1: names validated\n"}}
    state, snapshot = to_preview(graph, "rv-loop")
    assert [t["id"] for t in state["implementation_tasks"]] == ["T1", "T2", "F1"]
    f1 = state["implementation_tasks"][2]
    assert f1["title"] == "Address the code review findings" and f1["status"] == "done"
    assert "<untrusted>" in f1["spec"]["description"] and "Negative amounts are accepted" in f1["spec"]["description"]
    assert "Not shown" not in f1["spec"]["description"]                   # the finding on an unshown file was dropped
    assert f1["spec"]["verify_commands"] == ["ls package.json"]           # the plan's test commands
    # round 1 saw every file as new; round 2 saw only F1's diff, plus F1 in the fix history
    assert '<file path="src/main.js" change="new">' in reviewer.users[0]
    assert tag("changes", reviewer.users[1]).count("<file ") == 1 and 'path="src/habits.js" change="modified (whole file' in reviewer.users[1]
    assert '"id": "F1"' in tag("fix_history", reviewer.users[1])
    review = state["code_review"]
    assert review["round"] == 2 and review["status"] == "passed" and state["review_fix_round"] == 1
    assert [item["rule"] for item in state["learnings"]] == ["Validate habit names in src/habits.js before saving."]
    f1_prompt = next(c["prompt"] for c in fake_llm.agent.calls if c["task"] == "F1")
    assert "<project_learnings>" in f1_prompt and "Validate habit names" in f1_prompt
    assert "<project_learnings>" in reviewer.users[1]
    learned = (create_workspace("rv-loop").builder / R.LEARNINGS_FILE).read_text()
    assert "Validate habit names" in learned and "Negative amounts are accepted" in learned
    assert snapshot.next == ("await_change_request",) and snapshot.interrupts[0].value["review"]["status"] == "passed"


def test_high_findings_stop_after_the_fix_rounds_and_a_change_is_reviewed_alone(graph, fake_llm, fake_search, compound):
    always = FakeReviewer(later=lambda user: S.CodeReviewOutput(summary="Still bad.", findings=[finding("src/habits.js")]))
    fake_llm.overrides[S.CodeReviewOutput] = always
    fake_llm.agent.writes = {"F1": ["src/habits.js"], "C1": ["src/change.js"]}
    fake_llm.agent.contents = {"F1": {"src/habits.js": "// still wrong\n"}}
    state, snapshot = to_preview(graph, "rv-cap")
    fixes = [t for t in state["implementation_tasks"] if t["id"].startswith("F")]
    assert len(fixes) == get_settings().max_review_fix_rounds == 1
    assert state["code_review"]["status"] == "changes_requested" and snapshot.next == ("await_change_request",)
    calls = len(always.users)
    state, snapshot = reply(graph, "rv-cap", action="change", request="Add a dark mode")
    change_review = always.users[calls]
    assert tag("changes", change_review).count("<file ") == 1 and 'path="src/change.js" change="new"' in change_review
    # its new finding names src/habits.js, which this review did not show: dropped; but the unfixed HIGH finding on
    # habits.js stays open (carried), and the change's fresh fix round sends it back once more
    review = state["code_review"]
    assert review["dropped"] == 1 and review["carried"] == 1 and review["status"] == "changes_requested"
    assert state["review_fix_round"] == 1 and [t["id"] for t in state["implementation_tasks"]][-1] == "F2"


def test_compound_engineering_off_means_no_review_call_and_no_learnings(graph, fake_llm, fake_search, monkeypatch):
    monkeypatch.setattr(get_settings(), "compound_engineering", False)
    state, snapshot = to_preview(graph, "rv-off")
    assert "CodeReviewOutput" not in [name for name, _ in fake_llm.calls]
    assert state["code_review"]["status"] == "skipped" and "COMPOUND_ENGINEERING=false" in state["code_review"]["reason"]
    assert not state.get("learnings") and snapshot.next == ("await_change_request",)
    assert all("<project_learnings>" not in c["prompt"] for c in fake_llm.agent.calls)


def test_a_failed_build_is_not_reviewed(graph, fake_llm, fake_search, compound, monkeypatch):
    fake_llm.agent.skip = {"T1"}                                          # package.json never written
    monkeypatch.setattr(get_settings(), "max_build_fix_rounds", 0)
    state, _ = to_preview(graph, "rv-broken")
    assert state["code_review"]["status"] == "skipped" and "did not pass" in state["code_review"]["reason"]
    assert "CodeReviewOutput" not in [name for name, _ in fake_llm.calls]


def test_no_change_keeps_the_last_review(graph, fake_llm, fake_search, compound):
    """A fix task that touches no file (e.g. a browser-test fix answered in tests only) must not hide the last result."""
    fake_llm.overrides[S.CodeReviewOutput] = FakeReviewer()
    fake_llm.agent.writes = {"F1": []}                                    # the review fix changes nothing
    state, _ = to_preview(graph, "rv-same")
    assert state["code_review"]["round"] == 1 and state["code_review"]["status"] == "changes_requested"


def test_unfixed_findings_on_untouched_files_stay_open(graph, fake_llm, fake_search, compound, monkeypatch):
    """A later review of OTHER files must not report "passed" over an earlier high finding nobody fixed."""
    monkeypatch.setattr(get_settings(), "max_review_fix_rounds", 0)
    reviewer = FakeReviewer()
    fake_llm.overrides[S.CodeReviewOutput] = reviewer
    fake_llm.agent.writes = {"C1": ["src/change.js"]}
    to_preview(graph, "rv-carry")
    state, _ = reply(graph, "rv-carry", action="change", request="Add a dark mode")
    review = state["code_review"]
    assert review["round"] == 2 and review["status"] == "changes_requested" and review["carried"] == 1
    assert review["findings"][0]["file"] == "src/habits.js" and review["findings"][0]["from_round"] == 1
    assert "<open_findings>" not in reviewer.users[1]                     # habits.js was not shown again


def test_open_findings_on_a_file_shown_again_are_rejudged(graph, fake_llm, fake_search, compound):
    reviewer = FakeReviewer()
    fake_llm.overrides[S.CodeReviewOutput] = reviewer
    fake_llm.agent.writes = {"F1": ["src/habits.js"]}
    fake_llm.agent.contents = {"F1": {"src/habits.js": "// fixed\n"}}
    state, _ = to_preview(graph, "rv-rejudge")
    assert "Negative amounts are accepted" in tag("open_findings", reviewer.users[1])
    assert state["code_review"]["findings"] == []                         # the reviewer did not report it again

