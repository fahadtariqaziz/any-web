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
"""

import logging
from pathlib import Path

from ai_decision_arena.db.repository import replace_curated_docs, search_knowledge_docs

log = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"     # backend/knowledge
MAX_RESULTS = 5
MAX_EXCERPT_CHARS = 700
INCLUDE_CURATED = True      # (off in M10 while backend/knowledge/ still held the health app's docs)


def _parse(path: Path) -> dict:
    """A curated doc: a front-matter block (title / url / topic, one "key: value" per line) between two
    '---' lines, then the text."""
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        header, _, body = raw[3:].partition("\n---")
        for line in header.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return {"kind": "curated", "key": path.name, "title": meta.get("title", path.stem), "url": meta.get("url") or None,
            "domain": None, "topic": meta.get("topic") or None, "content": body.strip(), "thread_id": None}


def load_curated(directory: Path = KNOWLEDGE_DIR) -> tuple[int, int]:
    """(Re)load every backend/knowledge/*.md: (loaded, deleted). Same file name = updated row; curated rows whose file
    is gone are deleted."""
    docs = [_parse(p) for p in sorted(directory.glob("*.md"))]
    return len(docs), replace_curated_docs(docs)


def search(query: str, thread_id: str | None = None, limit: int = MAX_RESULTS) -> list[dict]:
    """Best matches first. Never raises: a database problem returns [] (the agent then says it found nothing)."""
    try:
        rows = search_knowledge_docs(query, thread_id, max(1, min(limit, 10)), include_curated=INCLUDE_CURATED)
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
            "excerpt": r["content"][:MAX_EXCERPT_CHARS],
        }
        for r in rows
    ]
