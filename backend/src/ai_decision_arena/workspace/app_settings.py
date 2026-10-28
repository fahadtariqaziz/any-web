"""Settings the generated app needs to run (its .env.example variables), given by the user in the Preview tab.

A generated app that talks to an external service (Supabase, Stripe, an AI API...) reads keys from environment
variables and ships a .env.example. The preview runs WITHOUT a .env, so such an app shows a setup screen or, before the
render check existed, a blank page. The user gives the values in a form, never in the chat:
- the values are stored in .builder/app.env (builder-owned, mode 600): NOT in app/, so the coding agent never reads
  them, they never reach a model, a commit or the code download;
- only the dev server gets them (processes.py merges `env_values` into its environment); install / test / build run
  without them, so nothing is baked into a build;
- the API returns names, whether a value is set and setup steps, never a value.

Setup steps come from the comment lines above each variable in .env.example (written by the coding agent) plus a few
built-in guides for well-known services, matched on the variable names.
"""

import os
import re
from dataclasses import dataclass, field

from ai_decision_arena.workspace.paths import Workspace

ENV_FILE = "app.env"
EXAMPLE_FILE = ".env.example"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
MAX_VALUE_CHARS = 4000
# The sandbox's own variables (sandbox.build_env) and the preview's port: a setting may never override them.
RESERVED = {"PATH", "HOME", "TMPDIR", "LANG", "TERM", "CI", "NO_COLOR", "FORCE_COLOR", "PORT", "BROWSER",
            "NODE_OPTIONS", "GIT_CEILING_DIRECTORIES", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT"}
RESERVED_PREFIXES = ("npm_config_", "UV_", "PIP_")


@dataclass(frozen=True)
class Guide:
    service: str
    match: re.Pattern
    url: str
    steps: tuple[str, ...]


GUIDES = (
    Guide("Supabase", re.compile(r"SUPABASE", re.I), "https://supabase.com/dashboard", (
        "Create a free project at supabase.com (sign in, then New project).",
        "Open Project Settings → API (or Data API) and copy the Project URL (https://<ref>.supabase.co, without "
        "/rest/v1) and the anon / publishable key.",
        "Create the app's tables: in the SQL Editor, run each file of the app's supabase/migrations folder in order "
        "(Download code gives you the files).",
        "Paste the values below and save: the preview restarts with them.")),
    Guide("Firebase", re.compile(r"FIREBASE", re.I), "https://console.firebase.google.com", (
        "Create a project in the Firebase console and add a Web app to it.",
        "Copy the values of its firebaseConfig (apiKey, authDomain, projectId...) into the matching fields below.")),
    Guide("Stripe", re.compile(r"STRIPE", re.I), "https://dashboard.stripe.com/test/apikeys", (
        "Sign in to the Stripe dashboard in TEST mode.",
        "Developers → API keys: copy the publishable key (pk_test_...) and, only if asked for, the secret key.")),
    Guide("OpenAI", re.compile(r"OPENAI", re.I), "https://platform.openai.com/api-keys", (
        "Create an API key at platform.openai.com → API keys and paste it below.",)),
    Guide("Anthropic", re.compile(r"ANTHROPIC|CLAUDE", re.I), "https://console.anthropic.com/settings/keys", (
        "Create an API key in the Claude Console → API keys and paste it below.",)),
    Guide("Clerk", re.compile(r"CLERK", re.I), "https://dashboard.clerk.com", (
        "Create an application in the Clerk dashboard; API keys shows the publishable and secret keys.",)),
    Guide("Mapbox", re.compile(r"MAPBOX", re.I), "https://account.mapbox.com/access-tokens", (
        "Copy your default public access token from account.mapbox.com.",)),
)


@dataclass
class Variable:
    name: str
    help: list[str] = field(default_factory=list)     # the comment lines above it in .env.example
    example: str = ""                                 # its value in .env.example (a placeholder, never a secret)


def allowed_name(name: str) -> bool:
    return bool(NAME_RE.match(name)) and name not in RESERVED and not name.startswith(RESERVED_PREFIXES)


def read_example(ws: Workspace) -> list[Variable]:
    """The variables of app/.env.example, in order, with the comment lines just above each."""
    try:
        lines = (ws.app / EXAMPLE_FILE).read_text(errors="replace").splitlines()
    except OSError:
        return []
    out: list[Variable] = []
    comments: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            comments = []
        elif line.startswith("#"):
            comments.append(line.lstrip("#").strip())
        elif "=" in line:
            name, value = line.removeprefix("export ").split("=", 1)
            name = name.strip()
            if allowed_name(name) and name not in {v.name for v in out}:
                out.append(Variable(name, [c for c in comments if c], _unquote(value.split(" #")[0].strip())))
            comments = []
    return out


def _unquote(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"" else value


def env_values(ws: Workspace) -> dict[str, str]:
    """The saved values (for the dev server only)."""
    try:
        lines = (ws.builder / ENV_FILE).read_text().splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            if allowed_name(name):
                out[name] = _decode(value)
    return out


def _encode(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def _decode(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), value)


SUPABASE_URL_RE = re.compile(r"^(https://[a-z0-9-]+\.supabase\.(?:co|in))(?:/.*)?$", re.I)


def normalize(name: str, value: str) -> tuple[str, str | None]:
    """Fix well-known paste mistakes. Returns (value, note about the fix or None).
    Supabase: the API page also shows the REST endpoint `https://<ref>.supabase.co/rest/v1/`; supabase-js appends its
    own paths, so sign-in then calls .../rest/v1/auth/v1/token ("Invalid path specified in request URL")."""
    if "SUPABASE" in name.upper() and "URL" in name.upper() and (m := SUPABASE_URL_RE.match(value)) and value != m.group(1):
        return m.group(1), f"{name}: kept only the project URL {m.group(1)} (supabase-js adds /rest/v1, /auth/v1 itself)"
    return value, None


def save(ws: Workspace, values: dict[str, str]) -> list[str]:
    """Merge `values` into the saved settings (an empty value removes one). Only .env.example names are accepted.
    Returns the problems (nothing is saved when there is one)."""
    known = {v.name for v in read_example(ws)}
    problems = [f"{name}: not a variable of this app's .env.example" for name in values if name not in known]
    problems += [f"{name}: value too long" for name, v in values.items() if len(v) > MAX_VALUE_CHARS]
    if problems:
        return problems
    current = env_values(ws) | {k: v.strip() for k, v in values.items()}
    current = {k: normalize(k, v)[0] for k, v in current.items() if v}      # also fixes values saved earlier
    ws.builder.mkdir(parents=True, exist_ok=True)
    path = ws.builder / ENV_FILE
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write("# Set by the user in the Preview tab; given to the dev server only (never to the coding agent).\n")
        out.writelines(f"{k}={_encode(v)}\n" for k, v in current.items())
    os.chmod(path, 0o600)
    return []


def describe(ws: Workspace) -> dict:
    """Names, set / missing and setup steps; never a value."""
    variables = read_example(ws)
    saved = env_values(ws)
    names = " ".join(v.name for v in variables)
    guides = [{"service": g.service, "url": g.url, "steps": list(g.steps)} for g in GUIDES if g.match.search(names)]
    has_migrations = (ws.app / "supabase" / "migrations").is_dir()
    for g in guides:
        if g["service"] == "Supabase" and not has_migrations:
            g["steps"] = [s for s in g["steps"] if "migrations" not in s]
    return {
        "variables": [{"name": v.name, "set": v.name in saved, "help": v.help, "example": v.example,
                       "public": v.name.startswith(("VITE_", "NEXT_PUBLIC_", "REACT_APP_", "PUBLIC_", "EXPO_PUBLIC_"))}
                      for v in variables],
        "missing": [v.name for v in variables if v.name not in saved and not " ".join(v.help).lower().startswith("optional")],
        "guides": guides,
    }
