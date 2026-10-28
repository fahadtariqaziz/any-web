"""Review 2026-10-29: the build check's secret scan (workspace/secret_scan.py), pure Python."""

from ai_decision_arena.workspace import secret_scan
from ai_decision_arena.workspace.paths import create_workspace


def _ws(tmp_path):
    return create_workspace("scan-1", root=tmp_path)


def test_known_key_shapes_are_found_and_redacted(tmp_path):
    ws = _ws(tmp_path)
    (ws.app / "src").mkdir(parents=True)
    (ws.app / "src" / "client.ts").write_text(
        'const key = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";\n'
        "const aws = 'AKIAIOSFODNN7EXAMPLE';\n"                          # placeholder: AWS docs example
        "const real = 'AKIAZZZZZZZZZZZZZZZZ';\n")
    (ws.app / "key.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n")
    found = secret_scan.scan(ws)
    kinds = [(f["kind"], f["file"], f["line"]) for f in found]
    assert ("Anthropic API key", "src/client.ts", 1) in kinds
    assert ("AWS access key", "src/client.ts", 3) in kinds and ("AWS access key", "src/client.ts", 2) not in kinds
    assert ("private key block", "key.pem", 1) in kinds
    assert all("…" in f["value"] and len(f["value"]) <= 7 for f in found)       # never the full value
    assert "ABCDEFGHIJ" not in secret_scan.describe(found)


def test_generic_assignments_env_lookups_tests_and_placeholders(tmp_path):
    ws = _ws(tmp_path)
    (ws.app / "src").mkdir(parents=True)
    (ws.app / "src" / "config.ts").write_text(
        'export const apiKey = process.env.API_KEY ?? "";\n'                                # env lookup: fine
        'const password = "correct horse battery staple";\n'                                # no digits: fine
        'const api_key = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4";\n'                                 # mixed, long: finding
        'const token = "your-api-key-goes-here-1234567890";\n')                            # placeholder: fine
    (ws.app / "src" / "config.test.ts").write_text('const api_key = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4";\n')  # test file: fine
    (ws.app / "node_modules").mkdir()
    (ws.app / "node_modules" / "x.js").write_text("const k = 'AKIAZZZZZZZZZZZZZZZZ';\n")  # skipped dir
    found = secret_scan.scan(ws)
    assert [(f["kind"], f["file"], f["line"]) for f in found] == [("hard-coded api_key", "src/config.ts", 3)]


def test_env_file_must_be_git_ignored(tmp_path):
    ws = _ws(tmp_path)
    (ws.app / ".env").write_text("VITE_SUPABASE_URL=https://x.supabase.co\n")
    assert [f["kind"] for f in secret_scan.scan(ws)] == [".env file not git-ignored"]
    (ws.app / ".gitignore").write_text("node_modules\n.env\n")
    assert secret_scan.scan(ws) == []


def test_binary_and_lock_files_are_skipped(tmp_path):
    ws = _ws(tmp_path)
    (ws.app / "package-lock.json").write_text('{"x": "AKIAZZZZZZZZZZZZZZZZ"}')
    (ws.app / "logo.png").write_bytes(b"\x89PNG\x00\x00AKIAZZZZZZZZZZZZZZZZ")
    assert secret_scan.scan(ws) == []
