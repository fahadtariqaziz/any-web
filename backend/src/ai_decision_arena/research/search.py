"""Tavily web search wrapper: bounded, de-duplicated, traced, never crashes the graph.

- Each query belongs to a research domain (apps / papers / tech); the domain decides which sites to prefer and
  the search depth.
- Transient errors (timeout, network, 5xx) → retry with exponential backoff.
- Permanent errors (bad key, quota used up, bad request) → no retry; recorded as a failure.
- A failed query becomes a SearchFailure (an evidence gap), never invented results.
- Queries run in parallel threads (network-bound work); results are merged in query order.
"""

import time
from functools import lru_cache

import tavily.errors as tavily_errors
from langsmith import traceable
from langsmith.utils import ContextThreadPoolExecutor
from tavily import TavilyClient

from ai_decision_arena import tool_log
from ai_decision_arena.config import get_settings
from ai_decision_arena.progress import report
from ai_decision_arena.research.sources import SITES_BY_DOMAIN, classify_source, normalize_url
from ai_decision_arena.schemas import SearchFailure, SearchHit, SearchQuery

PERMANENT_ERRORS = (
    tavily_errors.InvalidAPIKeyError,
    tavily_errors.MissingAPIKeyError,
    tavily_errors.UsageLimitExceededError,
    tavily_errors.BadRequestError,
    tavily_errors.ForbiddenError,
)
MAX_SNIPPET_CHARS = 2000
MAX_PARALLEL_SEARCHES = 9
MAX_PLANNER_DOMAINS = 3


@lru_cache
def _client() -> TavilyClient:
    """Created once; kept out of function arguments so it never appears in traces."""
    return TavilyClient(api_key=get_settings().tavily_api_key.get_secret_value())


def _domain_kwargs(q: SearchQuery) -> dict:
    """Site steering per research domain ("prefer": boosted, never exclusive). Planner-suggested sites are added.
    The apps domain uses the deeper search: review and forum snippets are too short with "basic"."""
    settings = get_settings()
    base = SITES_BY_DOMAIN[q.domain]
    extra = [d for d in q.preferred_domains if d and d not in base][:MAX_PLANNER_DOMAINS]
    return {
        "include_domains": base + extra,
        "include_domains_mode": "prefer",
        "search_depth": settings.tavily_apps_search_depth if q.domain == "apps" else settings.tavily_search_depth,
    }


@traceable(run_type="tool", name="tavily_search")   # shows each search in LangSmith
def search_one(q: SearchQuery) -> list[SearchHit]:
    """One Tavily call with bounded retries. Raises on final failure."""
    settings = get_settings()
    kwargs = {
        "max_results": settings.max_results_per_query,
        "timeout": settings.tavily_timeout_seconds,
    } | _domain_kwargs(q)

    started = time.monotonic()
    target = f"{q.domain}: {q.query}"
    for attempt in range(settings.search_max_retries + 1):
        try:
            response = _client().search(q.query, **kwargs)
            break
        except PERMANENT_ERRORS as exc:
            tool_log.record(tool_log.current_thread_id(), "search", "tavily", target=target, ok=False,
                            reason=f"{type(exc).__name__}: {exc}", duration_seconds=round(time.monotonic() - started, 3))
            raise
        except Exception as exc:
            if attempt == settings.search_max_retries:
                tool_log.record(tool_log.current_thread_id(), "search", "tavily", target=target, ok=False,
                                reason=f"{type(exc).__name__}: {exc} (after {attempt + 1} attempts)",
                                duration_seconds=round(time.monotonic() - started, 3))
                raise
            time.sleep(2 ** attempt)   # 1s, 2s, 4s ...
    tool_log.record(tool_log.current_thread_id(), "search", "tavily", target=target,
                    duration_seconds=round(time.monotonic() - started, 3), label=f"{len(response.get('results') or [])} hits")

    return [
        SearchHit(
            url=r["url"],
            title=(r.get("title") or r["url"])[:300],
            snippet=(r.get("content") or "")[:MAX_SNIPPET_CHARS],
            tavily_score=float(r.get("score") or 0.0),
            published_at=r.get("published_date"),   # Tavily only sometimes has this; never guessed
            source_type=classify_source(r["url"]),
            query=q.query,
            domain=q.domain,
            topic=q.topic,
        )
        for r in response.get("results", [])
        if r.get("url")
    ]


def _safe_search(q: SearchQuery) -> list[SearchHit] | SearchFailure:
    """Never raises: a failure is returned as a value, so one bad query can't stop the others."""
    try:
        hits = search_one(q)
        report("research", f"[{q.domain}] {len(hits)} results: {q.query[:70]}")
        return hits
    except Exception as exc:
        report("research", f"[{q.domain}] search failed ({type(exc).__name__}): {q.query[:70]}")
        return SearchFailure(
            query=q.query,
            domain=q.domain,
            error_type=type(exc).__name__,
            message=str(exc)[:300],                 # Tavily errors don't include the key
            retryable=not isinstance(exc, PERMANENT_ERRORS),
        )


def run_searches(queries: list[SearchQuery]) -> tuple[list[SearchHit], list[SearchFailure]]:
    """Run the queries in parallel. Returns (unique hits, failures). A URL found by two domains is kept once,
    under the domain whose query came first (apps → papers → tech)."""
    hits: list[SearchHit] = []
    failures: list[SearchFailure] = []
    seen: set[str] = set()
    if not queries:
        return hits, failures

    # ContextThreadPoolExecutor = ThreadPoolExecutor that also copies the LangSmith trace
    # context into each thread, so the tavily_search runs stay nested under "research".
    with ContextThreadPoolExecutor(max_workers=min(MAX_PARALLEL_SEARCHES, len(queries))) as pool:
        outcomes = list(pool.map(_safe_search, queries))   # map keeps the original query order

    for outcome in outcomes:
        if isinstance(outcome, SearchFailure):
            failures.append(outcome)
            continue
        for hit in outcome:
            key = normalize_url(hit.url)
            if key not in seen:                     # de-duplicate across queries and domains
                seen.add(key)
                hits.append(hit)

    hits.sort(key=lambda h: h.tavily_score, reverse=True)
    return hits, failures
