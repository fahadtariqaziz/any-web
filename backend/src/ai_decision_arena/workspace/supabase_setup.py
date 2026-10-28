"""Database setup of a generated Supabase app: check that its tables exist, and run its migrations on request.

A generated app that uses Supabase ships its schema as app/supabase/migrations/*.sql, but nothing applies those files
to the user's Supabase project: sign-in works (Auth exists in every project), and every screen after it fails with
"Could not find the table 'public.x' in the schema cache". Two steps, both started by the user from the Preview tab:

- `check(ws)` (read-only, after the settings are saved or on "Check again"): asks the project's REST API (PostgREST)
  for each table the migrations create, with the app's own public URL + key from app_settings. 404 = missing;
  200 / 206 / 401 / 403 = the table exists (RLS or grants may still hide rows). Saved in .builder/db_check.json for
  the URL it was made with. Tables only: probing a function would execute it.
- `apply(ws, db_url)` (writes to the user's database, only when they press "Set up database"): connects with the
  database connection string they paste (used for this run only, never stored, never given to a model or the app),
  refuses a database of another Supabase project than the app's URL, and runs every migration file not yet recorded
  in supabase_migrations.schema_migrations (the Supabase CLI's own table, so `supabase db push` agrees later), one
  transaction per file, stopping at the first failure. Then `NOTIFY pgrst, 'reload schema'` (the REST API's schema
  cache) and a new check.
"""

import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlparse

from ai_decision_arena.workspace import app_settings
from ai_decision_arena.workspace.paths import Workspace

log = logging.getLogger(__name__)

CHECK_FILE = "db_check.json"
MIGRATIONS_DIR = ("supabase", "migrations")
MAX_TABLES = 30
HTTP_TIMEOUT = 8
CONNECT_TIMEOUT = 15
TABLE_RE = re.compile(r'create\s+table\s+(?:if\s+not\s+exists\s+)?(?:"?public"?\.)?"?([a-z_][a-z0-9_]*)"?\s*\(', re.I)
REF_RE = re.compile(r"^https://([a-z0-9-]+)\.supabase\.(?:co|in)$", re.I)
MIGRATION_TABLE = """
create schema if not exists supabase_migrations;
create table if not exists supabase_migrations.schema_migrations (version text primary key, statements text[], name text);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migration_files(ws: Workspace) -> list:
    folder = ws.app.joinpath(*MIGRATIONS_DIR)
    return sorted(p for p in folder.glob("*.sql") if p.is_file()) if folder.is_dir() else []


def tables(ws: Workspace) -> list[str]:
    """Tables in the public schema the migrations create, in order."""
    out: list[str] = []
    for path in migration_files(ws):
        for name in TABLE_RE.findall(_strip_comments(path.read_text(errors="replace"))):
            if name.lower() not in out:
                out.append(name.lower())
    return out[:MAX_TABLES]


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def connection(ws: Workspace) -> tuple[str | None, str | None]:
    """The app's Supabase project URL and public key, from the saved settings."""
    values = app_settings.env_values(ws)
    url = next((v for k, v in values.items() if "SUPABASE" in k.upper() and "URL" in k.upper()), None)
    key = next((v for k, v in values.items() if "SUPABASE" in k.upper() and re.search(r"ANON|PUBLISHABLE|KEY", k, re.I)
                and "SERVICE" not in k.upper() and "SECRET" not in k.upper()), None)
    return url, key


def project_ref(url: str | None) -> str | None:
    m = REF_RE.match((url or "").rstrip("/"))
    return m.group(1).lower() if m else None


def applies(ws: Workspace) -> bool:
    """This app has Supabase migrations and Supabase settings."""
    return bool(migration_files(ws)) and any("SUPABASE" in v.name.upper() for v in app_settings.read_example(ws))


def _probe(url: str, key: str, table: str) -> str:
    request = urllib.request.Request(f"{url.rstrip('/')}/rest/v1/{quote(table)}?select=*&limit=0",
                                     headers={"apikey": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT):
            return "found"
    except urllib.error.HTTPError as exc:
        return "missing" if exc.code == 404 else "found" if exc.code in (401, 403) else f"error {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"error {type(exc).__name__}"


def check(ws: Workspace, probe=_probe) -> dict:
    """Read-only: which of the migrations' tables exist in the user's project. Saved for the URL it used."""
    url, key = connection(ws)
    names = tables(ws)
    if not url or not key:
        result = {"status": "not_checked", "reason": "save the Supabase URL and key first"}
    elif not names:
        result = {"status": "not_checked", "reason": "the migrations create no tables"}
    else:
        found = {t: probe(url, key, t) for t in names}
        missing = [t for t, s in found.items() if s == "missing"]
        errors = [f"{t}: {s}" for t, s in found.items() if s.startswith("error")]
        status = "missing" if missing else "unknown" if errors else "ready"
        result = {"status": status, "tables": names, "missing": missing, "errors": errors[:5]}
    result |= {"url": url, "at": _now()}
    ws.builder.mkdir(parents=True, exist_ok=True)
    (ws.builder / CHECK_FILE).write_text(json.dumps(result, indent=1))
    return result


def last_check(ws: Workspace) -> dict | None:
    """The saved check, if it was made with the URL saved now."""
    try:
        data = json.loads((ws.builder / CHECK_FILE).read_text())
    except (OSError, ValueError):
        return None
    return data if data.get("url") == connection(ws)[0] else None


def db_url_problem(db_url: str, app_url: str | None) -> str | None:
    """None when `db_url` is a Postgres URL of the SAME Supabase project as the app's URL."""
    ref = project_ref(app_url)
    if not ref:
        return "save the app's Supabase URL (https://<ref>.supabase.co) first"
    if "[YOUR-PASSWORD]" in db_url.upper():
        return "the connection string needs your database password in place of [YOUR-PASSWORD]"
    try:
        parsed = urlparse(db_url.strip())
        parsed.port                                                     # raises on a bad port
    except ValueError:
        return ("the connection string could not be read: if your password contains characters like @ # / ? [ ], "
                "reset it to one without them (Project Settings → Database) or URL-encode them")
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
        return "paste the connection string that starts with postgresql://"
    if not parsed.password:
        return "the connection string needs your database password in place of [YOUR-PASSWORD]"
    host, user = parsed.hostname.lower(), unquote(parsed.username or "").lower()
    direct = host == f"db.{ref}.supabase.co"
    pooler = host.endswith(".pooler.supabase.com") and user == f"postgres.{ref}"
    if not (direct or pooler):
        return (f"this connection string is not for the app's Supabase project ({ref}): use the one from that "
                "project's Connect dialog")
    if parsed.port == 6543:
        return "use the Session pooler (port 5432) or the direct connection, not the Transaction pooler (6543)"
    return None


def _version(path) -> str:
    return path.stem.split("_", 1)[0]


def apply(ws: Workspace, db_url: str, connect=None) -> dict:
    """Run the migration files the database has not recorded yet. One transaction per file; stops at a failure."""
    url, _ = connection(ws)
    if problem := db_url_problem(db_url, url):
        return {"ok": False, "error": problem, "files": []}
    files = migration_files(ws)
    if connect is None:
        import psycopg

        def connect():
            return psycopg.connect(db_url.strip(), connect_timeout=CONNECT_TIMEOUT, sslmode="require")
    results: list[dict] = []
    try:
        with connect() as conn:
            conn.execute(MIGRATION_TABLE)
            conn.commit()
            done = {row[0] for row in conn.execute("select version from supabase_migrations.schema_migrations")}
            conn.commit()
            for path in files:
                version = _version(path)
                if version in done:
                    results.append({"file": path.name, "status": "already applied"})
                    continue
                try:
                    conn.execute(path.read_text())
                    conn.execute("insert into supabase_migrations.schema_migrations (version, name, statements) "
                                 "values (%s, %s, %s)", (version, path.stem, []))
                    conn.commit()
                    results.append({"file": path.name, "status": "applied"})
                except Exception as exc:                                          # noqa: BLE001 - reported
                    conn.rollback()
                    message = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else type(exc).__name__
                    hint = (" (the objects may exist already, e.g. the file was run by hand in the SQL Editor)"
                            if "already exists" in message else "")
                    results.append({"file": path.name, "status": "failed", "error": message + hint})
                    break
            conn.execute("notify pgrst, 'reload schema'")
            conn.commit()
    except Exception as exc:                                                      # noqa: BLE001 - connect / setup
        message = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else type(exc).__name__
        message = message.replace(db_url.strip(), "<connection string>")
        log.info("supabase setup for %s: %s", ws.session_id, message)
        return {"ok": False, "error": f"could not run the migrations: {message}", "files": results}
    ok = all(r["status"] != "failed" for r in results)
    return {"ok": ok, "error": None if ok else "a migration file failed; nothing after it was run", "files": results}
