---
name: python-project-hygiene
audience: agent
applies_to: python, fastapi, flask, django, pytest, uv, pip
description: Layout, dependencies, tests and server port of a Python project.
---
- Dependencies are declared in pyproject.toml (uv) or requirements.txt with versions; install them in a project
  virtual environment, never globally.
- Tests use pytest under tests/; the test command from the plan exits non-zero on failure.
- A web server binds to 127.0.0.1 and takes its port from the PORT environment variable or the --port argument the
  builder passes.
- Configuration and secrets come from environment variables; ship a .env.example with the names only.
- Keep business logic in importable functions that tests call directly; the web layer stays thin.
