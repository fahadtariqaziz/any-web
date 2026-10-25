"""Session folders and the path guard (handoff.md section 6, spec §9 "separate project folders").

Layout, one folder per session (session id = the graph's thread_id):

    <generated_projects_dir>/<thread_id>/
    ├── app/        the generated project: the ONLY directory the coding agent and commands may touch
    └── .builder/   builder-owned: brief.md, plan.json, tasks.json, logs/, runtime.json, home/ (the commands' $HOME)

Every file path that comes from an LLM, a plan or a user goes through `safe_path`, which resolves symlinks and
refuses anything that ends up outside `app/`. Python owns this boundary, never the model.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from ai_decision_arena.config import get_settings

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")   # thread ids are uuids or "verify-m7-<ts>"
SHARED_DIR = ".shared"                                            # package caches (config.share_package_cache)


class PathError(ValueError):
    """A path or session id that would leave the session's sandbox."""


@dataclass(frozen=True)
class Workspace:
    session_id: str
    root: Path          # generated_projects/<id>
    app: Path           # root/app
    builder: Path       # root/.builder

    @property
    def home(self) -> Path:
        return self.builder / "home"

    @property
    def logs(self) -> Path:
        return self.builder / "logs"


def projects_root() -> Path:
    return Path(get_settings().generated_projects_dir).expanduser().resolve()


def workspace_for(session_id: str, root: Path | None = None) -> Workspace:
    """The workspace of a session (nothing is created). Refuses ids that could name another folder."""
    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        raise PathError(f"invalid session id {session_id!r} (letters, digits, '-' and '_', at most 64)")
    base = (root or projects_root()).resolve()
    session_root = base / session_id
    return Workspace(session_id=session_id, root=session_root, app=session_root / "app",
                     builder=session_root / ".builder")


def create_workspace(session_id: str, root: Path | None = None) -> Workspace:
    """Create (or reuse) the session's folders. Idempotent: resuming a session keeps its files."""
    ws = workspace_for(session_id, root)
    for folder in (ws.app, ws.home, ws.logs):
        folder.mkdir(parents=True, exist_ok=True)
    if ws.app.is_symlink() or ws.app.resolve() != ws.app:
        raise PathError(f"{ws.app} must be a real directory, not a symlink")
    return ws


def safe_path(ws: Workspace, relative: str) -> Path:
    """Absolute path of `relative` inside ws.app, or PathError. Symlinks are resolved first, so a link inside app/
    that points elsewhere (another session, the builder, /etc) is refused like a '..' path. The file need not exist."""
    if not isinstance(relative, str) or not relative.strip():
        raise PathError("empty path")
    if "\x00" in relative or "\\" in relative:
        raise PathError(f"{relative!r}: NUL bytes and backslashes are not allowed")
    if relative.startswith(("/", "~")) or ".." in Path(relative).parts:
        raise PathError(f"{relative!r}: must be relative to the project (no '/', '~' or '..')")
    app = ws.app.resolve()
    target = (app / relative).resolve()            # strict=False: follows every existing symlink on the way
    if target != app and app not in target.parents:
        raise PathError(f"{relative!r} resolves outside the project folder")
    return target


def is_inside(ws: Workspace, path: Path) -> bool:
    """True when `path` (absolute, symlinks resolved) is the session's app folder or inside it."""
    app = ws.app.resolve()
    resolved = path.resolve()
    return resolved == app or app in resolved.parents
