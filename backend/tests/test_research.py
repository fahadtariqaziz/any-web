"""Research plumbing: query planning fix-ups, Tavily de-duplication, hit selection and evidence assembly."""

import pytest
from pydantic import ValidationError

from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.research import search as search_module
from ai_decision_arena.research.extractor import extract_evidence, select_hits
from ai_decision_arena.research.planner import ensure_key_topics, plan_queries
from ai_decision_arena.schemas import DOMAINS, KEY_TOPIC
from tests.conftest import build_extraction


def q(domain: str, topic: str, text: str = "x") -> S.SearchQuery:
    return S.SearchQuery(query=text, domain=domain, topic=topic, preferred_domains=[])


def hit(url: str, domain: str = "apps", query: str = "q", score: float = 0.9,
        snippet: str = "Users complain that sync fails often.") -> S.SearchHit:
    return S.SearchHit(url=url, title="t", snippet=snippet, tavily_score=score, published_at=None,
                       source_type="review_site", query=query, domain=domain, topic="user_complaints")


def test_search_query_topic_must_belong_to_its_domain():
    with pytest.raises(ValidationError, match="not a 'apps' topic"):
        q("apps", "established_approaches")
    q("apps", "user_complaints")


def test_ensure_key_topics_fills_every_domain():
    queries = [q("apps", "existing_solutions", "a1"), q("apps", "must_have_features", "a2"),
               q("papers", "established_approaches", "p1"), q("tech", "architecture_patterns", "t1")]
    fixed = ensure_key_topics(queries, "calculator", per_domain=2)
    apps = [x.query for x in fixed if x.domain == "apps"]
    assert apps == ["a1", "calculator reviews complaints what users dislike"]       # budget full: last query replaced
    assert [x.query for x in fixed if x.domain == "papers"] == ["p1"]               # already had its key topic
    assert len([x for x in fixed if x.domain == "tech"]) == 2                       # room left: key query appended
    for d in DOMAINS:
        assert any(x.domain == d and x.topic == KEY_TOPIC[d] for x in fixed)


def test_plan_queries_enforces_the_budget_and_domain_order(fake_llm, base_state):
    def too_many(system, user):
        return S.ResearchPlan(search_term="t", queries=[q("tech", "feasibility_and_risks", f"t{i}") for i in range(5)]
                              + [q("apps", "user_complaints", "a"), q("papers", "established_approaches", "p")])
    fake_llm.overrides[S.ResearchPlan] = too_many
    plan = plan_queries(base_state)
    assert sum(1 for x in plan.queries if x.domain == "tech") == get_settings().queries_per_domain
    domains = [x.domain for x in plan.queries]
    assert domains == sorted(domains, key=DOMAINS.index)


def test_run_searches_dedupes_across_queries_and_keeps_failures(monkeypatch):
    def fake_search_one(query):
        if query.query == "boom":
            raise RuntimeError("tavily down")
        return [hit("https://www.example.com/a/?utm_source=x", domain=query.domain, score=0.5),
                hit("https://example.com/b", domain=query.domain, score=0.9)]
    monkeypatch.setattr(search_module, "search_one", fake_search_one)
    hits, failures = search_module.run_searches([q("apps", "user_complaints", "one"),
                                                 q("papers", "established_approaches", "two"),
                                                 q("tech", "feasibility_and_risks", "boom")])
    assert [h.url for h in hits] == ["https://example.com/b", "https://www.example.com/a/?utm_source=x"]   # deduped, best first
    assert all(h.domain == "apps" for h in hits)                                                             # first query wins the duplicate
    assert len(failures) == 1 and failures[0].domain == "tech" and failures[0].retryable is True


def test_select_hits_round_robins_across_queries():
    hits = [hit("https://e.com/q1a", query="q1", score=0.9), hit("https://e.com/q1b", query="q1", score=0.8),
            hit("https://e.com/q2a", query="q2", score=0.7)]
    assert [h.url for h in select_hits(hits, 2)] == ["https://e.com/q1a", "https://e.com/q2a"]


def test_extract_evidence_assigns_ids_copies_urls_and_demotes_fake_quotes(fake_llm, base_state):
    hits = {"apps": [hit("https://e.com/1", snippet="Sync fails often, users say."), hit("https://e.com/2")]}

    def claims_quotes(system, user):
        out = build_extraction(system, user)
        out.evidence[0].is_direct_quote, out.evidence[0].relevant_excerpt = True, "Sync fails often"   # real quote
        out.evidence[1].is_direct_quote, out.evidence[1].relevant_excerpt = True, "never said this"    # fake quote
        out.evidence.append(out.evidence[0].model_copy(update={"source_index": 99}))                    # invalid index
        return out
    fake_llm.overrides[S.ExtractionResult] = claims_quotes

    out = extract_evidence(base_state, hits, start_number=5)
    ev = out["evidence"]
    assert sorted(e["evidence_id"] for e in ev) == ["ev_005", "ev_006"]
    by_url = {e["source_url"]: e for e in ev}
    assert set(by_url) == {"https://e.com/1", "https://e.com/2"}                   # URLs come from the hits
    assert by_url["https://e.com/1"]["is_direct_quote"] is True
    assert by_url["https://e.com/2"]["is_direct_quote"] is False
    assert "Checker" in by_url["https://e.com/2"]["reliability_notes"]
    assert by_url["https://e.com/1"]["feedback_context"]["feedback_type"] == "complaint"
    assert out["summaries"]["apps"].endswith("Opportunity: Nobody does offline well.")
    assert out["rejected"] == []
