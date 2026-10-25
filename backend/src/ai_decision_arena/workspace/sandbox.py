"""Run ONE command inside a session's app/ folder (handoff.md section 6, spec §9 / §10.4 / §10.7).

What Python guarantees for every command (the LLM never sets any of this):
- policy: the same check as the plan (`schemas.command_problems`: allowlisted executable, no shell operators, no
  push/publish, no absolute / '~' / '..' paths), plus: an argument naming an existing path must stay inside app/
  after symlinks are resolved;
- argv only (no shell), `cwd = app/`, stdin closed;
- environment built from NOTHING: none of the builder's variables (API keys, DATABASE_URL...) can leak. PATH is a
  folder of symlinks to the allowlisted tools + /usr/bin:/bin; HOME and TMPDIR are inside the session's .builder/;
  npm's global prefix is in the session; GIT_CEILING_DIRECTORIES stops git from finding the BUILDER's repository
  above generated_projects/ (without it `git add/commit` in app/ would write into ai-lab-2's own repo);
- its own process group, killed on timeout (TERM, then KILL) and after the command ends (no stray children);
- output: the last `command_output_cap_bytes` of stdout and of stderr;
- every command (refused ones too) is appended to .builder/logs/commands.jsonl (audit log);
- while it runs, .builder/run/<pid>.json holds its pid + start time AND its owner's (the builder process that ran
  it), so a restarted builder can kill the groups whose owner died mid-command (ProcessManager.reconcile) without
  touching commands another live process (a second worker, a script) is running; pid + start time survive pid reuse.
What it does NOT do on the host (v1): memory/CPU limits, network blocking, or stopping a package.json script from
running other programs; `npm test` runs whatever the project's scripts say. That containment is M12 (Docker).
"""

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import psutil
from pydantic import BaseModel, Field

from ai_decision_arena.config import get_settings
from ai_decision_arena.schemas import ALLOWED_EXECUTABLES, command_problems
from ai_decision_arena.workspace.paths import SHARED_DIR, PathError, Workspace, safe_path

SYSTEM_PATH = ("/usr/bin", "/bin")                      # sh and env (script shebangs) live here
SECRET_NAME_RE = re.compile(r"KEY|TOKEN|SECRET|PASSW|CREDENTIAL|COOKIE|^DATABASE_URL$|^(ANTHROPIC|TAVILY|LANGSMITH|"
                            r"LANGCHAIN|OPENAI|AWS|GH|GITHUB)_", re.I)
INSTALL_COMMANDS = {("npm", "install"), ("npm", "i"), ("npm", "ci"), ("pnpm", "install"), ("pnpm", "i"),
                    ("pnpm", "add"), ("uv", "sync"), ("uv", "add"), ("pip", "install")}
KILL_GRACE_SECONDS = 3
AUDIT_TAIL_CHARS = 4000


class CommandResult(BaseModel):
    """What happened, measured by Python: exit code, timeout, output tails. `ok` is the only success signal."""

    command: str
    argv: list[str] = Field(default_factory=list)
    ok: bool = False
    exit_code: int | None = None                  # None: refused, not found, or killed before exiting
    refused: list[str] = Field(default_factory=list)
    timed_out: bool = False
    stdout_tail: str = ""
    stderr_tail: str = ""
    output_truncated: bool = False
    duration_seconds: float = 0.0
    started_at: str = ""
    label: str = ""

    def summary(self) -> str:
        if self.refused:
            return f"refused: {'; '.join(self.refused)}"
        if self.timed_out:
            return f"timed out after {self.duration_seconds:.0f}s"
        return f"exit {self.exit_code} in {self.duration_seconds:.1f}s"


# --- environment -----------------------------------------------------------------------------------------------

def shared_dir() -> Path:
    from ai_decision_arena.workspace.paths import projects_root
    return projects_root() / SHARED_DIR


@lru_cache
def _tools_bin(shared: Path, host_path: str) -> Path:
    """A folder with a symlink per allowlisted executable found on the builder's PATH (missing ones are left out,
    so `pytest` without a project venv fails with 'not installed' instead of finding some other binary)."""
    bin_dir = shared / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ALLOWED_EXECUTABLES:
        found = shutil.which(name, path=host_path)
        link = bin_dir / name
        if found and not link.is_symlink():
            link.symlink_to(found)
    return bin_dir


def host_tool_path() -> str:
    """The builder's PATH without its own virtualenv: generated projects must not run the builder's Python."""
    venvs = {Path(p).resolve() for p in (os.environ.get("VIRTUAL_ENV"), sys.prefix if sys.prefix != sys.base_prefix
                                         else None) if p}
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not any(v == Path(d).resolve() or v in Path(d).resolve().parents for v in venvs)]
    return os.pathsep.join(keep)


def tools_bin() -> Path:
    return _tools_bin(shared_dir(), host_tool_path())


def secret_like(name: str) -> bool:
    return bool(SECRET_NAME_RE.search(name))


def build_env(ws: Workspace, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """The complete environment of a sandboxed process. Starts from an empty dict (nothing inherited)."""
    settings = get_settings()
    cache_root = shared_dir() if settings.share_package_cache else ws.home / ".cache"
    tmp = ws.builder / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.pathsep.join([str(ws.app / "node_modules" / ".bin"), str(tools_bin()), *SYSTEM_PATH]),
        "HOME": str(ws.home),
        "TMPDIR": str(tmp),
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
        "CI": "1",                                     # non-interactive test runners / installers
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "npm_config_cache": str(cache_root / "npm"),
        "npm_config_prefix": str(ws.home / ".npm-global"),     # `npm install -g` stays in the session
        "npm_config_update_notifier": "false",
        "npm_config_fund": "false",
        "npm_config_audit": "false",
        "UV_CACHE_DIR": str(cache_root / "uv"),
        "PIP_CACHE_DIR": str(cache_root / "pip"),
        "PIP_REQUIRE_VIRTUALENV": "1",                 # never into the host's Python
        "GIT_CEILING_DIRECTORIES": str(ws.root.parent),  # don't discover the builder's repo above generated_projects
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    for name, value in (extra or {}).items():
        if secret_like(name):
            raise ValueError(f"refusing to pass {name!r} into a generated project's process (looks like a secret)")
        env[name] = str(value)
    return env


# --- policy ------------------------------------------------------------------------------------------------------

def to_argv(command: str | Sequence[str]) -> tuple[str, list[str]]:
    if isinstance(command, str):
        try:
            return command, shlex.split(command)
        except ValueError:
            return command, []
    argv = [str(a) for a in command]
    return shlex.join(argv), argv


def argument_problems(ws: Workspace, argv: list[str]) -> list[str]:
    """Arguments that name an existing file or link must stay inside app/ once symlinks are resolved."""
    problems = []
    for arg in argv[1:]:
        for value in ([arg.split("=", 1)[1]] if arg.startswith("-") and "=" in arg else [arg]):
            if not value or value.startswith("-") or not os.path.lexists(ws.app / value):
                continue
            try:
                safe_path(ws, value)
            except PathError as exc:
                problems.append(str(exc))
    return problems


def check_command(ws: Workspace, command: str | Sequence[str]) -> tuple[str, list[str], list[str]]:
    """(command text, argv, problems). Empty problems = allowed to run."""
    text, argv = to_argv(command)
    problems = command_problems(text, shell_operators=isinstance(command, str))
    if not problems:
        problems = argument_problems(ws, argv)
    return text, argv, problems


def default_timeout(argv: list[str]) -> float:
    settings = get_settings()
    return settings.install_timeout_seconds if tuple(argv[:2]) in INSTALL_COMMANDS else settings.command_timeout_seconds


def resolve_executable(argv: list[str], env: Mapping[str, str]) -> str | None:
    return shutil.which(argv[0], path=env["PATH"]) if argv else None


# --- processes -------------------------------------------------------------------------------------------------

def kill_group(pgid: int, grace: float = KILL_GRACE_SECONDS) -> None:
    """TERM the whole process group, then KILL whatever is left after `grace` seconds."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def read_tail(path: Path, cap: int) -> tuple[str, bool]:
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > cap:
            fh.seek(size - cap)
        data = fh.read()
    return data.decode("utf-8", errors="replace"), size > cap


def process_started_at(pid: int) -> float | None:
    try:
        return psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def is_same_process(pid: int | None, started_at: float | None) -> bool:
    """True when `pid` is still the very process we started (alive, not a zombie, same start time)."""
    if not pid or started_at is None:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.status() != psutil.STATUS_ZOMBIE and abs(proc.create_time() - started_at) < 0.01
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def run_file(ws: Workspace, pid: int) -> Path:
    return ws.builder / "run" / f"{pid}.json"


def track(ws: Workspace, pid: int, command: str) -> Path:
    path = run_file(ws, pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = os.getpid()
    path.write_text(json.dumps({"pid": pid, "started_at": process_started_at(pid), "command": command,
                                "owner_pid": owner, "owner_started_at": process_started_at(owner)}))
    return path


def audit(ws: Workspace, result: CommandResult) -> None:
    record = result.model_dump()
    record["stdout_tail"] = record["stdout_tail"][-AUDIT_TAIL_CHARS:]
    record["stderr_tail"] = record["stderr_tail"][-AUDIT_TAIL_CHARS:]
    ws.logs.mkdir(parents=True, exist_ok=True)
    with (ws.logs / "commands.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def run(ws: Workspace, command: str | Sequence[str], *, timeout: float | None = None,
        env: Mapping[str, str] | None = None, label: str = "") -> CommandResult:
    """Run one command in ws.app and wait for it. Never raises for the command's own failures: a refused, missing,
    failing or timed-out command comes back as a CommandResult with ok=False and the reason."""
    started = datetime.now(timezone.utc).isoformat()
    text, argv, problems = check_command(ws, command)
    result = CommandResult(command=text, argv=argv, started_at=started, label=label)
    if problems:
        result.refused = problems
        audit(ws, result)
        return result
    full_env = build_env(ws, env)
    executable = resolve_executable(argv, full_env)
    if not executable:
        result.refused = [f"'{argv[0]}' is not installed on this machine (or not in the project)"]
        audit(ws, result)
        return result

    settings = get_settings()
    limit = timeout if timeout is not None else default_timeout(argv)
    cap = settings.command_output_cap_bytes
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(dir=full_env["TMPDIR"]) as out_dir:
        out_path, err_path = Path(out_dir) / "stdout", Path(out_dir) / "stderr"
        with out_path.open("wb") as out, err_path.open("wb") as err:
            proc = subprocess.Popen([executable, *argv[1:]], cwd=ws.app, env=full_env, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, start_new_session=True)   # own session = own group
            tracked = track(ws, proc.pid, text)
            try:
                proc.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                result.timed_out = True
                kill_group(proc.pid)
                proc.wait()
            else:
                kill_group(proc.pid, grace=0.5)          # children the command left running
            tracked.unlink(missing_ok=True)
        result.duration_seconds = round(time.monotonic() - t0, 3)
        result.exit_code = None if result.timed_out else proc.returncode
        result.stdout_tail, cut_out = read_tail(out_path, cap)
        result.stderr_tail, cut_err = read_tail(err_path, cap)
    result.output_truncated = cut_out or cut_err
    result.ok = result.exit_code == 0
    audit(ws, result)
    return result
