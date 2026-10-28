"""Render check of a running preview (spec §9 "show useful errors"): does the app actually draw something?

The dev server's health check (processes.py) only proves that HTTP answers. A single-page app can answer with its
index.html and still crash in the browser before it renders (e.g. a module that throws at import time because an
environment variable is missing): the user sees a blank preview while every build step passed. This module opens the
URL in headless Chrome over the DevTools protocol and reports facts from the browser, never from a model:

- `status`: "ok" (visible text or media, no errors) · "warnings" (renders, but the browser logged errors) ·
  "blank" (nothing visible after the page settled) · "skipped" (disabled, no Chrome, or the check itself failed);
- `errors`: uncaught exceptions, console.error calls and failed resource loads (first lines, capped);
- `text_chars` / `snippet`: how much visible text the page shows.

The result is saved next to the runtime record (.builder/render.json) with the dev server's started_at, so
GET /preview shows it only for the server run it belongs to.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone

from ai_decision_arena.config import get_settings
from ai_decision_arena.workspace.paths import Workspace
from ai_decision_arena.workspace.sandbox import kill_group

log = logging.getLogger(__name__)

RENDER_FILE = "render.json"
MAX_ERRORS = 8
MAX_ERROR_CHARS = 600
SETTLE_AFTER_CONTENT_SECONDS = 1.0
CRASH_GRACE_SECONDS = 4.0             # an uncaught error + still blank this long after navigating = done
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
)
DEVTOOLS_RE = re.compile(r"DevTools listening on (ws://\S+)")
IGNORED_ERRORS = ("favicon.ico",)

# Visible content: text, or media / controls that draw without text. Scripts and styles do not count.
PROBE_JS = """(() => {
  const b = document.body;
  if (!b) return {text_chars: 0, media: 0, snippet: ""};
  const text = (b.innerText || "").trim();
  const media = [...b.querySelectorAll("img,svg,canvas,video,input,button,select,textarea,iframe")]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }).length;
  return {text_chars: text.length, media, snippet: text.slice(0, 200)};
})()"""


def find_browser() -> str | None:
    configured = get_settings().preview_render_browser
    for candidate in ((configured,) if configured else CHROME_CANDIDATES):
        path = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if path and os.path.exists(path):
            return path
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(text: str) -> str:
    return str(text).strip()[:MAX_ERROR_CHARS]


def verdict(probe: dict | None, errors: list[str]) -> str:
    """ok / warnings / blank from what the page showed and what the browser logged."""
    shown = bool(probe) and (probe.get("text_chars", 0) > 0 or probe.get("media", 0) > 0)
    if not shown:
        return "blank"
    return "warnings" if errors else "ok"


def skipped(reason: str) -> dict:
    return {"status": "skipped", "reason": reason, "errors": [], "text_chars": 0, "snippet": "", "at": _now()}


def summary(result: dict) -> str:
    """One line for the activity log."""
    status = result.get("status")
    if status == "skipped":
        return f"render check skipped ({result.get('reason', '')})"
    if status == "blank":
        first = (result.get("errors") or ["no browser error was logged"])[0].splitlines()[0]
        return f"render check: the page is BLANK in the browser: {first[:200]}"
    if status == "warnings" and result.get("errors"):
        return (f"render check: the page renders, but the browser logged {len(result['errors'])} error(s): "
                f"{result['errors'][0].splitlines()[0][:200]}")
    return f"render check: the page renders ({result.get('text_chars', 0)} characters of text)"


class _Cdp:
    """Minimal DevTools protocol client over one browser websocket, flat sessions."""

    def __init__(self, ws_url: str) -> None:
        from websockets.sync.client import connect
        self.ws = connect(ws_url, max_size=None, open_timeout=5)
        self.next_id = 0
        self.events: list[dict] = []

    def send(self, method: str, params: dict | None = None, session: str | None = None, timeout: float = 10) -> dict:
        self.next_id += 1
        message = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        self.ws.send(json.dumps(message))
        deadline = time.monotonic() + timeout
        while True:
            data = json.loads(self.ws.recv(timeout=max(deadline - time.monotonic(), 0.01)))
            if data.get("id") == self.next_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error'].get('message')}")
                return data.get("result", {})
            if "method" in data:
                self.events.append(data)

    def pump(self, seconds: float) -> None:
        """Collect events for `seconds`."""
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            try:
                self.events.append(json.loads(self.ws.recv(timeout=left)))
            except TimeoutError:
                return

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:                                                     # noqa: BLE001
            pass


def browser_errors(events: list[dict]) -> list[str]:
    """Uncaught exceptions, console.error and failed loads, in order, de-duplicated and capped."""
    out: list[str] = []
    for e in events:
        method, p = e.get("method"), e.get("params", {})
        text = None
        if method == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails", {})
            text = (d.get("exception") or {}).get("description") or d.get("text")
            text = f"Uncaught {text}" if text and not text.startswith("Uncaught") else text
        elif method == "Runtime.consoleAPICalled" and p.get("type") == "error":
            text = "console.error: " + " ".join(str(a.get("description") or a.get("value") or "") for a in p.get("args", []))
        elif method == "Log.entryAdded" and p.get("entry", {}).get("level") == "error":
            entry = p["entry"]
            text = entry.get("text", "") + (f" ({entry['url']})" if entry.get("url") else "")
        if text and not any(i in text for i in IGNORED_ERRORS):
            text = _clip(text)
            if text not in out:
                out.append(text)
    return out[:MAX_ERRORS]


def check(url: str, timeout: float | None = None) -> dict:
    """Open `url` in headless Chrome and report what it showed. Never raises: problems of the check itself = skipped."""
    settings = get_settings()
    if not settings.preview_render_check:
        return skipped("disabled (PREVIEW_RENDER_CHECK=false)")
    browser = find_browser()
    if not browser:
        return skipped("Chrome / Chromium is not installed")
    timeout = timeout or settings.preview_render_timeout_seconds
    profile = tempfile.mkdtemp(prefix="builder-render-")
    proc = subprocess.Popen([browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                             "--disable-extensions", "--remote-debugging-port=0", f"--user-data-dir={profile}",
                             "--window-size=1280,800", "about:blank"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            start_new_session=True, text=True)
    cdp = None
    started = time.monotonic()
    try:
        ws_url = None
        while ws_url is None and time.monotonic() - started < 15:
            line = proc.stderr.readline()
            if not line and proc.poll() is not None:
                return skipped(f"Chrome exited with code {proc.returncode}")
            if m := DEVTOOLS_RE.search(line):
                ws_url = m.group(1)
        if ws_url is None:
            return skipped("Chrome did not open its DevTools port")
        cdp = _Cdp(ws_url)
        target = cdp.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        for domain in ("Page", "Runtime", "Log"):
            cdp.send(f"{domain}.enable", session=session)
        cdp.send("Page.navigate", {"url": url}, session=session)
        navigated = time.monotonic()
        deadline = navigated + timeout
        probe, content_since = None, None
        while time.monotonic() < deadline:
            cdp.pump(0.5)
            probe = cdp.send("Runtime.evaluate", {"expression": PROBE_JS, "returnByValue": True},
                             session=session).get("result", {}).get("value")
            if verdict(probe, []) != "blank":
                content_since = content_since or time.monotonic()
                if time.monotonic() - content_since >= SETTLE_AFTER_CONTENT_SECONDS:
                    break
            elif time.monotonic() - navigated >= CRASH_GRACE_SECONDS and any(
                    e.get("method") == "Runtime.exceptionThrown" and e.get("sessionId") == session for e in cdp.events):
                break                                     # crashed and still blank: no need to wait the full timeout
        errors = browser_errors([e for e in cdp.events if e.get("sessionId") == session])
        probe = probe or {}
        return {"status": verdict(probe, errors), "errors": errors, "text_chars": probe.get("text_chars", 0),
                "snippet": probe.get("snippet", ""), "url": url, "seconds": round(time.monotonic() - started, 1),
                "at": _now()}
    except Exception as exc:                                                  # noqa: BLE001 - a check, not the app
        log.warning("render check of %s failed: %s", url, exc)
        return skipped(f"the check itself failed: {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        if cdp:
            cdp.close()
        kill_group(proc.pid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        shutil.rmtree(profile, ignore_errors=True)


def save(ws: Workspace, result: dict, started_at: datetime | None) -> None:
    ws.builder.mkdir(parents=True, exist_ok=True)
    payload = result | {"server_started_at": started_at.isoformat() if started_at else None}
    (ws.builder / RENDER_FILE).write_text(json.dumps(payload, indent=1))


def load(ws: Workspace, started_at: datetime | None) -> dict | None:
    """The saved result for THIS dev server run (None after a restart until it was checked again)."""
    try:
        data = json.loads((ws.builder / RENDER_FILE).read_text())
    except (OSError, ValueError):
        return None
    return data if data.get("server_started_at") == (started_at.isoformat() if started_at else None) else None


def check_preview(ws: Workspace, record) -> dict | None:
    """Render-check a READY preview record and save the result; None when the server is not ready."""
    if record is None or record.state != "ready" or not record.url:
        return None
    result = check(record.url)
    save(ws, result, record.started_at)
    return result
