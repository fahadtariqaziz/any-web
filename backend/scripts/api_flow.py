"""Drive one full session through the HTTP API, like the frontend will (start → poll → answer → report).

Start the server first (another terminal, backend/ folder):
    uv run uvicorn ai_decision_arena.api.main:app --port 8000
Then:
    uv run python scripts/api_flow.py                                   # "A simple calculator web app", you answer
    uv run python scripts/api_flow.py "I get migraines twice a week"
    uv run python scripts/api_flow.py --auto                            # skip questions
    uv run python scripts/api_flow.py --thread <thread_id>              # pick up an existing session
"""

import argparse
import sys
import time

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("question", nargs="*")
parser.add_argument("--auto", action="store_true", help="no typing: skip all questions")
parser.add_argument("--thread", help="existing thread_id instead of starting a new session")
parser.add_argument("--base", default="http://localhost:8000")
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
    print(f"\n🤔 Clarification round {payload['round']} (Enter = skip)")      # the only pause type
    answers = {} if args.auto else {q: input(f"{q}\n> ") for q in payload["questions"]}
    return {"type": "clarification", "answers": answers}


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
    for item in r["domains"]:
        print(f"   {item['domain']}: {(item.get('plan') or {}).get('name', item.get('unavailable_reason'))}")
evidence = check(api.get(f"{P}/{thread_id}/evidence"))
print(f"\n📚 evidence: {evidence['count']}  {evidence['verification_counts']}")
sys.exit(0 if report.status_code == 200 else 1)
