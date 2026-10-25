---
name: write-a-change-request
audience: ask
description: Turn what the user wants changed in their running app into a ready-to-send, testable change request.
---
# Write a change request

Use when the user describes something they want different in the app ("make the buttons bigger", "add history").

1. Restate the change in one sentence in the user's terms. Ask ONE question only if something essential is unclear
   (which screen, what should happen on an edge case); otherwise make a sensible assumption and say it.
2. Write the request so the coding agent can test it:
   - what to add or change, where in the app;
   - concrete examples with exact inputs and expected results (e.g. "430 - 20% = 344");
   - edge cases that matter (empty input, errors, very long values);
   - what must stay as it is (existing features, the tech stack, earlier changes from <user_requests>);
   - "add tests for these cases".
3. Put the ready-to-send text in a quote block and say which mode to send it with: "Request some change in app" for a
   change inside the approved scope (one coding task), "Plan a bigger change" for a new capability (see the
   small-or-bigger-change skill). Never say the change was made.
