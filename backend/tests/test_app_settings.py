"""App settings (workspace/app_settings.py): .env.example parsing, saving outside app/, guides, and the dev server
(and ONLY the dev server) getting the values."""

import stat

import psutil

from ai_decision_arena.workspace import app_settings as A
from ai_decision_arena.workspace import sandbox
from ai_decision_arena.workspace.paths import create_workspace
from ai_decision_arena.workspace.processes import MemoryRuntimeStore, ProcessManager

EXAMPLE = """# Supabase project URL: Project Settings → API
VITE_SUPABASE_URL=
# anon / publishable key (public)
VITE_SUPABASE_ANON_KEY="your-anon-key"

PATH=/evil
STRIPE_SECRET_KEY=sk_test_xxx  # only for the server
"""


def ws_with_example(name: str):
    ws = create_workspace(name)
    (ws.app / ".env.example").write_text(EXAMPLE)
    return ws


def test_example_is_parsed_with_comments_and_reserved_names_dropped():
    ws = ws_with_example("settings-parse")
    variables = {v.name: v for v in A.read_example(ws)}
    assert list(variables) == ["VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY", "STRIPE_SECRET_KEY"]
    assert variables["VITE_SUPABASE_URL"].help == ["Supabase project URL: Project Settings → API"]
    assert variables["VITE_SUPABASE_ANON_KEY"].example == "your-anon-key"
    assert variables["STRIPE_SECRET_KEY"].example == "sk_test_xxx" and variables["STRIPE_SECRET_KEY"].help == []


def test_save_keeps_values_outside_the_app_and_describe_never_returns_them():
    ws = ws_with_example("settings-save")
    assert A.save(ws, {"NOT_IN_EXAMPLE": "x"}) == ["NOT_IN_EXAMPLE: not a variable of this app's .env.example"]
    assert A.save(ws, {"VITE_SUPABASE_URL": " https://abc.supabase.co ", "STRIPE_SECRET_KEY": "sk\nline2"}) == []
    path = ws.builder / A.ENV_FILE
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and not (ws.app / ".env").exists()
    assert A.env_values(ws) == {"VITE_SUPABASE_URL": "https://abc.supabase.co", "STRIPE_SECRET_KEY": "sk\nline2"}
    described = A.describe(ws)
    assert "abc.supabase.co" not in str(described)
    assert described["missing"] == ["VITE_SUPABASE_ANON_KEY"]
    assert {g["service"] for g in described["guides"]} == {"Supabase", "Stripe"}
    assert not any("migrations" in s for g in described["guides"] for s in g["steps"])   # no migrations folder
    assert A.save(ws, {"STRIPE_SECRET_KEY": ""}) == [] and "STRIPE_SECRET_KEY" not in A.env_values(ws)   # removed


def test_only_the_dev_server_gets_the_values():
    ws = ws_with_example("settings-env")
    A.save(ws, {"VITE_SUPABASE_URL": "https://abc.supabase.co"})
    assert "VITE_SUPABASE_URL" not in sandbox.build_env(ws)                     # install / test / build: no
    manager = ProcessManager(store=MemoryRuntimeStore())
    record = manager.start(ws, "python3 -m http.server {port} --bind 127.0.0.1")
    try:
        assert record.state == "ready", record.last_error
        assert psutil.Process(record.pid).environ().get("VITE_SUPABASE_URL") == "https://abc.supabase.co"
    finally:
        manager.stop(ws.session_id)


def test_supabase_rest_endpoint_is_cut_to_the_project_url():
    assert A.normalize("VITE_SUPABASE_URL", "https://abcd.supabase.co/rest/v1/")[0] == "https://abcd.supabase.co"
    assert A.normalize("VITE_SUPABASE_URL", "https://abcd.supabase.co") == ("https://abcd.supabase.co", None)
    assert A.normalize("OTHER_URL", "https://abcd.supabase.co/rest/v1/")[1] is None
    ws = ws_with_example("settings-normalize")
    (ws.builder / A.ENV_FILE).write_text("VITE_SUPABASE_URL=https://abcd.supabase.co/rest/v1/\n")   # saved earlier
    assert A.save(ws, {}) == [] and A.env_values(ws)["VITE_SUPABASE_URL"] == "https://abcd.supabase.co"
