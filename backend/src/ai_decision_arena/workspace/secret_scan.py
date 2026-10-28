"""Secret scan of a generated project (review of 2026-10-29, guardrail "dependency and secret checks").

Pure Python, no model, no network: the build check runs it after install / test / build and FAILS the check when a
key-shaped string sits in the project's source. The coding agent's prompt already forbids it (secrets come from
environment variables; .env.example carries the names); this is the independent check that the rule held, in the
same spirit as "a task is done by exit codes, not by what the agent says". A finding becomes a fix task for the
coding agent (nodes/delivery.py), within the usual fix-round cap.

What counts as a finding:
- known key shapes (AWS access key, Anthropic / OpenAI / Stripe / GitHub / Google / Slack tokens, a JWT, a private
  key block), anywhere in a text file of app/ outside node_modules / .git / build outputs / lock files;
- a generic `api_key = "..."` / `secret: "..."` / `password = "..."` assignment whose value is long and mixed
  (letters AND digits, 24+ chars) and is not an environment lookup, outside test files (fixtures use dummy values);
- a .env file in app/ that .gitignore does not ignore (its VALUES are not inspected: they may be the user's own).
Placeholders (EXAMPLE, xxxx, your-, placeholder, dummy, changeme) are skipped. Values are never stored in full:
findings carry a redacted form (first 4 and last 2 characters).
"""

import re
from pathlib import Path

from ai_decision_arena.workspace.paths import Workspace

SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".venv", "__pycache__", ".next", "coverage", ".cache", "out"}
SKIP_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock", "Cargo.lock"}
MAX_FILE_BYTES = 512_000
MAX_FINDINGS = 20
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|spec|fixtures|__mocks__)(/|$)|\.(test|spec)\.[a-z]+$|_test\.py$|test_[^/]*\.py$")
PLACEHOLDER_RE = re.compile(r"example|xxxx|your[-_ ]|placeholder|dummy|changeme|<[^>]+>|\.\.\.", re.IGNORECASE)
ENV_LOOKUP_RE = re.compile(r"process\.env|import\.meta\.env|os\.environ|os\.getenv|getenv\(|\$\{|Deno\.env|env\(")

# (kind, regex). Order matters only for overlapping shapes (Anthropic before OpenAI).
KEY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b")),
    ("Stripe key", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b")),
]
GENERIC_RE = re.compile(
    r"""(?i)\b(api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|password|passwd|private[_-]?key)\b\s*[:=]\s*["']([^"'\n]{24,})["']""")


def redact(value: str) -> str:
    return value[:4] + "…" + value[-2:] if len(value) > 8 else "…"


def _is_text(path: Path) -> bool:
    try:
        return path.stat().st_size <= MAX_FILE_BYTES and b"\0" not in path.read_bytes()[:4000]
    except OSError:
        return False


def scan_text(text: str, rel: str) -> list[dict]:
    """Findings in one file's text (rel = its path inside app/, for the report)."""
    findings: list[dict] = []
    is_test = bool(TEST_PATH_RE.search(rel))
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in KEY_PATTERNS:
            m = pattern.search(line)
            if m and not PLACEHOLDER_RE.search(m.group(0)):
                findings.append({"kind": kind, "file": rel, "line": number, "value": redact(m.group(0))})
                break
        else:
            m = GENERIC_RE.search(line)
            if m and not is_test:
                value = m.group(2).strip()
                mixed = any(c.isdigit() for c in value) and any(c.isalpha() for c in value)
                if mixed and not PLACEHOLDER_RE.search(value) and not ENV_LOOKUP_RE.search(line):
                    findings.append({"kind": f"hard-coded {m.group(1).lower()}", "file": rel, "line": number,
                                     "value": redact(value)})
    return findings


def scan(ws: Workspace) -> list[dict]:
    """Every finding in the project folder, at most MAX_FINDINGS, files in sorted order."""
    findings: list[dict] = []
    root = ws.app
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not path.is_file() or path.name in SKIP_FILES:
            continue
        if not _is_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings += scan_text(text, str(rel))
        if len(findings) >= MAX_FINDINGS:
            break
    env_file = root / ".env"
    if env_file.is_file():
        ignore = (root / ".gitignore").read_text(encoding="utf-8", errors="replace") if (root / ".gitignore").is_file() else ""
        if not any(line.strip() in (".env", "/.env", ".env*", "*.env") for line in ignore.splitlines()):
            findings.append({"kind": ".env file not git-ignored", "file": ".env", "line": 0, "value": "(values not inspected)"})
    return findings[:MAX_FINDINGS]


def describe(findings: list[dict]) -> str:
    return "\n".join(f"{f['file']}:{f['line']}: {f['kind']} ({f['value']})" for f in findings)
