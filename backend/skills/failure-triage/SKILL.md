---
name: failure-triage
audience: agent
phases: fix, retry
description: How to go from a failing build, test or render check to a real fix, not a cover-up.
---
You received this task because a command or check failed (its output is in the task, as data). Work like a
debugger, not like a guesser.

1. Reproduce first: run the exact failing command with run_command before changing anything. Read the FIRST error
   in the output, not the last line; later errors are usually consequences.
2. Name the cause in one sentence before you edit. Common kinds: missing or wrong dependency / import path;
   configuration or environment (a variable the preview does not have, a port, a path); a type or syntax error; a
   test that expects the specified behaviour while the code does something else (fix the code); a test that
   encodes an old behaviour an approved change replaced (update that test and say so); a blank page from code that
   throws while loading (render a setup screen instead); a flaky timing or ordering dependency in a test (make it
   deterministic, never add retries or sleeps).
3. Fix the cause where it lives. Never delete, skip, loosen or `.only` a test to make the run green; never change
   the approved architecture, the test command or the build command to route around the failure; never catch an
   exception just to hide it.
4. Verify: re-run the failing command until it passes, then the task's verify commands. If a fix changes shared
   code, run the whole test suite once.
5. Report in at most 3 short lines: the cause, the change (files), what you ran. If the cause is outside the project
   (an external service, a missing secret the user must provide), say exactly that: the builder shows it to the
   user and an honest "needs the user's key" beats a fake fix.
