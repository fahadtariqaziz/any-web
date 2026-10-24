"""Drive one full session through the HTTP API, like the frontend does (start → poll → answer → review the brief →
report).

Start the server first (another terminal, backend/ folder):
    FRONTEND_URL=http://localhost:3001 uv run uvicorn ai_decision_arena.api.main:app --port 8001
Then:
    uv run python scripts/api_flow.py                                   # "A simple calculator web app", you answer
    uv run python scripts/api_flow.py "A booking site for a small yoga studio"
    uv run python scripts/api_flow.py --auto                            # skip questions, approve the brief and the plan
    uv run python scripts/api_flow.py --thread <thread_id>              # pick up an existing session
"""

import argparse
import sys
import time

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("question", nargs="*")
parser.add_argument("--auto", action="store_true", help="no typing: skip all questions, approve the brief and the plan")
parser.add_argument("--thread", help="existing thread_id instead of starting a new session")
parser.add_argument("--base", default="http://localhost:8001")
args = parser.parse_args()

api = httpx.Client(base_url=args.base, timeout=30)
P = "/api/decisions"


def check(resp: httpx.Response) -> dict:
    print(f"   ← {resp.request.method} {resp.request.url.path}  {resp.status_code}")
    if resp.status_code >= 400:
        print(f"   ❌ {resp.json()['error']}")
    return resp.json()


def poll(thread_id: str, shown: int) -> tuple[dict, int]:
    """GET every 2 s, printing new progress lines, until the run is no longer 'running'."""
    while True:
        status = api.get(f"{P}/{thread_id}").json()
        for line in status["progress"][shown:]:
            print(f"      · {line['node']}: {line['message']}")
        shown = len(status["progress"])
        if status["run_state"] != "running":
            return status, shown
        time.sleep(2)


def answer(pending: dict) -> dict:
    payload = pending["payload"]
    if payload.get("error"):
        print(f"⚠️  {payload['error']}")
    if pending["type"] == "brief_review":
        return review(payload)
    if pending["type"] == "plan_review":
        return review_plan(payload)
    print(f"\n🤔 Clarification round {payload['round']} (Enter = skip)")
    answers = {} if args.auto else {q: input(f"{q}\n> ") for q in payload["questions"]}
    return {"type": "clarification", "answers": answers}


def review(payload: dict) -> dict:
    summary = payload["validation_summary"]
    print("\n" + "=" * 80 + "\n" + payload["brief_markdown"] + "=" * 80)
    print(f"📝 Brief review, round {payload['round']} of {payload['max_rounds']}: {summary['checks_passed']}/"
          f"{summary['checks_total']} checks passed, {summary['word_count']} words"
          + (" · only wording changes are accepted now" if payload["wording_only"] else ""))
    if args.auto:
        print("   --auto: approving")
        return {"type": "brief_review", "action": "approve"}
    feedback = input("Press Enter to APPROVE, or type the change you want:\n> ").strip()
    if not feedback:
        return {"type": "brief_review", "action": "approve"}
    target = input("Where should it go? [auto] / requirements / research / proposal / wording\n> ").strip() or "auto"
    return {"type": "brief_review", "action": "request_changes", "feedback": feedback, "target": target}


def review_plan(payload: dict) -> dict:
    print("\n" + "=" * 80 + "\n" + payload["plan_markdown"] + "=" * 80)
    print(f"🛠  Plan review, version {payload['round']}: {payload['task_count']} tasks, written by {payload['model']}"
          + ("" if payload["changes_allowed"] else " · changes no longer possible, approve to continue"))
    if args.auto:
        print("   --auto: approving")
        return {"type": "plan_review", "action": "approve"}
    feedback = input("Press Enter to APPROVE the plan, or type the change you want:\n> ").strip()
    if not feedback:
        return {"type": "plan_review", "action": "approve"}
    return {"type": "plan_review", "action": "request_changes", "feedback": feedback}


if args.thread:
    thread_id = args.thread
else:
    print("▶  POST /api/decisions")
    started = check(api.post(P, json={"question": " ".join(args.question) or "A simple calculator web app"}))
    thread_id = started["thread_id"]
print(f"   thread_id: {thread_id}\n")

shown = 0
while True:
    status, shown = poll(thread_id, shown)
    print(f"\n⏸  run_state={status['run_state']}  workflow_status={status['workflow_status']}")
    if status["run_state"] == "paused":
        reply = answer(status["pending"])
        check(api.post(f"{P}/{thread_id}/resume", json=reply))
    elif status["run_state"] == "interrupted":
        print("▶  Interrupted (server restarted?) → POST /resume {type: continue}")
        check(api.post(f"{P}/{thread_id}/resume", json={"type": "continue"}))
    else:
        break

if status["error"]:
    print(f"❌ {status['error']}")
report = api.get(f"{P}/{thread_id}/report")
body = check(report)
if report.status_code == 200:
    r = body["report"]
    print(f"\n📋 {r['project_name']}\n{r['overview']}")
    winner = r.get("winner")
    print(f"   winner: {winner['proposal']['name'] if winner else r.get('no_winner_reason')}")
    for alt in r.get("alternatives", []):
        print(f"   alternative: {alt['proposal']['name']}")
brief = api.get(f"{P}/{thread_id}/brief")
if brief.status_code == 200:
    b = brief.json()
    print(f"\n📄 brief draft {b['brief']['revision'] + 1}, approved at {b['approved_at']}, {b['review_round']} change request(s)")
plan = api.get(f"{P}/{thread_id}/plan")
if plan.status_code == 200:
    pl = plan.json()
    print(f"🛠  plan version {pl['revision'] + 1} by {pl['model']}: {len(pl['tasks'])} tasks, approved at {pl['approved_at']}")
artifacts = api.get(f"{P}/{thread_id}/artifacts")
if artifacts.status_code == 200:
    print(f"🗂  artifacts: {[(a['kind'], a['version'], a['content_hash'][:10]) for a in artifacts.json()['artifacts']]}")
evidence = check(api.get(f"{P}/{thread_id}/evidence"))
print(f"\n📚 evidence: {evidence['count']}  {evidence['verification_counts']}")
sys.exit(0 if report.status_code == 200 else 1)
