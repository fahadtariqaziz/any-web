"""Code export (M10 "Download code"): the files of a session's generated project, for the user to keep locally.

Only `app/` (never `.builder/`: logs, agent config). Left out: dependency and build folders the user recreates
(`npm install`, `npm run build`), git data, `.env*` files except `.env.example` (no secrets ever leave), symlinks
(they could point outside the project) and anything that is not a regular file. Size caps keep a runaway project from
being sent as one huge response. Paths are POSIX, relative, and checked again by the browser before it writes them.
"""

import base64
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ai_decision_arena.workspace.paths import Workspace

SKIP_DIRS = {"node_modules", ".git", "dist", ".next", "coverage", "__pycache__", ".venv", "venv", ".pytest_cache",
             ".cache", ".turbo", ".parcel-cache"}
MAX_FILE_BYTES = 5_000_000
MAX_TOTAL_BYTES = 50_000_000


@dataclass
class CodeExport:
    folder_name: str                                     # suggested folder name, e.g. "simple-calculator-web-app"
    files: list[tuple[str, Path]] = field(default_factory=list)       # (relative posix path, absolute path)
    skipped: list[str] = field(default_factory=list)     # what was left out and why (for the UI)
    total_bytes: int = 0


def folder_name(project_name: str | None, session_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (project_name or "").lower()).strip("-")[:60]
    return slug or f"project-{session_id[:8]}"


def _skip_file(name: str) -> bool:
    return name.startswith(".env") and name != ".env.example"


def collect(ws: Workspace, project_name: str | None) -> CodeExport:
    export = CodeExport(folder_name=folder_name(project_name, ws.session_id))
    for dirpath, dirnames, filenames in os.walk(ws.app, followlinks=False):
        base = Path(dirpath)
        for d in sorted(dirnames):
            if d in SKIP_DIRS or (base / d).is_symlink():
                export.skipped.append(f"{(base / d).relative_to(ws.app).as_posix()}/ (" +
                                      ("symlink" if (base / d).is_symlink() else "recreated by install / build") + ")")
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not (base / d).is_symlink())
        for name in sorted(filenames):
            path = base / name
            rel = path.relative_to(ws.app).as_posix()
            if path.is_symlink() or not path.is_file():
                export.skipped.append(f"{rel} (symlink or special file)")
            elif _skip_file(name):
                export.skipped.append(f"{rel} (may hold secrets)")
            elif (size := path.stat().st_size) > MAX_FILE_BYTES:
                export.skipped.append(f"{rel} (larger than {MAX_FILE_BYTES // 1_000_000} MB)")
            elif export.total_bytes + size > MAX_TOTAL_BYTES:
                export.skipped.append(f"{rel} (export limit of {MAX_TOTAL_BYTES // 1_000_000} MB reached)")
            else:
                export.files.append((rel, path))
                export.total_bytes += size
    return export


def as_json(export: CodeExport) -> dict:
    return {"folder_name": export.folder_name, "total_bytes": export.total_bytes, "skipped": export.skipped,
            "files": [{"path": rel, "content_b64": base64.b64encode(path.read_bytes()).decode("ascii")}
                      for rel, path in export.files]}


def as_zip(export: CodeExport) -> bytes:
    """A zip with one top-level folder (folder_name/...), like a repository download."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, path in export.files:
            zf.write(path, f"{export.folder_name}/{rel}")
    return buffer.getvalue()
