"""Live check of supabase_setup.apply against a REAL Postgres (the local one from backend/.env), free.

    uv run python scripts/verify_db_setup.py [session_id]

Creates a throwaway database `verify_db_setup_<ts>` (and the roles anon / authenticated only if the cluster lacks
them), loads a stand-in for Supabase's auth schema (the generated app's tests/db/auth_shim.sql when it has one), then:
  1. applies the session's supabase/migrations through apply() (psycopg, one transaction per file, the CLI's
     supabase_migrations.schema_migrations table, NOTIFY pgrst);
  2. runs apply() again: every file "already applied";
  3. a broken extra migration fails, is rolled back, and nothing after it runs;
  4. db_url_problem refuses another project's connection string, the transaction pooler and [YOUR-PASSWORD].
Drops the database (and the roles it created) at the end. The project folder is only read (the broken file goes into
a temporary copy).
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_decision_arena.config import get_settings  # noqa: E402
from ai_decision_arena.workspace import supabase_setup as S  # noqa: E402
from ai_decision_arena.workspace.paths import Workspace, workspace_for  # noqa: E402

SESSION = sys.argv[1] if len(sys.argv) > 1 else "dd258d42-e089-4bce-af23-85387d2b597d"
FALLBACK_SHIM = """create schema if not exists auth;
create table auth.users (id uuid primary key default gen_random_uuid(), email text,
  raw_user_meta_data jsonb not null default '{}'::jsonb);
create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
"""


def ok(cond: bool, label: str) -> None:
    print(("   PASS " if cond else "   FAIL ") + label)
    if not cond:
        raise SystemExit(1)


def main() -> None:
    base = get_settings().database_url
    db = f"verify_db_setup_{int(time.time())}"
    admin = psycopg.connect(base, autocommit=True)
    created_roles = [r for r in ("anon", "authenticated")
                     if not admin.execute("select 1 from pg_roles where rolname = %s", (r,)).fetchone()]
    for role in created_roles:
        admin.execute(f"create role {role} nologin")
    admin.execute(f'create database "{db}"')
    url = urlunparse(urlparse(base)._replace(path=f"/{db}"))
    src = workspace_for(SESSION)
    tmp = Path(tempfile.mkdtemp(prefix="verify-db-setup-"))
    try:
        shutil.copytree(src.app / "supabase", tmp / "app" / "supabase")
        ws = Workspace(session_id="verify-db-setup", root=tmp, app=tmp / "app", builder=tmp / ".builder")
        shim_path = src.app / "tests" / "db" / "auth_shim.sql"
        shim = shim_path.read_text() if shim_path.exists() else FALLBACK_SHIM
        shim = "\n".join(l for l in shim.splitlines() if not l.strip().lower().startswith("create role"))
        with psycopg.connect(url) as conn:
            conn.execute(shim)
            conn.commit()
        S.db_url_problem = lambda db_url, app_url: None          # local DB: no Supabase project ref to match
        connect = lambda: psycopg.connect(url)                    # noqa: E731

        print(f"== 1. apply {len(S.migration_files(ws))} migration files of {SESSION} to {db} ==")
        first = S.apply(ws, url, connect=connect)
        for f in first["files"]:
            print(f"   {f['file']}: {f['status']} {f.get('error') or ''}")
        ok(first["ok"] and all(f["status"] == "applied" for f in first["files"]), "every file applied")
        with psycopg.connect(url) as conn:
            have = {r[0] for r in conn.execute("select table_name from information_schema.tables where table_schema='public'")}
            versions = [r[0] for r in conn.execute("select version from supabase_migrations.schema_migrations order by 1")]
        ok(set(S.tables(ws)) <= have, f"all {len(S.tables(ws))} tables exist: {', '.join(S.tables(ws))}")
        ok(versions == [S._version(p) for p in S.migration_files(ws)], f"recorded versions {versions}")

        print("== 2. apply again ==")
        again = S.apply(ws, url, connect=connect)
        ok(again["ok"] and all(f["status"] == "already applied" for f in again["files"]), "every file already applied")

        print("== 3. a broken migration ==")
        folder = ws.app / "supabase" / "migrations"
        (folder / "9998_broken.sql").write_text("create table broken_one (id int);\nselect * from no_such_table;")
        (folder / "9999_after.sql").write_text("create table after_broken (id int);")
        bad = S.apply(ws, url, connect=connect)
        print("   " + "; ".join(f"{f['file']}: {f['status']}" for f in bad["files"][-2:]) + f" | {bad['files'][-1].get('error')}")
        with psycopg.connect(url) as conn:
            leftovers = {r[0] for r in conn.execute("select table_name from information_schema.tables "
                                                    "where table_name in ('broken_one', 'after_broken')")}
        ok(not bad["ok"] and bad["files"][-1]["file"] == "9998_broken.sql" and not leftovers,
           "the broken file failed, was rolled back, the next one never ran")

        print("== 4. connection string checks ==")
        import importlib
        importlib.reload(S)
        app = "https://abcdefghijklmnopqrst.supabase.co"
        ok(S.db_url_problem("postgresql://postgres.abcdefghijklmnopqrst:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres", app) is None, "session pooler of the same project accepted")
        ok(S.db_url_problem("postgresql://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres", app) is None, "direct connection accepted")
        ok("not for the app's" in S.db_url_problem("postgresql://postgres.zzzzzzzzzzzzzzzzzzzz:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres", app), "another project refused")
        ok("6543" in S.db_url_problem("postgresql://postgres.abcdefghijklmnopqrst:pw@aws-0-eu-central-1.pooler.supabase.com:6543/postgres", app), "transaction pooler refused")
        ok("password" in S.db_url_problem("postgresql://postgres:[YOUR-PASSWORD]@db.abcdefghijklmnopqrst.supabase.co:5432/postgres", app), "placeholder password refused")
        print("\nDB SETUP VERIFY: PASS")
    finally:
        admin.execute(f'drop database if exists "{db}" with (force)')
        for role in created_roles:
            admin.execute(f"drop role if exists {role}")
        admin.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
