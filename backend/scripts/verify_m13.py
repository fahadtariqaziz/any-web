"""M13 live check: code review + project learnings (nodes/code_review.py) with the REAL reviewer (review_model,
Sonnet 5.5): three review rounds on a small habit tracker with planted bugs. About $0.05-0.15.

Run from the backend/ folder:
    uv run python scripts/verify_m13.py

State: the eval fixture `built_calculator.json` (a real fake-pipeline state with an approved habit-tracker brief and
plan); the project folder is a throwaway one (GENERATED_PROJECTS_DIR is set to a temp dir before the package loads).

1. Planted bugs (delete removes the wrong habit; habit names rendered with innerHTML; empty names saved) → at least
   one HIGH finding on a real file, a fix task "Address the code review findings" with the plan's test commands,
   at least one project learning (state + .builder/learnings.md), no finding on a file that was not shown.
2. The delete bug is fixed by hand (other bugs left) → round 2 sees habits.js WHOLE (an open finding is on it) and
   the earlier findings in <open_findings>; the delete finding is not reported again, the innerHTML one is.
3. False-positive control: a correct, tested helper is added (src/format.js + test) → no HIGH finding on it.
"""

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

os.environ["GENERATED_PROJECTS_DIR"] = tempfile.mkdtemp(prefix="verify-m13-")
os.environ["COMPOUND_ENGINEERING"] = "true"
os.environ["PERSIST_RESULTS"] = "false"

from langgraph.graph import END, START, StateGraph  # noqa: E402

from ai_decision_arena.config import get_settings  # noqa: E402
from ai_decision_arena.nodes import code_review as R  # noqa: E402
from ai_decision_arena.state import ArenaState  # noqa: E402
from ai_decision_arena.usage import metering  # noqa: E402
from ai_decision_arena.workspace.paths import create_workspace  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "built_calculator.json"
FAILED: list[str] = []

HABITS = """// Habits live in localStorage under "habits": [{ name, days: ["2026-10-29", ...] }]
const KEY = 'habits';

export function load() {
  return JSON.parse(localStorage.getItem(KEY) || '[]');
}

export function save(habits) {
  localStorage.setItem(KEY, JSON.stringify(habits));
}

export function addHabit(habits, name) {
  return [...habits, { name, days: [] }];
}

export function deleteHabit(habits, index) {
  const copy = [...habits];
  copy.splice(index + 1, 1);
  return copy;
}

export function tick(habits, index) {
  const today = new Date().toISOString().slice(0, 10);
  return habits.map((h, i) => (i === index && !h.days.includes(today) ? { ...h, days: [...h.days, today] } : h));
}

export function renderHabits(list, habits) {
  list.innerHTML = habits
    .map((h, i) => `<li>${h.name} <button data-tick="${i}">Done today</button> <button data-delete="${i}">Delete</button></li>`)
    .join('');
}
"""

MAIN = """import { addHabit, deleteHabit, load, renderHabits, save, tick } from './habits.js';

let habits = load();
const list = document.getElementById('habits');
const form = document.getElementById('add');

function refresh() { save(habits); renderHabits(list, habits); }

form.addEventListener('submit', (e) => {
  e.preventDefault();
  habits = addHabit(habits, form.elements.name.value);
  form.reset();
  refresh();
});

list.addEventListener('click', (e) => {
  const t = e.target.dataset;
  if (t.tick) habits = tick(habits, Number(t.tick));
  if (t.delete) habits = deleteHabit(habits, Number(t.delete));
  refresh();
});

refresh();
"""

INDEX = """<!doctype html><html><head><title>Habits</title></head><body>
<h1>Habits</h1><form id="add"><label>Habit <input name="name"></label><button>Add</button></form>
<ul id="habits"></ul><script type="module" src="/src/main.js"></script></body></html>
"""

FORMAT = """// Streak label: "1 day", "3 days"; negative or non-integer input is a programming error.
export function formatStreak(days) {
  if (!Number.isInteger(days) || days < 0) throw new RangeError(`invalid streak: ${days}`);
  return days === 1 ? '1 day' : `${days} days`;
}
"""

FORMAT_TEST = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatStreak } from '../src/format.js';

test('formats streaks', () => {
  assert.equal(formatStreak(0), '0 days');
  assert.equal(formatStreak(1), '1 day');
  assert.equal(formatStreak(5), '5 days');
  assert.throws(() => formatStreak(-1), RangeError);
});
"""


def check(ok: bool, label: str) -> None:
    print(("✅ " if ok else "❌ ") + label)
    if not ok:
        FAILED.append(label)


def run_node(state: dict, thread_id: str) -> dict:
    builder = StateGraph(ArenaState)
    builder.add_node("code_review", R.code_review_node)
    builder.add_edge(START, "code_review")
    builder.add_edge("code_review", END)
    with metering() as meter:
        out = builder.compile().invoke(state, {"configurable": {"thread_id": thread_id}})
    print(f"   reviewer: {meter.calls} call(s), ${meter.cost_usd:.4f}, models {meter.models}")
    run_node.total += meter.cost_usd
    return out


run_node.total = 0.0


def show(review: dict) -> None:
    print(f"   summary: {review.get('summary')}")
    for f in review.get("findings", []):
        print(f"   - [{f['severity']}] {f['file']}:{f.get('line')} {f['title']}" + (f" (open since round {f['from_round']})" if f.get("from_round") else ""))


def main() -> int:
    fixture = json.loads(FIXTURE.read_text())
    state = fixture.get("state", fixture)
    thread_id = f"verify-m13-{uuid.uuid4().hex[:8]}"
    state = state | {"thread_id": thread_id, "build_results": {"round": 1, "passed": True, "steps": []},
                     "code_review": {}, "learnings": [], "review_fix_round": 0}
    ws = create_workspace(thread_id)
    for name, text in {"index.html": INDEX, "src/habits.js": HABITS, "src/main.js": MAIN,
                       "package.json": json.dumps({"name": "habits", "type": "module", "scripts": {"test": "node --test"}})}.items():
        (ws.app / name).parent.mkdir(parents=True, exist_ok=True)
        (ws.app / name).write_text(text)
    print(f"model {get_settings().review_model} · project {ws.app}")

    print("\n— 1. planted bugs")
    state = run_node(state, thread_id)
    review = state["code_review"]
    show(review)
    high = [f for f in review["findings"] if f["severity"] == "high"]
    check(bool(high), f"at least one HIGH finding ({len(high)})")
    check(all(f["file"] in review["files_reviewed"] for f in review["findings"]), "every finding is on a reviewed file")
    text = " ".join((f["title"] + " " + f["detail"]).lower() for f in review["findings"])
    check(("delete" in text or "splice" in text or "wrong habit" in text), "the off-by-one delete is found")
    check("innerhtml" in text or "xss" in text or "html" in text, "the innerHTML rendering of names is found")
    fix = next((t for t in state["implementation_tasks"] if t["title"] == "Address the code review findings"), None)
    check(fix is not None and fix["spec"]["verify_commands"] == state["implementation_plan"]["commands"]["test"],
          f"fix task {fix['id'] if fix else '-'} with the plan's test commands")
    check(len(state["learnings"]) >= 1, f"{len(state['learnings'])} project learning(s): "
          + "; ".join(item["rule"] for item in state["learnings"]))
    learned = (ws.builder / R.LEARNINGS_FILE).read_text()
    check(all(item["rule"] in learned for item in state["learnings"]), ".builder/learnings.md holds them")

    print("\n— 2. the delete bug fixed by hand, the rest left")
    (ws.app / "src/habits.js").write_text(HABITS.replace("copy.splice(index + 1, 1);", "copy.splice(index, 1);"))
    state = state | {"implementation_tasks": [t for t in state["implementation_tasks"] if t is not fix]}
    before = review
    state = run_node(state, thread_id)
    review = state["code_review"]
    show(review)
    check(review["files_reviewed"] == ["src/habits.js"], f"only the changed file was reviewed: {review['files_reviewed']}")
    text = " ".join((f["title"] + " " + f["detail"]).lower() for f in review["findings"] if f["file"] == "src/habits.js")
    check("splice" not in text and "wrong habit" not in text and "off-by-one" not in text,
          "the fixed delete finding is not reported again")
    had_html = any("innerhtml" in (f["title"] + f["detail"]).lower() or "xss" in (f["title"] + f["detail"]).lower()
                   for f in before["findings"])
    check(not had_html or "innerhtml" in text or "xss" in text or "html" in text,
          "the unfixed innerHTML finding is reported again (the whole file was shown)")
    carried_ok = all(f.get("from_round") for f in review["findings"] if f["file"] != "src/habits.js")
    check(carried_ok, "findings on untouched files are carried as open")

    print("\n— 3. false-positive control: a correct, tested helper")
    (ws.app / "src/format.js").write_text(FORMAT)
    (ws.app / "test").mkdir(exist_ok=True)
    (ws.app / "test/format.test.js").write_text(FORMAT_TEST)
    state = run_node(state, thread_id)
    review = state["code_review"]
    show(review)
    new_high = [f for f in review["findings"] if f["severity"] == "high" and f["file"] in ("src/format.js", "test/format.test.js")]
    check(not new_high, f"no HIGH finding on the correct helper ({[f['title'] for f in new_high]})")
    check(set(review["files_reviewed"]) == {"src/format.js", "test/format.test.js"}, "only the new files were reviewed")

    print(f"\nreviewer total: ${run_node.total:.4f}")
    print("M13 VERIFY: " + ("PASS" if not FAILED else f"FAIL ({len(FAILED)}: {'; '.join(FAILED)})"))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
