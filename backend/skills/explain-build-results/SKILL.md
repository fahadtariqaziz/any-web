---
name: explain-build-results
audience: ask
description: Explain a failed or skipped task, a failed build check or a preview that does not start, from the measured facts in <build>.
---
# Explain build results

Use when the user asks why something failed, is blocked, skipped, or why the preview does not show the app.

1. Read only <build>: task status and notes (verify commands and their summaries), the last build check (phase,
   command, ok, summary) and the preview state / last error. These were measured by running commands.
2. Say in plain words what failed and where: which task or step, which command, the exit code or error summary.
   Separate the fact ("`npm test` exited with 1 in build check 2") from your reading of it ("probably a test that
   still expects the old layout").
3. Explain the consequences: a failed task blocks the tasks that depend on it; a failed build check may have created
   fix tasks (F1, F2); the preview may run the last version that built.
4. Suggest the next step: usually a change request that quotes the failing command and the expected behaviour (use the
   write-a-change-request skill's format). If <build> lacks the detail, say the Build tab has the full output.
