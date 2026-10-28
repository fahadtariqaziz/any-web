---
title: Node.js built-in test runner (node --test)
url: https://nodejs.org/api/test.html
topic: testing, node, javascript, unit tests
verified: 2026-10-25
stack: node, javascript, typescript

---
Node.js ships a test runner in the node:test module: `import test from 'node:test'` (or `describe` / `it`) with
assertions from `node:assert`. `node --test` finds and runs test files (by default names such as *.test.js,
*.test.mjs and files in test/ folders) and exits with a non-zero code when a test fails, so it works as a verify or
build-check command without extra dependencies.

A test can be skipped (`test('x', { skip: true }, ...)` or `t.skip()`) or marked todo (`{ todo: true }`). Skipped and
todo tests do NOT fail the run: the summary only counts them. A project should not keep skipped tests once the feature
they need exists, because the exit code then hides untested behaviour.

Useful options: `--test-name-pattern` to run matching tests, `--watch` while developing, and `--experimental-test-coverage`
for a coverage report (check the docs of the installed Node version for which flags are stable).
