"""Dev servers (live previews) per session: start, health-check, stop, restart, idle stop, startup reconcile.

Spec §9: run each generated app in its own environment, show useful errors when it fails to start, keep one project
from disturbing another. Facts here come only from the OS and HTTP, never from a model:
- `ready` is set ONLY after an HTTP answer from http://127.0.0.1:<port>/ (any status: the server is up) AND the
  listening socket on that port belongs to the started process tree (never another app answering on the port);
- `failed` carries the exit code / timeout and the tail of the server's log (.builder/logs/dev-server.log);
- each session gets its own port from `preview_port_range` (registry + a real bind test), passed as $PORT; a command
  may also contain "{port}" (Vite ignores $PORT: "npm run dev -- --port {port} --strictPort");
- the command goes through the sandbox policy and environment (sandbox.check_command / build_env), cwd app/;
- the registry (project_runtimes table; a dict in tests) survives a backend restart: `reconcile()` at startup adopts
  servers whose pid AND start time still match, marks the rest failed, and kills the process groups of sandbox
  commands that were running when the previous backend died (.builder/run/*.json).
"""

import json
import logging
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Protocol

import psutil
from pydantic import BaseModel

from ai_decision_arena.config import get_settings
from ai_decision_arena.workspace import app_settings
from ai_decision_arena.workspace.paths import SHARED_DIR, Workspace, projects_root, workspace_for
from ai_decision_arena.workspace.sandbox import (build_env, check_command, is_same_process, kill_group,
                                                 process_started_at, read_tail, resolve_executable)

log = logging.getLogger(__name__)

RuntimeState = Literal["starting", "ready", "failed", "stopped"]
ACTIVE: tuple[str, ...] = ("starting", "ready")
LOG_NAME = "dev-server.log"
LOG_TAIL_BYTES = 4000
POLL_SECONDS = 0.25


class RuntimeRecord(BaseModel):
    """One session's dev server. Mirrors a project_runtimes row and .builder/runtime.json."""

    thread_id: str
    state: RuntimeState
    command: str
    port: int | None = None
    pid: int | None = None
    process_started_at: float | None = None
    url: str | None = None
    last_error: str | None = None
    log_path: str | None = None
    started_at: datetime | None = None
    ready_at: datetime | None = None
    stopped_at: datetime | None = None
    last_seen_at: datetime | None = None


class RuntimeStore(Protocol):
    def get(self, thread_id: str) -> RuntimeRecord | None: ...
    def save(self, record: RuntimeRecord) -> None: ...
    def active(self) -> list[RuntimeRecord]: ...


class MemoryRuntimeStore:
    """For tests and runs without the database (PERSIST_RESULTS=false)."""

    def __init__(self) -> None:
        self._rows: dict[str, RuntimeRecord] = {}

    def get(self, thread_id: str) -> RuntimeRecord | None:
        row = self._rows.get(thread_id)
        return row.model_copy() if row else None

    def save(self, record: RuntimeRecord) -> None:
        self._rows[record.thread_id] = record.model_copy()

    def active(self) -> list[RuntimeRecord]:
        return [r.model_copy() for r in self._rows.values() if r.state in ACTIVE]


class DbRuntimeStore:
    """The project_runtimes table."""

    def get(self, thread_id: str) -> RuntimeRecord | None:
        from ai_decision_arena.db.repository import get_runtime
        row = get_runtime(thread_id)
        return RuntimeRecord(**row) if row else None

    def save(self, record: RuntimeRecord) -> None:
        from ai_decision_arena.db.repository import save_runtime
        save_runtime(record.thread_id, record.model_dump(exclude={"thread_id"}))

    def active(self) -> list[RuntimeRecord]:
        from ai_decision_arena.db.repository import list_runtimes
        return [RuntimeRecord(**row) for row in list_runtimes(ACTIVE)]


def default_store() -> RuntimeStore:
    return DbRuntimeStore() if get_settings().persist_results else MemoryRuntimeStore()


def now() -> datetime:
    return datetime.now(timezone.utc)


def port_range() -> range:
    low, high = (int(x) for x in get_settings().preview_port_range.split("-"))
    return range(low, high + 1)


def port_accepts(port: int, timeout: float = 0.3) -> bool:
    """Something accepts TCP connections on this port on loopback (127.0.0.1 or ::1)."""
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                if sock.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def port_is_free(port: int) -> bool:
    """Nobody listens on the port. A connect test first: on macOS a bind with SO_REUSEADDR to 127.0.0.1 SUCCEEDS
    while another process listens on the wildcard address (`*:4100`, e.g. a Node server), so the bind alone said
    "free" and two previews shared a port. Then a real bind on 127.0.0.1 and ::1."""
    if port_accepts(port):
        return False
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                # like the dev servers themselves: a port in TIME_WAIT (after our health check) is free, a
                # LISTENING port is not (SO_REUSEADDR does not allow binding over a listener)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
        except OSError as exc:
            if family == socket.AF_INET6 and exc.errno in (47, 49, 97, 99):   # no IPv6 on this host: ignore
                continue
            return False
    return True


def http_answers(port: int, timeout: float = 2.0) -> bool:
    """Any HTTP response (200, 404, 500...) means a server is listening and speaking HTTP."""
    for host in ("127.0.0.1", "[::1]"):
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/", timeout=timeout):
                return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return False


_manager: "ProcessManager | None" = None
_manager_lock = threading.Lock()


def get_manager() -> "ProcessManager":
    """The process-wide manager: the preview node (graph thread) and the API endpoints must share one registry of
    child processes. Created on first use (store: DB, or memory when PERSIST_RESULTS=false)."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = ProcessManager()
        return _manager


def set_manager(manager: "ProcessManager | None") -> None:
    global _manager
    with _manager_lock:
        _manager = manager


class IdleStopper:
    """Trigger (spec §10.8): every `preview_idle_check_seconds`, stop previews nobody looked at for
    `preview_idle_minutes` (GET /preview touches them)."""

    def __init__(self, manager: "ProcessManager") -> None:
        self.manager = manager
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="preview-idle-stopper", daemon=True)

    def _loop(self) -> None:
        while not self._stop.wait(get_settings().preview_idle_check_seconds):
            try:
                stopped = self.manager.stop_idle()
                if stopped:
                    log.info("idle previews stopped: %s", stopped)
            except Exception:                       # never let the trigger thread die
                log.exception("idle preview check failed")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def listens_on(pid: int, port: int) -> bool:
    """The process `pid` or one of its children holds a LISTEN socket on `port` (it is OUR server that answers)."""
    try:
        root = psutil.Process(pid)
        procs = [root, *root.children(recursive=True)]
    except psutil.Error:
        return False
    for proc in procs:
        try:
            if any(c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port
                   for c in proc.net_connections(kind="inet")):
                return True
        except psutil.Error:
            continue
    return False


class ProcessManager:
    """One per API process (app.state.processes). Thread-safe for start/stop; the health wait runs unlocked."""

    def __init__(self, store: RuntimeStore | None = None, root: Path | None = None) -> None:
        self.store = store or default_store()
        self.root = root
        self._lock = threading.RLock()       # start / stop / status: a stop must never be read as a crash
        self._children: dict[str, subprocess.Popen] = {}   # started by THIS process (reaped on stop)

    # --- helpers ---------------------------------------------------------------------------------------------
    def _ws(self, thread_id: str) -> Workspace:
        return workspace_for(thread_id, self.root)

    def _save(self, record: RuntimeRecord) -> RuntimeRecord:
        self.store.save(record)
        ws = self._ws(record.thread_id)
        if ws.builder.is_dir():
            (ws.builder / "runtime.json").write_text(record.model_dump_json(indent=2))
        return record

    def _alive(self, record: RuntimeRecord) -> bool:
        child = self._children.get(record.thread_id)
        if child is not None and child.pid == record.pid and child.poll() is not None:
            return False                                       # our own child exited (and is now reaped)
        return is_same_process(record.pid, record.process_started_at)

    @staticmethod
    def _being_started(record: RuntimeRecord) -> bool:
        """Saved as "starting" but no pid yet: a (possibly other) process is between registering and spawning it."""
        grace = timedelta(seconds=get_settings().preview_health_timeout_seconds)
        return record.pid is None and record.started_at is not None and now() - record.started_at < grace

    def _exit_note(self, record: RuntimeRecord) -> str:
        child = self._children.get(record.thread_id)
        code = child.poll() if child is not None and child.pid == record.pid else None
        return f"the dev server exited (code {code})" if code is not None else "the dev server is no longer running"

    def log_tail(self, thread_id: str, max_bytes: int = LOG_TAIL_BYTES) -> str:
        path = self._ws(thread_id).logs / LOG_NAME
        return read_tail(path, max_bytes)[0] if path.exists() else ""

    def _fail(self, record: RuntimeRecord, error: str) -> RuntimeRecord:
        tail = self.log_tail(record.thread_id).strip()
        record.state, record.stopped_at = "failed", now()
        record.last_error = error + (f"\n--- last output ---\n{tail[-1500:]}" if tail else "")
        return self._save(record)

    def _allocate_port(self) -> int:
        taken = {r.port for r in self.store.active() if r.port}
        for port in port_range():
            if port not in taken and port_is_free(port):
                return port
        raise RuntimeError(f"no free preview port in {get_settings().preview_port_range}")

    # --- lifecycle -------------------------------------------------------------------------------------------
    def start(self, ws: Workspace, command: str | Sequence[str], *, wait: bool = True) -> RuntimeRecord:
        """Start the session's dev server (stopping its previous one). With wait=True, returns after the health
        check: state "ready" (HTTP answered) or "failed" (exited, refused, or no answer in time)."""
        self.stop(ws.session_id, reason="restarted")
        with self._lock:
            port = self._allocate_port()
            if isinstance(command, str):
                command = command.replace("{port}", str(port))
            else:
                command = [a.replace("{port}", str(port)) for a in command]
            text, argv, problems = check_command(ws, command)
            record = RuntimeRecord(thread_id=ws.session_id, state="starting", command=text, port=port,
                                   started_at=now(), log_path=str(ws.logs / LOG_NAME))
            if problems:
                record.port = None
                return self._fail(record, "refused: " + "; ".join(problems))
            # + the app's own settings the user gave in the Preview tab (app_settings: never in app/, never to a model)
            env = build_env(ws, {"PORT": str(port), "BROWSER": "none"}) | app_settings.env_values(ws)
            executable = resolve_executable(argv, env)
            if not executable:
                record.port = None
                return self._fail(record, f"'{argv[0]}' is not installed")
            self._save(record)                                    # reserves the port in the registry
            ws.logs.mkdir(parents=True, exist_ok=True)
            with (ws.logs / LOG_NAME).open("wb") as out:          # truncated per start
                child = subprocess.Popen([executable, *argv[1:]], cwd=ws.app, env=env, stdin=subprocess.DEVNULL,
                                         stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
            self._children[ws.session_id] = child
            record.pid, record.process_started_at = child.pid, process_started_at(child.pid)
            self._save(record)
        log.info("preview %s: started pid %s on port %s (%s)", ws.session_id, record.pid, port, text)
        return self.wait_ready(ws.session_id) if wait else record

    def wait_ready(self, thread_id: str, timeout: float | None = None) -> RuntimeRecord:
        record = self.store.get(thread_id)
        if record is None or record.state != "starting":
            return record
        deadline = time.monotonic() + (timeout or get_settings().preview_health_timeout_seconds)
        while time.monotonic() < deadline:
            if not self._alive(record):
                return self._fail(record, self._exit_note(record))
            if http_answers(record.port) and listens_on(record.pid, record.port):   # an answer from OUR server
                record.state, record.ready_at = "ready", now()
                record.url, record.last_seen_at = f"http://localhost:{record.port}", record.ready_at
                log.info("preview %s: ready at %s", thread_id, record.url)
                return self._save(record)
            time.sleep(POLL_SECONDS)
        kill_group(record.pid)
        child = self._children.pop(thread_id, None)
        if child is not None:
            child.wait(timeout=5)
        return self._fail(record, f"no HTTP answer on port {record.port} within "
                                  f"{timeout or get_settings().preview_health_timeout_seconds:.0f} s")

    def status(self, thread_id: str) -> RuntimeRecord | None:
        """The current record; an active server whose process died is marked failed with its log tail."""
        with self._lock:                     # inside the lock: a concurrent stop() finishes first (no false "failed")
            record = self.store.get(thread_id)
            if record and record.state in ACTIVE and not self._alive(record) and not self._being_started(record):
                return self._fail(record, self._exit_note(record))
            return record

    def touch(self, thread_id: str) -> None:
        """The preview was looked at (resets the idle clock)."""
        record = self.store.get(thread_id)
        if record and record.state in ACTIVE:
            record.last_seen_at = now()
            self._save(record)

    def stop(self, thread_id: str, reason: str = "stopped") -> RuntimeRecord | None:
        with self._lock:
            record = self.store.get(thread_id)
            if record is None or record.state not in ACTIVE:
                return record
            if self._alive(record):                 # pid AND start time match: it is ours to kill
                kill_group(record.pid)
            child = self._children.pop(thread_id, None)
            if child is not None:
                child.wait(timeout=5)
            record.state, record.stopped_at, record.last_error = "stopped", now(), None
            log.info("preview %s: stopped (%s)", thread_id, reason)
            return self._save(record)

    def restart(self, ws: Workspace, command: str | Sequence[str] | None = None) -> RuntimeRecord:
        previous = self.store.get(ws.session_id)
        if command is None and previous is None:
            raise ValueError(f"session {ws.session_id} has no dev server command to restart")
        return self.start(ws, command or previous.command)

    def stop_idle(self, idle_minutes: float | None = None) -> list[str]:
        """Stop previews nobody has looked at for `preview_idle_minutes`. Returns the stopped session ids."""
        cutoff = now() - timedelta(minutes=idle_minutes if idle_minutes is not None
                                   else get_settings().preview_idle_minutes)
        stopped = []
        for record in self.store.active():
            seen = record.last_seen_at or record.ready_at or record.started_at
            if seen is not None and seen < cutoff:
                self.stop(record.thread_id, reason="idle")
                stopped.append(record.thread_id)
        return stopped

    def stop_all(self) -> list[str]:
        return [r.thread_id for r in self.store.active() if self.stop(r.thread_id, reason="shutdown")]

    def reconcile(self) -> dict[str, list]:
        """Startup: adopt live dev servers, mark dead ones failed, kill sandbox commands whose builder process died
        (uvicorn --reload restarts the API on every code change: a command another LIVE process runs is left alone)."""
        adopted, lost, killed = [], [], []
        for record in self.store.active():
            if is_same_process(record.pid, record.process_started_at):
                adopted.append(record.thread_id)
            elif self._being_started(record):
                continue
            else:
                self._fail(record, "the dev server was not running when the builder restarted")
                lost.append(record.thread_id)
        base = (self.root or projects_root()).resolve()
        for run_file in base.glob(f"*/.builder/run/*.json"):
            if run_file.parts[-4] == SHARED_DIR:
                continue
            try:
                info = json.loads(run_file.read_text())
            except (OSError, ValueError):
                info = {}
            if is_same_process(info.get("owner_pid"), info.get("owner_started_at")):
                continue                                  # its builder process is alive: not an orphan
            if is_same_process(info.get("pid"), info.get("started_at")):
                kill_group(info["pid"])
                killed.append(info["pid"])
            run_file.unlink(missing_ok=True)
        if adopted or lost or killed:
            log.info("preview reconcile: adopted %s, lost %s, killed orphan groups %s", adopted, lost, killed)
        return {"adopted": adopted, "lost": lost, "killed": killed}
