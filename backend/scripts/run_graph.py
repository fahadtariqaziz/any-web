"""Run the full graph, with real pause/resume, saving checkpoints in PostgreSQL.

Run from the backend/ folder:
    uv run python scripts/run_graph.py                                  # new session, "A simple calculator web app"
    uv run python scripts/run_graph.py "I get migraines twice a week"   # new session, your own text
    uv run python scripts/run_graph.py --resume <thread_id>             # continue a saved session
    uv run python scripts/run_graph.py --resume                         # continue the most recent session
    uv run python scripts/run_graph.py --memory                         # old behaviour: InMemorySaver

Checkpoints go to DATABASE_URL (Phase 7). You can stop the script at any pause (Ctrl+C) and continue
later with --resume and the printed thread_id, even after a restart.

The graph is STREAMED (see print_helpers.stream_graph): nodes emit progress events while they run
(planner done, each search, each lane...), one line is printed per finished node, and red flags appear
the moment they are recorded, instead of waiting several minutes for the final result.
"""

import argparse
import json
import os
import sys
import uuid
from contextlib import nullcontext
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.checkpointing import postgres_checkpointer
from ai_decision_arena.graph import build_graph
from print_helpers import print_case, print_risk_flags, print_report, stream_graph

parser = argparse.ArgumentParser(description="Run Health Decision Arena end to end.")
parser.add_argument("question", nargs="*", help='your app idea (default: "A simple calculator web app")')
parser.add_argument("--resume", metavar="THREAD_ID", nargs="?", const="latest",
                    help="continue a session saved in PostgreSQL (no id = the most recent session)")
parser.add_argument("--memory", action="store_true", help="use InMemorySaver (nothing survives the script)")
args = parser.parse_args()
if args.resume and args.memory:
    sys.exit("--resume needs PostgreSQL; it cannot be combined with --memory.")


def answer_pauses(graph, config, result, payload, shown_red_flags):
    """While the graph is paused, the stream ends with an "__interrupt__" update. The only pause is
    "clarification" (questions)."""
    while payload is not None:
        snapshot = graph.get_state(config)
        print(f"\n⏸  Paused at node: {snapshot.next}  |  status: {snapshot.values.get('status')}")
        if not args.memory:
            print(f"   (safe to stop here with Ctrl+C; continue later with --resume {config['configurable']['thread_id']})")
        if payload.get("error"):
            print(f"⚠️  {payload['error']}")

        print(f"\n🤔 Clarification round {payload['round']}. Press Enter to skip a question.\n")
        answers = {q: input(f"Q{i}: {q}\n> ") for i, q in enumerate(payload["questions"], start=1)}
        # We don't know yet whether clarification will ask again, so don't promise research.
        print("\n▶  Resuming. Checking your answers first; if no more questions are needed, research (~1 min) "
              "and debate (~2-3 min) follow. One line per finished node:\n")
        reply = {"answers": answers}
        # Resume the SAME thread: the paused node continues, interrupt() returns this value.
        result, payload = stream_graph(graph, Command(resume=reply), config, shown_red_flags)
    return result


def stop(thread_id: str) -> None:
    """Ctrl+C / closed input. The last finished step is already saved, so nothing is lost.
    os._exit instead of sys.exit: a node may still be waiting for Claude in a worker thread, and a normal
    exit would wait for that call to finish (pressing Ctrl+C again then prints a threading traceback)."""
    if args.memory:
        print("\n⏹  Stopped. InMemorySaver keeps nothing, so this session is gone.", flush=True)
    else:
        print(f"\n⏹  Stopped. Everything up to the last finished step is saved in PostgreSQL; continue with:\n"
              f"   uv run python scripts/run_graph.py --resume {thread_id}", flush=True)
    os._exit(130)


def latest_thread_id(saver) -> str:
    """Checkpoint ids are time-ordered, so the newest checkpoint across all threads belongs to the latest session."""
    newest = next(iter(saver.list(None, limit=1)), None)
    if newest is None:
        sys.exit("❌ No saved sessions in the database yet.")
    return newest.config["configurable"]["thread_id"]


def print_outcome(result):
    print(f"\n✅ Finished with status: {result['status']}")
    if result["status"] == "failed":
        err = result.get("error") or {}
        sys.exit(f"❌ {err.get('category', 'error')} in {err.get('node', '?')}: {err.get('message', '')}")
    print_risk_flags(result)
    print_case(result)
    print_report(result)

    cache_dir = Path(__file__).resolve().parent.parent / ".cache"
    cache_dir.mkdir(exist_ok=True)
    (cache_dir / "final_state.json").write_text(json.dumps(result, indent=2, default=str))
    (cache_dir / "final_report.json").write_text(json.dumps(result.get("final_report"), indent=2, default=str))
    print(f"\n💾 Full state and report saved to {cache_dir}/final_state.json and final_report.json "
          "(evidence, plans, criticisms and scores are all in there)")


# The checkpointer saves state after every step; that's what makes pausing (and resuming later) possible.
# PostgresSaver holds an open connection, so EVERYTHING that uses the graph runs inside this with-block.
saver_context = nullcontext(InMemorySaver()) if args.memory else postgres_checkpointer()
with saver_context as saver:
    graph = build_graph(checkpointer=saver)

    # One thread_id = one session. Resuming needs the SAME thread_id.
    thread_id = (latest_thread_id(saver) if args.resume == "latest" else args.resume) or str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": "arena_graph",
        "metadata": {"thread_id": thread_id},   # LangSmith groups runs by thread_id
    }
    shown_red_flags: set[str] = set()

    try:   # Ctrl+C anywhere (at a pause or while a node runs) → friendly stop, session kept
        if args.resume:
            snapshot = graph.get_state(config)
            if not snapshot.values:
                sys.exit(f"❌ No saved session with thread_id {thread_id} in the database.")
            print(f"📂 Loaded session {thread_id} from PostgreSQL  |  status: {snapshot.values.get('status')}  "
                  f"|  condition: {snapshot.values.get('project_name')}")
            print_risk_flags(snapshot.values)                  # show saved warnings once, then not again
            shown_red_flags.update(snapshot.values.get("risk_flags", []))
            if snapshot.interrupts:                           # paused at a clarification question
                result, payload = snapshot.values, snapshot.interrupts[0].value
            elif snapshot.next:                               # stopped mid-node (e.g. Ctrl+C during research)
                print(f"▶  Continuing from the last saved step before {snapshot.next}:\n")
                result, payload = stream_graph(graph, None, config, shown_red_flags)   # None = continue the thread
            else:                                             # already finished: just show the result again
                result, payload = snapshot.values, None
        else:
            print(graph.get_graph().draw_ascii())
            print(f"thread_id: {thread_id}\n")
            question = " ".join(args.question) or "A simple calculator web app"
            result, payload = stream_graph(graph, {"question": question}, config, shown_red_flags)

        result = answer_pauses(graph, config, result, payload, shown_red_flags)
    except (KeyboardInterrupt, EOFError):
        stop(thread_id)
    print_outcome(result)
