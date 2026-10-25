"""M7 live check: session workspace, sandbox and dev-server manager on the real machine (no LLM calls).

Uses the real generated_projects/ folder (inside the ai-lab-2 repo, git-ignored), real npm / node / git and the real
database (project_runtimes). Steps:
1. create a workspace; `npm init -y` in the sandbox; refused commands never run;
2. the builder's secrets (loaded from backend/.env) are NOT visible to a sandboxed process; git inside app/ does not
   see the ai-lab-2 repository around it; a hanging command is killed at its timeout;
3. a tiny static server (written through safe_path, started with `npm start`, $PORT injected) is health-checked,
   answers HTTP 200 with its page, and is registered in project_runtimes; a second session gets another port;
4. a "restarted backend" (new ProcessManager on the same table) adopts the running servers; stop frees the ports.
    uv run python scripts/verify_m7.py            (--keep leaves the workspaces in generated_projects/)
"""

import os
import shutil
import sys
import time
import urllib.request

from ai_decision_arena.config import get_settings
from ai_decision_arena.db.repository import get_runtime
from ai_decision_arena.workspace import sandbox
from ai_decision_arena.workspace.paths import create_workspace, safe_path
from ai_decision_arena.workspace.processes import DbRuntimeStore, ProcessManager, port_is_free

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


SERVER_JS = """const http = require("http");
const port = Number(process.env.PORT);
http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "text/html" });
  res.end("<h1>Hello from SESSION</h1>");
}).listen(port, "127.0.0.1", () => console.log(`listening on ${port}`));
"""

settings = get_settings()
stamp = int(time.time())
ids = [f"verify-m7-{stamp}", f"verify-m7-{stamp}-b"]
print(f"generated_projects: {settings.generated_projects_dir}")
print(f"preview ports: {settings.preview_port_range}\n")

print("1. workspace + sandbox")
ws = create_workspace(ids[0])
check(ws.app.is_dir() and ws.home.is_dir(), f"workspace created: {ws.root}")
result = sandbox.run(ws, "npm init -y", label="init")
check(result.ok and (ws.app / "package.json").exists(), f"npm init -y → {result.summary()}")
for bad in ("git push origin main", "cat /etc/passwd", "curl https://example.com", "ls && rm package.json"):
    r = sandbox.run(ws, bad)
    check(bool(r.refused) and r.exit_code is None, f"refused: {bad!r}")
check((ws.app / "package.json").exists(), "nothing was deleted by the refused commands")

print("\n2. isolation")
check(bool(os.environ.get("ANTHROPIC_API_KEY")), "the builder process itself has ANTHROPIC_API_KEY (so the next check means something)")
r = sandbox.run(ws, ["node", "-e", "console.log(Object.keys(process.env).sort().join(','))"])
names = r.stdout_tail.strip().split(",")
leaked = [n for n in names if sandbox.secret_like(n) or n in ("DATABASE_URL",)]
check(r.ok and not leaked, f"sandboxed env has {len(names)} variables, no secrets ({', '.join(names)})")
r = sandbox.run(ws, "git status")
check(r.exit_code == 128 and "not a git repository" in r.stderr_tail,
      "git in app/ does not find the ai-lab-2 repository around it")
t0 = time.monotonic()
r = sandbox.run(ws, ["node", "-e", "setTimeout(() => {}, 60000)"], timeout=2)
check(r.timed_out and time.monotonic() - t0 < 10, f"hanging command killed at its timeout ({r.summary()})"
      + ("" if r.timed_out else f" stderr: {r.stderr_tail[-300:]!r}"))

print("\n3. dev server")
for session_id in ids:
    w = create_workspace(session_id)
    safe_path(w, "server.js").write_text(SERVER_JS.replace("SESSION", session_id))
    safe_path(w, "package.json").write_text('{"name": "verify-m7", "private": true, '
                                            '"scripts": {"start": "node server.js"}}\n')
manager = ProcessManager(store=DbRuntimeStore())
records = []
for session_id in ids:
    t0 = time.monotonic()
    rec = manager.start(create_workspace(session_id), "npm start")
    records.append(rec)
    check(rec.state == "ready", f"{session_id}: {rec.state} on port {rec.port} in {time.monotonic() - t0:.1f}s"
                                + (f" ({rec.last_error})" if rec.last_error else ""))
if all(r.state == "ready" for r in records):
    for rec in records:
        with urllib.request.urlopen(rec.url, timeout=5) as resp:
            body = resp.read().decode()
        check(resp.status == 200 and rec.thread_id in body, f"GET {rec.url} → {resp.status} {body!r}")
    check(records[0].port != records[1].port, "the two sessions have different ports")
    row = get_runtime(ids[0])
    check(row is not None and row["state"] == "ready" and row["port"] == records[0].port,
          f"project_runtimes row: state={row and row['state']} port={row and row['port']} pid={row and row['pid']}")

print("\n4. restart of the backend, then stop")
summary = ProcessManager(store=DbRuntimeStore()).reconcile()
check(set(ids) <= set(summary["adopted"]), f"a new manager adopts the running servers: {summary}")
for rec in records:
    stopped = manager.stop(rec.thread_id)
    check(stopped is not None and stopped.state == "stopped", f"{rec.thread_id}: stopped")
time.sleep(0.5)
for rec in records:
    if rec.port:
        check(port_is_free(rec.port), f"port {rec.port} is free again")
check(get_runtime(ids[0])["state"] == "stopped", "project_runtimes row says stopped")
lines = (ws.logs / "commands.jsonl").read_text().splitlines()
check(len(lines) >= 8, f"audit log has {len(lines)} commands (.builder/logs/commands.jsonl)")

if "--keep" not in sys.argv and not failures:
    for session_id in ids:
        shutil.rmtree(create_workspace(session_id).root)
    print("\n(workspaces removed; run with --keep to inspect them)")

print(f"\nM7 VERIFY: {'PASS' if not failures else 'FAIL'}")
for f in failures:
    print(f"  - {f}")
sys.exit(1 if failures else 0)
