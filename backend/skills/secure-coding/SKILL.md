---
name: secure-coding
audience: agent
applies_to: *
description: The security habits every generated app keeps, whatever the stack.
---
The builder's own checks (sandbox, secret scan, tests) catch some mistakes; these habits prevent the rest. Apply
the ones that fit the task; do not add security features the task did not ask for.

- Secrets: never in code, tests, fixtures or comments. Read them from environment variables, list each name in
  .env.example with a comment (what it is, where to get it), keep .env git-ignored. A key the browser can see is
  public: anything that must stay secret goes behind a backend endpoint.
- Validate at the boundary: every input from a user, a URL, a form, a file or an external API is checked (type,
  length, range, allowed values) before it is used, in the server-side code when there is a server. Reject with a
  clear message; never "fix up" silently.
- Authorization is checked server-side on every request that reads or changes another user's data (the user id
  comes from the session / token, never from the request body or the URL alone). Row-level rules (e.g. database
  policies) count only when they are actually enabled and tested.
- No string-built queries or commands: parameters for SQL, no shell concatenation, no `eval` / `new Function` /
  `exec` on data. Escape or sanitise user content before rendering it as HTML (frameworks do it by default: keep it
  that way; no `dangerouslySetInnerHTML` / `innerHTML` / `v-html` with user content).
- File paths from input are resolved and checked to stay inside the intended folder; uploads get a size and type
  limit.
- Dependencies: only well-known, maintained packages the plan names; no package added "just in case"; pinned
  versions in the lock file.
- Errors and logs never contain secrets, tokens, passwords or full personal records; the user sees a message, not a
  stack trace.
- Sessions and tokens: HttpOnly + Secure cookies or the framework's session helper; CSRF protection on state-changing
  form posts when cookies carry the session; sensible CORS (named origins, not `*` with credentials).
- Write a test for each rule you implement (a rejected bad input, a forbidden cross-user read): a security check
  without a test disappears in the next refactor.
