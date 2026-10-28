"""Knowledge base (KB): stored documents the agents can search, each result with a citation.

Two kinds of documents in the `knowledge_docs` table:
- curated: short, hand-written docs in backend/knowledge/*.md (builder know-how: how the builder works, exact decimals,
  the Node test runner, Vite, accessibility, secrets; each with its source), loaded by scripts/load_knowledge.py
  (re-loading deletes curated rows whose file is gone);
- evidence: every kept source of every finished session (written at completion, db/repository.py), so a later
  chat can reuse what an earlier session found.

Retrieval is Postgres full-text search (stemming, ranking, a GIN index), no embeddings: "decimals" finds "decimal",
but not a synonym like "floating point" unless the doc says it (curated docs list their synonyms in `topic`). A vector
store would be justified only by measured misses (spec §10.10: no large KB without a use case); the use case here is
Ask answering questions about the project and the stack with cited sources.
Results carry an id like "kb_12" plus title and URL, so the agent can cite where a fact comes from.

Freshness and relevance (review 2026-10-29, "Knowledge Base ko versioned, searchable technical knowledge system
banao"): every doc has a `status` (verified | deprecated: kept for the record, never returned), a `verified_at`
date (curated: the file's `verified:` line; evidence: when its session completed) and a `stack` (comma keywords).
Results say when a fact was verified, and docs whose stack matches the project's are ranked first (Python re-rank
over Postgres' text rank: a Vite doc for a Vite project). Knowledge is what the system knows; memory (memory.py)
is what happened with this user: the two stay apart.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from ai_decision_arena.db.repository import replace_curated_docs, search_knowledge_docs

log = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"     # backend/knowledge
MAX_RESULTS = 5
MAX_EXCERPT_CHARS = 700
INCLUDE_CURATED = True      # (off in M10 while backend/knowledge/ still held the health app's docs)


def _date(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None
    except ValueError:
        return None


def _parse(path: Path) -> dict:
    """A curated doc: a front-matter block (title / url / topic / verified / stack / status, one "key: value" per line)
    between two '---' lines, then the text."""
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        header, _, body = raw[3:].partition("\n---")
        for line in header.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return {"kind": "curated", "key": path.name, "title": meta.get("title", path.stem), "url": meta.get("url") or None,
            "domain": None, "topic": meta.get("topic") or None, "content": body.strip(), "thread_id": None,
            "status": "deprecated" if meta.get("status", "").strip().lower() == "deprecated" else "verified",
            "verified_at": _date(meta.get("verified")), "stack": (meta.get("stack") or "").strip()[:200] or None}


def load_curated(directory: Path = KNOWLEDGE_DIR) -> tuple[int, int]:
    """(Re)load every backend/knowledge/*.md: (loaded, deleted). Same file name = updated row; curated rows whose file
    is gone are deleted."""
    docs = [_parse(p) for p in sorted(directory.glob("*.md"))]
    return len(docs), replace_curated_docs(docs)


STACK_BOOST = 1.3


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9.+#-]+", (text or "").lower()))


def rerank(rows: list[dict], stack: str, limit: int) -> list[dict]:
    """Docs whose `stack` keywords overlap the project's stack move up (x1.3 on the text rank); docs for another
    stack keep their rank (never hidden: a general answer beats none)."""
    wanted = _words(stack)
    def score(r: dict) -> float:
        own = _words(r.get("stack"))
        return float(r.get("rank") or 0.0) * (STACK_BOOST if wanted and own and (wanted & own) else 1.0)
    return sorted(rows, key=score, reverse=True)[:limit]


def search(query: str, thread_id: str | None = None, limit: int = MAX_RESULTS, stack: str = "") -> list[dict]:
    """Best matches first. Never raises: a database problem returns [] (the agent then says it found nothing)."""
    limit = max(1, min(limit, 10))
    try:
        rows = search_knowledge_docs(query, thread_id, min(limit * 2, 20), include_curated=INCLUDE_CURATED)
    except Exception:                                    # noqa: BLE001
        log.exception("knowledge search failed")
        return []
    return [
        {
            "id": f"kb_{r['id']}",
            "kind": r["kind"] if r["kind"] == "curated" else ("this chat's research" if r["thread_id"] == thread_id
                                                              else "an earlier session's research"),
            "title": r["title"],
            "url": r["url"],
            "domain": r["domain"],
            "verified": r["verified_at"].date().isoformat() if r.get("verified_at") else None,
            "stack": r.get("stack"),
            "excerpt": r["content"][:MAX_EXCERPT_CHARS],
        }
        for r in rerank(rows, stack, limit)
    ]
