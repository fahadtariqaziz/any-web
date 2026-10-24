#!/usr/bin/env bash
# M0 verify: backend unit tests (no network, no database) + frontend lint and type check.
# Run from anywhere:  bash backend/scripts/verify_m0.sh
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fail=0

echo "== backend: pytest =="
(cd "$ROOT/backend" && uv run pytest -q) || fail=1

echo "== frontend: eslint =="
(cd "$ROOT/frontend" && npm run --silent lint) || fail=1

echo "== frontend: tsc --noEmit =="
(cd "$ROOT/frontend" && npx tsc --noEmit) || fail=1

if [ "$fail" -eq 0 ]; then echo "M0 VERIFY: PASS"; else echo "M0 VERIFY: FAIL"; fi
exit $fail
