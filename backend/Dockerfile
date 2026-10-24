# Runtime sandbox for the backend (agent anatomy: "Runtime", handoff.md 11.8).
# Build + run from the repo root:  docker compose up --build
# The container holds no secrets (they come from backend/.env at run time) and no source of truth (Postgres
# stays on the host). docker-compose.yml adds the locks: non-root, read-only filesystem, no Linux capabilities.

# --- stage 1: install the dependencies with uv (exact versions from uv.lock) ---
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev && python -m compileall -q src

# --- stage 2: the small image that runs (no uv, no build tools) ---
FROM python:3.13-slim-bookworm
RUN useradd --create-home --uid 10001 arena
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/src ./src
# knowledge/ and skills/ are found next to src/ (knowledge.py, skills.py), migrations for "alembic upgrade head"
COPY knowledge ./knowledge
COPY skills ./skills
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER arena
EXPOSE 8000
CMD ["uvicorn", "ai_decision_arena.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
