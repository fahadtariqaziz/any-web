"""M7: session workspace, path guard, sandbox, dev-server manager. Real subprocesses (python3, git), no network,
no database (MemoryRuntimeStore), everything under pytest's tmp_path."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import timedelta

import psutil
import pytest

from ai_decision_arena.config import get_settings
from ai_decision_arena.schemas import command_problems
from ai_decision_arena.workspace import sandbox
from ai_decision_arena.workspace.paths import PathError, create_workspace, safe_path, workspace_for
from ai_decision_arena.workspace.processes import (MemoryRuntimeStore, ProcessManager, RuntimeRecord, http_answers, now,
                                                   port_is_free)

PY = "python3"
pytestmark = pytest.mark.skipif(shutil.which(PY, path=sandbox.host_tool_path()) is None, reason="needs python3")


@pytest.fixture
def root(tmp_path, monkeypatch):
    settings = get_settings()
    base = tmp_path / "generated_projects"
    monkeypatch.setattr(settings, "generated_projects_dir", base)
    monkeypatch.setattr(settings, "preview_port_range", "4150-4169")
    monkeypatch.setattr(settings, "preview_health_timeout_seconds", 15)
    return base


@pytest.fixture
def ws(root):
    return create_workspace("session-a")


def alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def wait_dead(pid: int, seconds: float = 5) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return False


# --- paths -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "../x", "a/b", ".hidden", "x" * 65, "a b", "sess\x00"])
def test_invalid_session_ids_are_refused(root, bad):
    with pytest.raises(PathError):
        workspace_for(bad)


def test_create_workspace_layout_and_idempotent(root):
    ws = create_workspace("abc-123")
    assert ws.app.is_dir() and ws.home.is_dir() and ws.logs.is_dir()
    assert ws.root == root.resolve() / "abc-123"
    (ws.app / "keep.txt").write_text("x")
    assert (create_workspace("abc-123").app / "keep.txt").read_text() == "x"     # resume keeps the files


def test_safe_path_accepts_project_files(ws):
    assert safe_path(ws, "src/main.js") == ws.app.resolve() / "src" / "main.js"
    assert safe_path(ws, "./index.html") == ws.app.resolve() / "index.html"


@pytest.mark.parametrize("bad", ["", "  ", "../x", "src/../../x", "/etc/passwd", "~/.ssh/id_rsa", "a\\b", "x\x00"])
def test_safe_path_refuses_traversal(ws, bad):
    with pytest.raises(PathError):
        safe_path(ws, bad)


def test_safe_path_refuses_symlink_escapes(root, ws):
    other = create_workspace("session-b")
    (other.app / "secret.txt").write_text("b's file")
    (ws.app / "to_other").symlink_to(other.app)
    (ws.app / "to_etc").symlink_to("/etc")
    (ws.app.parent / "app-evil").mkdir()
    (ws.app / "to_prefix_sibling").symlink_to(ws.app.parent / "app-evil")       # "/…/app-evil" starts with "/…/app"
    for path in ("to_other/secret.txt", "to_etc/passwd", "to_other", "to_prefix_sibling/x"):
        with pytest.raises(PathError):
            safe_path(ws, path)
    (ws.app / "src").mkdir()
    (ws.app / "inner").symlink_to(ws.app / "src")                                 # a link inside app/ is fine
    assert safe_path(ws, "inner/a.js") == ws.app.resolve() / "src" / "a.js"


# --- sandbox: policy ---------------------------------------------------------------------------------------------

def test_shell_operators_refused_in_strings_but_not_inside_argv_items(ws):
    assert sandbox.run(ws, f"{PY} -c \"print(1); print(2)\"").refused
    result = sandbox.run(ws, [PY, "-c", "print(1); print(2)"])
    assert result.ok and result.stdout_tail.split() == ["1", "2"]


def test_command_policy_refuses_option_paths():
    assert command_problems("npm install --prefix=/tmp")
    assert command_problems("npm install --cache=../x")
    assert not command_problems("npm test -- --run=engine")


@pytest.mark.parametrize("command", ["curl http://example.com", "ls && rm x", "git push origin main", "cat /etc/passwd",
                                     "cat ../session-b/app/secret.txt", "rm -rf .", "sh -c ls", "npm publish"])
def test_refused_commands_never_run_and_are_audited(ws, command):
    result = sandbox.run(ws, command)
    assert not result.ok and result.refused and result.exit_code is None and result.duration_seconds == 0
    lines = (ws.logs / "commands.jsonl").read_text().splitlines()
    assert json.loads(lines[-1])["refused"] == result.refused


def test_argument_through_symlink_is_refused(root, ws):
    other = create_workspace("session-b")
    (other.app / "secret.txt").write_text("b's file")
    (ws.app / "leak.txt").symlink_to(other.app / "secret.txt")
    result = sandbox.run(ws, "cat leak.txt")
    assert result.refused and "outside the project" in result.refused[0]
    (ws.app / "own.txt").write_text("mine")
    assert sandbox.run(ws, "cat own.txt").stdout_tail == "mine"


def test_default_timeouts():
    settings = get_settings()
    assert sandbox.default_timeout(["npm", "install"]) == settings.install_timeout_seconds
    assert sandbox.default_timeout(["uv", "sync"]) == settings.install_timeout_seconds
    assert sandbox.default_timeout(["npm", "test"]) == settings.command_timeout_seconds


# --- sandbox: execution ------------------------------------------------------------------------------------------

def test_env_is_built_from_nothing(ws, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-leak")
    monkeypatch.setenv("SOME_HOST_VAR", "host-only")
    result = sandbox.run(ws, [PY, "-c", "import os, json; print(json.dumps(dict(os.environ)))"])
    assert result.ok, result.stderr_tail
    env = json.loads(result.stdout_tail)
    assert "sk-ant-should-never-leak" not in result.stdout_tail
    assert not any(sandbox.secret_like(k) for k in env), env.keys()
    assert "SOME_HOST_VAR" not in env and "DATABASE_URL" not in env
    assert env["HOME"] == str(ws.home) and env["TMPDIR"].startswith(str(ws.builder))
    assert env["PATH"].split(os.pathsep)[1] == str(sandbox.tools_bin())
    assert sys.prefix not in env["PATH"]                                         # not the builder's virtualenv


def test_sandbox_python_is_not_the_builders(ws):
    result = sandbox.run(ws, [PY, "-c", "import sys; print(sys.prefix)"])
    assert result.ok and result.stdout_tail.strip() != sys.prefix


def test_extra_env_refuses_secret_names(ws):
    with pytest.raises(ValueError):
        sandbox.build_env(ws, {"OPENAI_API_KEY": "x"})
    assert sandbox.build_env(ws, {"PORT": "4100"})["PORT"] == "4100"


def test_cwd_is_app_and_exit_code_is_reported(ws):
    result = sandbox.run(ws, [PY, "-c", "import os, sys; print(os.getcwd()); sys.exit(3)"])
    assert result.exit_code == 3 and not result.ok
    assert result.stdout_tail.strip() == str(ws.app.resolve())
    assert not list((ws.builder / "run").glob("*.json"))                         # run file removed afterwards


def test_timeout_kills_the_whole_group(ws):
    script = ("import subprocess, time; c = subprocess.Popen(['sleep', '60']); "
              "open('child.pid', 'w').write(str(c.pid)); time.sleep(60)")
    t0 = time.monotonic()
    result = sandbox.run(ws, [PY, "-c", script], timeout=1.5)
    assert result.timed_out and result.exit_code is None and not result.ok
    assert time.monotonic() - t0 < 10
    assert wait_dead(int((ws.app / "child.pid").read_text()))


def test_children_left_running_are_killed(ws):
    script = "import subprocess; c = subprocess.Popen(['sleep', '60']); open('child.pid', 'w').write(str(c.pid))"
    assert sandbox.run(ws, [PY, "-c", script]).ok
    assert wait_dead(int((ws.app / "child.pid").read_text()))


def test_output_is_capped_to_the_tail(ws, monkeypatch):
    monkeypatch.setattr(get_settings(), "command_output_cap_bytes", 5000)
    result = sandbox.run(ws, [PY, "-c", "print('x' * 100000); print('THE-END')"])
    assert result.ok and result.output_truncated
    assert len(result.stdout_tail) <= 5000 and result.stdout_tail.rstrip().endswith("THE-END")


def test_git_cannot_reach_the_builders_repo(tmp_path, monkeypatch):
    repo = tmp_path / "builder_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    monkeypatch.setattr(get_settings(), "generated_projects_dir", repo / "generated_projects")
    ws = create_workspace("session-git")
    assert subprocess.run(["git", "status"], cwd=ws.app, capture_output=True).returncode == 0   # host git: sees it
    result = sandbox.run(ws, "git status")
    assert result.exit_code == 128 and "not a git repository" in result.stderr_tail
    assert sandbox.run(ws, "git init -q").ok and sandbox.run(ws, "git status").ok              # its own repo works


# --- processes ---------------------------------------------------------------------------------------------------

SERVER = f"{PY} -m http.server {{port}} --bind 127.0.0.1"


@pytest.fixture
def manager(root):
    pm = ProcessManager(store=MemoryRuntimeStore())
    yield pm
    pm.stop_all()


def test_dev_server_ready_only_after_http_answer_then_stops(ws, manager):
    record = manager.start(ws, SERVER)
    assert record.state == "ready", record.last_error
    assert 4150 <= record.port <= 4169 and record.url == f"http://localhost:{record.port}"
    assert http_answers(record.port) and record.ready_at and record.pid
    assert json.loads((ws.builder / "runtime.json").read_text())["state"] == "ready"
    stopped = manager.stop(ws.session_id)
    assert stopped.state == "stopped" and wait_dead(record.pid) and port_is_free(record.port)


def test_two_sessions_get_their_own_ports(root, manager):
    a, b = create_workspace("s-one"), create_workspace("s-two")
    ra, rb = manager.start(a, SERVER), manager.start(b, SERVER)
    assert ra.state == rb.state == "ready" and ra.port != rb.port
    manager.stop("s-one")
    assert manager.status("s-two").state == "ready" and http_answers(rb.port)     # one stop doesn't touch the other


def test_server_that_exits_fails_with_its_output(ws, manager):
    record = manager.start(ws, [PY, "-c", "import sys; print('boom: missing module'); sys.exit(2)"])
    assert record.state == "failed"
    assert "code 2" in record.last_error and "boom: missing module" in record.last_error


def test_server_that_never_answers_is_killed(ws, manager, monkeypatch):
    monkeypatch.setattr(get_settings(), "preview_health_timeout_seconds", 1.5)
    record = manager.start(ws, [PY, "-c", "import time; time.sleep(60)"])
    assert record.state == "failed" and "no HTTP answer" in record.last_error
    assert wait_dead(record.pid)


def test_refused_dev_command_starts_nothing(ws, manager):
    record = manager.start(ws, "curl http://example.com")
    assert record.state == "failed" and record.last_error.startswith("refused") and record.pid is None


def test_restart_replaces_the_process(ws, manager):
    first = manager.start(ws, SERVER)
    second = manager.restart(ws)
    assert second.state == "ready", second.last_error
    assert second.pid != first.pid and wait_dead(first.pid)


def test_status_notices_a_dead_server(ws, manager):
    record = manager.start(ws, SERVER)
    os.killpg(record.pid, signal.SIGKILL)
    assert wait_dead(record.pid)
    assert manager.status(ws.session_id).state == "failed"


def test_idle_previews_are_stopped(ws, manager):
    record = manager.start(ws, SERVER)
    assert manager.stop_idle() == []
    old = manager.store.get(ws.session_id)
    old.last_seen_at = now() - timedelta(hours=2)
    manager.store.save(old)
    assert manager.stop_idle(idle_minutes=30) == [ws.session_id]
    assert manager.status(ws.session_id).state == "stopped" and wait_dead(record.pid)


def test_ports_run_out_cleanly(root, manager, monkeypatch):
    monkeypatch.setattr(get_settings(), "preview_port_range", "4168-4168")
    assert manager.start(create_workspace("s-one"), SERVER).state == "ready"
    with pytest.raises(RuntimeError, match="no free preview port"):
        manager.start(create_workspace("s-two"), SERVER)


def test_reconcile_adopts_live_servers_and_marks_dead_ones(root, manager):
    a, b = create_workspace("s-live"), create_workspace("s-dead")
    live, dead = manager.start(a, SERVER), manager.start(b, SERVER)
    os.killpg(dead.pid, signal.SIGKILL)
    manager._children[b.session_id].wait()
    restarted = ProcessManager(store=manager.store)          # a new backend process, same registry
    summary = restarted.reconcile()
    assert summary["adopted"] == ["s-live"] and summary["lost"] == ["s-dead"]
    assert restarted.status("s-live").state == "ready" and restarted.status("s-dead").state == "failed"
    assert restarted.stop("s-live").state == "stopped" and wait_dead(live.pid)


def write_run_file(ws, pid: int, started_at: float | None, owner_alive: bool) -> None:
    owner = {"owner_pid": os.getpid(), "owner_started_at": sandbox.process_started_at(os.getpid()) if owner_alive
             else 1.0}                                         # 1.0: the owning builder process is gone
    sandbox.run_file(ws, pid).parent.mkdir(parents=True, exist_ok=True)
    sandbox.run_file(ws, pid).write_text(json.dumps({"pid": pid, "started_at": started_at, "command": "x"} | owner))


def test_reconcile_kills_orphan_commands_but_not_reused_pids(ws, manager):
    orphan = subprocess.Popen(["sleep", "60"], start_new_session=True)
    write_run_file(ws, orphan.pid, sandbox.process_started_at(orphan.pid), owner_alive=False)
    write_run_file(ws, os.getpid(), 1.0, owner_alive=False)     # its pid now belongs to someone else (this test)
    summary = manager.reconcile()
    assert summary["killed"] == [orphan.pid]
    orphan.wait(timeout=5)
    assert alive(os.getpid()) and not list((ws.builder / "run").glob("*.json"))


def test_reconcile_leaves_commands_of_a_live_builder_alone(ws, manager):
    """uvicorn --reload: the new API process must not kill what another live process (a script, a worker) runs."""
    busy = subprocess.Popen(["sleep", "60"], start_new_session=True)
    sandbox.track(ws, busy.pid, "sleep 60")                     # owner = this (live) test process
    try:
        assert manager.reconcile()["killed"] == []
        assert alive(busy.pid) and sandbox.run_file(ws, busy.pid).exists()
    finally:
        busy.kill()
        busy.wait()


def test_reconcile_does_not_fail_a_server_another_process_is_starting(ws, manager):
    manager.store.save(RuntimeRecord(thread_id=ws.session_id, state="starting", command="npm start", port=4155,
                                     started_at=now()))
    assert manager.reconcile()["lost"] == [] and manager.status(ws.session_id).state == "starting"


def test_a_foreign_wildcard_listener_is_never_mistaken_for_our_preview(root, manager, monkeypatch):
    """Regression (M9 E2E): a Node app listening on *:4100 made 127.0.0.1:4100 look free (SO_REUSEADDR bind on
    macOS); a second session got 4100 and its health check was answered by the OTHER app."""
    from ai_decision_arena.workspace.processes import listens_on, port_accepts
    monkeypatch.setattr(get_settings(), "preview_port_range", "4160-4161")
    foreign = subprocess.Popen([PY, "-m", "http.server", "4160", "--bind", "::"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        while not port_accepts(4160) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert port_accepts(4160) and not port_is_free(4160)
        assert listens_on(foreign.pid, 4160)
        record = manager.start(create_workspace("s-isolated"), SERVER)
        assert record.state == "ready" and record.port == 4161                     # not the foreign app's port
        assert listens_on(record.pid, 4161) and not listens_on(record.pid, 4160)     # ours ≠ the foreign one
    finally:
        os.killpg(foreign.pid, signal.SIGKILL)
        foreign.wait()
