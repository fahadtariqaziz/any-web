"""Supabase database setup (workspace/supabase_setup.py): tables from migrations, the read-only check (fake REST),
connection string rules. The real migration run against Postgres: scripts/verify_db_setup.py."""

from ai_decision_arena.workspace import app_settings as A
from ai_decision_arena.workspace import supabase_setup as S
from ai_decision_arena.workspace.paths import create_workspace

REF = "abcdefghijklmnopqrst"


def supabase_ws(name: str):
    ws = create_workspace(name)
    (ws.app / ".env.example").write_text("VITE_SUPABASE_URL=\nVITE_SUPABASE_ANON_KEY=\n")
    folder = ws.app / "supabase" / "migrations"
    folder.mkdir(parents=True)
    (folder / "0001_schema.sql").write_text(
        "-- create table commented_out (id int);\ncreate table profiles (id uuid);\n"
        "CREATE TABLE IF NOT EXISTS public.budgets (id int);\ncreate view v as select 1;\n")
    (folder / "0002_more.sql").write_text('create table "transactions" (id int);\n')
    return ws


def test_tables_come_from_the_migrations_in_order():
    ws = supabase_ws("sb-tables")
    assert S.applies(ws) and [p.name for p in S.migration_files(ws)] == ["0001_schema.sql", "0002_more.sql"]
    assert S.tables(ws) == ["profiles", "budgets", "transactions"]


def test_check_reports_missing_tables_for_the_saved_url():
    ws = supabase_ws("sb-check")
    assert S.check(ws)["status"] == "not_checked"                                  # no settings yet
    A.save(ws, {"VITE_SUPABASE_URL": f"https://{REF}.supabase.co", "VITE_SUPABASE_ANON_KEY": "sb_publishable_x"})
    seen = []

    def probe(url, key, table):
        seen.append((url, key, table))
        return "found" if table == "profiles" else "missing"
    result = S.check(ws, probe=probe)
    assert result["status"] == "missing" and result["missing"] == ["budgets", "transactions"]
    assert seen[0] == (f"https://{REF}.supabase.co", "sb_publishable_x", "profiles")
    assert S.last_check(ws)["status"] == "missing"
    A.save(ws, {"VITE_SUPABASE_URL": "https://zzzzzzzzzzzzzzzzzzzz.supabase.co"})
    assert S.last_check(ws) is None                                                # another project: not checked
    assert S.check(ws, probe=lambda *a: "found")["status"] == "ready"
    assert S.check(ws, probe=lambda *a: "error 500")["status"] == "unknown"


def test_connection_string_must_be_the_apps_project():
    app = f"https://{REF}.supabase.co"
    pooler = f"postgresql://postgres.{REF}:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    assert S.db_url_problem(pooler, app) is None
    assert S.db_url_problem(f"postgresql://postgres:pw@db.{REF}.supabase.co:5432/postgres", app) is None
    assert "first" in S.db_url_problem(pooler, None)
    assert "not for the app's" in S.db_url_problem(pooler.replace(REF, "z" * 20), app)
    assert "6543" in S.db_url_problem(pooler.replace(":5432", ":6543"), app)
    assert "[YOUR-PASSWORD]" in S.db_url_problem(pooler.replace(":pw@", ":[YOUR-PASSWORD]@"), app)
    assert "postgresql://" in S.db_url_problem("https://example.com", app)


def test_apply_refuses_before_connecting():
    ws = supabase_ws("sb-apply")
    A.save(ws, {"VITE_SUPABASE_URL": f"https://{REF}.supabase.co"})
    called = []
    result = S.apply(ws, "postgresql://postgres.other:pw@x.pooler.supabase.com:5432/postgres",
                     connect=lambda: called.append(1))
    assert not result["ok"] and not called and "not for the app's" in result["error"]
