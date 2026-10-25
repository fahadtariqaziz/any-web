---
title: Keeping secrets out of generated apps
url: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
topic: security, secrets, api keys, environment variables
---
Secrets (API keys, passwords, tokens) must not be written into source files, committed to a repository, or shipped
to the browser. The OWASP Secrets Management Cheat Sheet recommends keeping them in the environment or a secrets
manager, giving each one the least privilege it needs, and rotating them.

In a generated project: code reads secrets from environment variables, the project ships a .env.example with the
variable NAMES only, and .env is git-ignored. Anything the browser downloads is public: a key a frontend needs must go
through a small backend endpoint instead of being embedded in the bundle (in Vite, VITE_ variables are embedded).
The builder's own keys are never given to the coding agent or to the project's commands.
