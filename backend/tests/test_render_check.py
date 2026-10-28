"""Render check (workspace/render_check.py): verdicts from browser facts, the saved result per dev server run, and
one REAL headless-Chrome run against a page that crashes at import time (skipped when Chrome is not installed)."""

import threading
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ai_decision_arena.config import get_settings
from ai_decision_arena.workspace import render_check as R
from ai_decision_arena.workspace.paths import create_workspace


def test_verdict():
    assert R.verdict(None, []) == "blank"
    assert R.verdict({"text_chars": 0, "media": 0}, ["Uncaught Error: x"]) == "blank"
    assert R.verdict({"text_chars": 0, "media": 2}, []) == "ok"                  # a canvas / button counts
    assert R.verdict({"text_chars": 10, "media": 0}, ["console.error: y"]) == "warnings"


def test_browser_errors_are_collected_deduplicated_and_filtered():
    events = [
        {"method": "Runtime.exceptionThrown", "params": {"exceptionDetails": {"exception": {"description": "Error: boom"}}}},
        {"method": "Runtime.exceptionThrown", "params": {"exceptionDetails": {"exception": {"description": "Error: boom"}}}},
        {"method": "Runtime.consoleAPICalled", "params": {"type": "log", "args": [{"value": "hi"}]}},
        {"method": "Runtime.consoleAPICalled", "params": {"type": "error", "args": [{"value": "bad"}]}},
        {"method": "Log.entryAdded", "params": {"entry": {"level": "error", "text": "404", "url": "http://x/favicon.ico"}}},
    ]
    assert R.browser_errors(events) == ["Uncaught Error: boom", "console.error: bad"]


def test_disabled_check_is_skipped(monkeypatch):
    monkeypatch.setattr(get_settings(), "preview_render_check", False)
    result = R.check("http://127.0.0.1:1/")
    assert result["status"] == "skipped" and "disabled" in R.summary(result)


def test_saved_result_belongs_to_one_server_run():
    ws = create_workspace("render-save")
    started = datetime(2026, 10, 27, tzinfo=timezone.utc)
    R.save(ws, {"status": "blank", "errors": ["e"]}, started)
    assert R.load(ws, started)["status"] == "blank"
    assert R.load(ws, datetime(2026, 10, 28, tzinfo=timezone.utc)) is None        # restarted: not checked yet


PAGES = {
    "index.html": '<!doctype html><div id="root"></div><script type="module" src="/main.js"></script>',
    "main.js": 'import "./config.js";\ndocument.getElementById("root").textContent = "Hello budget";',
    "config.js": 'throw new Error("Missing Supabase configuration: set VITE_SUPABASE_URL");',
    "ok.html": '<!doctype html><div id="root"></div><script>document.getElementById("root").textContent = "Hi";</script>',
}


@pytest.mark.skipif(R.find_browser() is None, reason="Chrome / Chromium is not installed")
def test_real_chrome_sees_an_import_time_crash_as_blank(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "preview_render_check", True)
    for name, text in PAGES.items():
        (tmp_path / name).write_text(text)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        crashed = R.check(f"{base}/index.html", timeout=15)
        assert crashed["status"] == "blank", crashed
        assert "Missing Supabase configuration" in crashed["errors"][0]
        fine = R.check(f"{base}/ok.html", timeout=15)
        assert fine["status"] == "ok" and fine["text_chars"] == 2, fine
    finally:
        server.shutdown()
