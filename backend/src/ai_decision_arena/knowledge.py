"""Knowledge base (KB): stored documents the agents can search, each result with a citation.

Two kinds of documents in the `knowledge_docs` table:
- curated: short, hand-written docs in backend/knowledge/*.md (general safety know-how with their sources),
  loaded by scripts/load_knowledge.py;
- evidence: every kept source of every finished session (written at completion, db/repository.py), so a later
  chat can reuse what an earlier session found.

Retrieval is Postgres full-text search (stemming, ranking, a GIN index), no embeddings: "blood sugar" finds
"sugars", but not a synonym like "glucose". Good enough here, and no extra API key or service.
Results carry an id like "kb_12" plus title and URL, so the agent can cite where a fact comes from.
"""

import logging
from pathlib import Path

from ai_decision_arena.db.repository import search_knowledge_docs, upsert_knowledge_docs

log = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"     # backend/knowledge
MAX_RESULTS = 5
MAX_EXCERPT_CHARS = 700


def _parse(path: Path) -> dict:
    """A curated doc: a front-matter block (title / url / condition, one "key: value" per line) between two
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
            "domain": None, "condition": meta.get("condition") or None, "content": body.strip(), "thread_id": None}


def load_curated(directory: Path = KNOWLEDGE_DIR) -> int:
    """(Re)load every backend/knowledge/*.md. Safe to run again: same file name = updated row."""
    docs = [_parse(p) for p in sorted(directory.glob("*.md"))]
    upsert_knowledge_docs(docs)
    return len(docs)


def search(query: str, thread_id: str | None = None, limit: int = MAX_RESULTS) -> list[dict]:
    """Best matches first. Never raises: a database problem returns [] (the agent then says it found nothing)."""
    try:
        rows = search_knowledge_docs(query, thread_id, max(1, min(limit, 10)))
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
