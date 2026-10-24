"""URL normalisation, the per-domain site lists and the host/path source classifier (research/sources.py)."""

import pytest

from ai_decision_arena.research.sources import SITES_BY_DOMAIN, classify_source, normalize_url
from ai_decision_arena.schemas import DOMAINS


@pytest.mark.parametrize("a, b", [
    ("https://www.example.com/page/", "https://example.com/page"),
    ("https://example.com/page#section", "https://example.com/page"),
    ("https://example.com/page?utm_source=x&id=3", "https://example.com/page?id=3"),
    ("HTTPS://Example.COM/Page", "https://example.com/Page"),
])
def test_normalize_url_makes_same_page_same_key(a, b):
    assert normalize_url(a) == normalize_url(b)


def test_normalize_url_keeps_meaningful_query():
    assert normalize_url("https://example.com/a?page=2") != normalize_url("https://example.com/a?page=3")


def test_every_domain_has_a_site_list_of_bare_hosts():
    assert set(SITES_BY_DOMAIN) == set(DOMAINS)
    for sites in SITES_BY_DOMAIN.values():
        assert sites and all("/" not in s and s == s.lower() for s in sites)


@pytest.mark.parametrize("url, expected", [
    ("https://arxiv.org/abs/2401.01234", "research_paper"),
    ("https://dl.acm.org/doi/10.1145/123", "research_paper"),
    ("https://github.com/foo/bar", "source_repository"),
    ("https://pypi.org/project/httpx/", "source_repository"),
    ("https://github.com/foo/bar/discussions/12", "community_discussion"),     # a thread is a discussion, wherever it is
    ("https://www.reddit.com/r/webdev/comments/abc", "community_discussion"),
    ("https://stackoverflow.com/questions/123", "community_discussion"),
    ("https://apps.apple.com/us/app/calc/id123", "app_store"),
    ("https://play.google.com/store/apps/details?id=x", "app_store"),
    ("https://www.g2.com/products/foo/reviews", "review_site"),
    ("https://www.producthunt.com/products/foo", "review_site"),
    ("https://developer.mozilla.org/en-US/docs/Web", "technical_docs"),
    ("https://nextjs.org/docs/app", "technical_docs"),
    ("https://example.com/docs/getting-started", "technical_docs"),
    ("https://help.notion.so/articles/1", "product_docs"),
    ("https://example.com/pricing", "product_docs"),
    ("https://medium.com/@x/post", "article_or_blog"),
    ("https://example.com/blog/post", "article_or_blog"),
    ("https://example.com/some/page", "other"),
])
def test_classify_source(url, expected):
    assert classify_source(url) == expected
