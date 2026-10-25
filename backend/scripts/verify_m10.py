"""M10 verify: the Lovable-style builder UI (chat left, live preview right).

Checks, against the user's running dev servers (API on 8001, Next on 3001; nothing is started here):
  1. frontend: eslint, tsc --noEmit, next build (production build of every page);
  2. the API contract the builder page relies on, for one BUILT session (default: the newest session with a build,
     or --session <thread_id>): has_build, the chat transcript (reviews in time order with valid actions, every
     change request of type "change" linked to its C<n> task, Ask messages), the preview endpoint;
  3. the pages answer 200: /, /c/<id>, /admin, /decisions/<id>;
  4. the RENDERED page (headless Chrome --dump-dom, after the client fetched its data): the conversation shows the
     first message and every change request, the stage chips, the right-pane tabs, the message box in Ask mode;
     the admin page links back to the builder; real mouse drags on the chat | preview border (check_resize.mjs);
     real clicks on "Download code" in folder mode and zip mode (check_download.mjs).
     Skipped (not failed) when Chrome is not installed.
  5. --ask: one real Ask-mode question (one Sonnet call, cents): a non-empty streamed answer, saved in the transcript.

Usage (from backend/):  uv run python scripts/verify_m10.py [--session <id>] [--ask] [--skip-build]
Exit code 0 = PASS. The manual browser checklist (new idea → answers → approve brief → approve plan → preview →
change request) is in handoff.md section 14; it needs the user's eyes and a full paid run.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

API = "http://localhost:8001"
WEB = "http://localhost:3001"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((ok, label))
    print(f"{'✅' if ok else '❌'} {label}" + (f"  ({detail})" if detail else ""))
    return ok


def run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          env={**__import__("os").environ, "NEXT_PUBLIC_API_URL": API})


def frontend_checks(skip_build: bool) -> None:
    print("\n== 1. frontend: lint, tsc, build ==")
    lint = run(["npm", "run", "lint"], FRONTEND)
    check(lint.returncode == 0, "eslint clean", lint.stdout[-300:] if lint.returncode else "")
    tsc = run(["npx", "tsc", "--noEmit"], FRONTEND)
    check(tsc.returncode == 0, "tsc --noEmit clean", tsc.stdout[-300:] if tsc.returncode else "")
    if skip_build:
        print("   (next build skipped)")
        return
    build = run(["npx", "next", "build"], FRONTEND)
    routes = all(r in build.stdout for r in ("/c/[threadId]", "/decisions/[threadId]", "/admin"))
    check(build.returncode == 0 and routes, "next build passes with the builder and admin routes",
          build.stdout[-500:] if build.returncode else "")


def pick_session(client: httpx.Client, wanted: str | None) -> str | None:
    if wanted:
        return wanted
    for s in client.get(f"{API}/api/decisions", params={"limit": 50}).json()["sessions"]:
        status = client.get(f"{API}/api/decisions/{s['thread_id']}").json()
        if status.get("has_build"):
            return s["thread_id"]
    return None


def api_checks(client: httpx.Client, thread_id: str) -> dict:
    print(f"\n== 2. API contract for session {thread_id[:8]} ==")
    status = client.get(f"{API}/api/decisions/{thread_id}").json()
    check(status.get("has_build") is True, "status.has_build is true for a built session")
    chat = client.get(f"{API}/api/chats/{thread_id}").json()
    check(chat.get("ready") is True, "transcript ready (Ask mode available)")
    reviews, changes = chat.get("reviews", []), chat.get("changes", [])
    check(all(r["kind"] in ("brief", "plan") and r["action"] in ("approve", "request_changes") for r in reviews)
          and [r["at"] for r in reviews] == sorted(r["at"] for r in reviews),
          "reviews have valid kinds / actions and are in time order", f"{len(reviews)} reviews")
    check(any(r["kind"] == "brief" and r["action"] == "approve" for r in reviews)
          and any(r["kind"] == "plan" and r["action"] == "approve" for r in reviews),
          "the brief and the plan approvals are in the conversation")
    linked = [c for c in changes if c["action"] == "change"]
    impl = client.get(f"{API}/api/decisions/{thread_id}/implementation").json()
    task_status = {t["id"]: t["status"] for t in impl["tasks"]}
    check(all(c["task_id"] and task_status.get(c["task_id"]) == c["task_status"] for c in linked),
          "every change request is linked to its C<n> task with the task's real status",
          ", ".join(f"{c['task_id']}={c['task_status']}" for c in linked) or "no change requests")
    preview = client.get(f"{API}/api/decisions/{thread_id}/preview")
    check(preview.status_code == 200 and preview.json()["state"] in ("starting", "ready", "failed", "stopped"),
          "preview endpoint answers with a known state", preview.json().get("state", preview.text[:80]))
    return chat


def page_checks(client: httpx.Client, thread_id: str) -> None:
    print("\n== 3. pages answer ==")
    for path in ("/", f"/c/{thread_id}", "/admin", f"/decisions/{thread_id}"):
        r = client.get(f"{WEB}{path}")
        check(r.status_code == 200, f"GET {path} → 200", str(r.status_code))


def dump_dom(url: str, budget_ms: int = 9000) -> str:
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--window-size=1440,900",
                          f"--virtual-time-budget={budget_ms}", "--dump-dom", url],
                         capture_output=True, text=True, timeout=120)
    return out.stdout


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&amp;", "&").replace("&#x27;", "'")


def status_of(thread_id: str) -> dict:
    return httpx.get(f"{API}/api/decisions/{thread_id}", timeout=30).json()


def rendered_checks(thread_id: str, chat: dict) -> None:
    print("\n== 4. rendered page (headless Chrome) ==")
    if not Path(CHROME).exists():
        print("   (Chrome not installed: skipped)")
        return
    html = dump_dom(f"{WEB}/c/{thread_id}")
    text = text_of(html)
    check(bool(chat.get("question")) and chat["question"][:40] in text, "the first message is in the conversation")
    for c in chat.get("changes", []):
        if c["action"] == "change":
            check(c["request"][:40] in text, f"change request {c['round']} is in the conversation")
            check(f"{c['task_id']} done" in text if c["task_status"] == "done" else c["task_id"] in text,
                  f"its outcome ({c['task_id']} {c['task_status']}) is shown")
    check(all(w in text for w in ("Idea", "Research", "Solution", "Brief", "Plan", "Build", "Preview")), "stage chips rendered")
    check(all(f'>{t}<' in html or f"> {t}" in html or t in text for t in ("Preview", "Brief", "Plan", "Build", "Activity"))
          and 'aria-label="Preview and documents"' in html, "right pane with its five tabs")
    paused_for_change = status_of(thread_id).get("pending", {}) or {}
    if paused_for_change.get("type") == "change_request":      # the app runs: the box defaults to a change
        check("Describe the change, e.g. make the buttons bigger" in html and "Ask about app" in html
              and "Plan a bigger change" in html, "message box: change (default), bigger change, Ask about app")
    else:
        check('aria-label="Conversation"' in html and "Ask about the research, the brief, the plan or the build" in html
              and "Ask about app" in html, "message box in Ask-about-app mode")
    check("You approved the brief" in text and "You approved the plan" in text, "approvals shown as conversation events")
    admin = dump_dom(f"{WEB}/decisions/{thread_id}", 7000)
    check(f'href="/c/{thread_id}"' in admin and "Open in the builder" in admin, "the admin page links to the builder")
    resize_checks(thread_id)
    download_checks(thread_id)
    home = text_of(dump_dom(f"{WEB}/", 6000))
    check("What do you want to build?" in home and "Recent projects" in home, "home page: prompt and recent projects")


def resize_checks(thread_id: str) -> None:
    """Real mouse drags on the chat | preview border (frontend/scripts/check_resize.mjs, Chrome DevTools protocol)."""
    out = subprocess.run(["node", str(FRONTEND / "scripts" / "check_resize.mjs"), f"{WEB}/c/{thread_id}"],
                         capture_output=True, text=True, timeout=180)
    steps = {line.split(" ", 1)[0]: json.loads(line.split(" ", 1)[1]) for line in out.stdout.splitlines() if " {" in line}
    if not check(len(steps) == 6, "resize check ran", out.stderr[-300:]):
        return
    d, wide, narrow, widest, reload, reset = (steps[k] for k in ("default", "dragged_+400", "dragged_-900", "dragged_+2000",
                                                                "after_reload", "double-click"))
    check(wide["chat"] > d["chat"] + 300 and wide["preview"] < d["preview"] - 300,
          "dragging right across the preview iframe widens the chat, the preview shrinks", f"{d['chat']} → {wide['chat']} px")
    check(narrow["chat"] == 320 and widest["chat"] == 900, "the width stops at 320 / 900 px")
    check(reload["chat"] == widest["chat"] and reload["stored"] == "900", "the width survives a reload")
    check(reset["chat"] == d["chat"] and reset["stored"] is None, "double-click resets to the default")


def download_checks(thread_id: str) -> None:
    """Real clicks on "Download code" (frontend/scripts/check_download.mjs): folder mode writes exactly the project's
    files (byte sizes compared with the files in generated_projects/<id>/app), zip mode downloads the same files."""
    import zipfile
    out = subprocess.run(["node", str(FRONTEND / "scripts" / "check_download.mjs"), f"{WEB}/c/{thread_id}"],
                         capture_output=True, text=True, timeout=180)
    steps = {line.split(" ", 1)[0]: json.loads(line.split(" ", 1)[1]) for line in out.stdout.splitlines() if " {" in line}
    if not check(set(steps) == {"folder", "zip"}, "download check ran", out.stderr[-300:]):
        return
    code = httpx.get(f"{API}/api/decisions/{thread_id}/code", timeout=60).json()
    app = Path(httpx.get(f"{API}/api/decisions/{thread_id}/implementation", timeout=30).json()["workspace_dir"]) / "app"
    expected = {f"{code['folder_name']}/{f['path']}": (app / f["path"]).stat().st_size for f in code["files"]}
    written = dict(map(tuple, steps["folder"]["files"]))
    check(written == expected, "folder mode wrote every project file with its exact size, nothing else",
          f"{len(written)} files, {sum(written.values())} bytes")
    check(not any("/node_modules/" in p or "/dist/" in p or p.split("/")[-1].startswith(".env") for p in written),
          "no node_modules, build output or .env files in the download")
    check("Saved" in steps["folder"]["status"] and "npm install" in steps["folder"]["status"],
          "the result says where it was saved and how to run it", steps["folder"]["status"][:90])
    zips = steps["zip"]["files"]
    names = zipfile.ZipFile(zips[0]["path"]).namelist() if zips else []
    check(bool(zips) and zips[0]["name"] == f"{code['folder_name']}.zip" and sorted(names) == sorted(expected),
          "without a folder picker the click downloads the same files as <folder>.zip", zips[0]["name"] if zips else "none")


def ask_check(client: httpx.Client, thread_id: str) -> None:
    print("\n== 5. Ask mode (one real Sonnet call) ==")
    before = len(client.get(f"{API}/api/chats/{thread_id}").json()["messages"])
    question = "In one sentence: which command does the build check run for the tests?"
    started = time.time()
    with client.stream("POST", f"{API}/api/chats/{thread_id}/messages", json={"content": question}, timeout=180) as r:
        answer = "".join(r.iter_text())
    check(r.status_code == 200 and len(answer.strip()) > 10, "streamed a non-empty answer",
          f"{time.time() - started:.1f}s: {answer.strip()[:160]!r}")
    after = client.get(f"{API}/api/chats/{thread_id}").json()["messages"]
    check(len(after) == before + 2 and after[-2]["content"] == question, "question and answer saved in the transcript")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session")
    parser.add_argument("--ask", action="store_true", help="one real Ask-mode question (costs cents)")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    frontend_checks(args.skip_build)
    with httpx.Client(timeout=30) as client:
        try:
            client.get(f"{API}/api/decisions", params={"limit": 1}).raise_for_status()
            client.get(f"{WEB}/").raise_for_status()
        except Exception as exc:                          # noqa: BLE001
            check(False, "dev servers reachable on 8001 / 3001", str(exc))
            return finish()
        thread_id = pick_session(client, args.session)
        if not check(thread_id is not None, "a built session exists", thread_id or "run api_flow.py --auto first"):
            return finish()
        chat = api_checks(client, thread_id)
        page_checks(client, thread_id)
        rendered_checks(thread_id, chat)
        if args.ask:
            ask_check(client, thread_id)
    return finish()


def finish() -> int:
    failed = [label for ok, label in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    print("M10 VERIFY:", "PASS" if not failed else "FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
