"""URL normalisation and the domain-based source classifier (research/sources.py)."""

import pytest

from ai_decision_arena.research.sources import classify_source, normalize_url


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


@pytest.mark.parametrize("url, expected", [
    ("https://pubmed.ncbi.nlm.nih.gov/123", "research_paper"),
    ("https://www.nice.org.uk/guidance/ng28", "clinical_guideline"),
    ("https://www.mayoclinic.org/diseases", "medical_reference"),
    ("https://www.reddit.com/r/diabetes/comments/abc", "patient_community"),
    ("https://www.healthline.com/community/thread-1", "patient_community"),   # forum path wins over host
    ("https://someblog.example/post", "health_article"),
])
def test_classify_source(url, expected):
    assert classify_source(url) == expected
