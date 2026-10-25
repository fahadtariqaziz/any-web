---
name: testing-discipline
audience: agent
applies_to: *
description: How tests are written and kept in a generated project.
---
- Every task that adds behaviour adds tests for it: the normal case, edge cases named in the task's acceptance
  criteria, and error cases. Tests run offline and deterministically (no network, no real time or randomness without
  control).
- Use the project's test command from the plan; make it exit non-zero on any failure.
- No skipped, pending or todo tests at the end of a task. A test that needs a later feature belongs to that later
  task, not a skip.
- Do not weaken, loosen or delete an existing test to make the suite pass; fix the code, or, if the approved behaviour
  really changed (a change request), update that test and say so in the report.
- Run the verify commands yourself before finishing; read the output instead of assuming success.
