---
title: How this AI app builder works (stages, approvals, changes, limits)
url:
topic: app builder process
verified: 2026-10-25

---
A project goes through these stages: questions to clarify the idea (up to 3 rounds), research in three domains
(existing apps and user feedback, papers and technical literature, technical feasibility), two or three solution
proposals that a critic reviews and a judge scores, an evidence check of the winning proposal, and a one-page problem
statement and solution brief. Nothing is planned before the user approves the brief, and nothing is built before the
user approves the implementation plan.

The coding agent builds the plan one task at a time. A task counts as done only when its own verify commands pass
when the builder runs them itself; the agent's report does not count. After the tasks, the build check runs the plan's
install, test and build commands; a failure can create a fix task. The app then runs in the live preview.

After the build the user can: send a small change ("Request some change in app": one coding task), plan a bigger
change ("Plan a bigger change": the brief is updated first, then a plan with only the new work, both need approval),
ask questions ("Ask about app": answers only, never changes anything), download the code, or finish. A finished
project can be reopened with a change.

Costs and limits: every model call of the builder and every coding-agent attempt is measured and shown in the Build
tab's Cost card (per stage, for the first build and for each change). Per project, the builder's own AI spend has a
limit (SESSION_LLM_BUDGET_USD, default $5: then no more automatic research or clarification loops) and the coding
agent has one (IMPLEMENTATION_BUDGET_USD, default $15: then no new task starts). Both count the whole project.
