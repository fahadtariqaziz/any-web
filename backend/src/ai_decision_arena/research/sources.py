"""Pure-Python helpers for URLs: normalize for de-duplication, guess the source type, and the per-domain site
lists used to steer Tavily.

The source type here is a cheap first guess from the host and path. A research-paper host does NOT make a claim
reliable: that is the extractor's and the Evidence Checker's job.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_decision_arena.schemas import SourceType

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}

# --- Site lists per research domain (Python-owned, so a wrong LLM guess can't break a domain) ---
# Tavily gets them as include_domains in "prefer" mode: boosted, never exclusive, so a domain never comes back empty.
APPS_SITES = [
    "g2.com", "capterra.com", "getapp.com", "producthunt.com", "trustpilot.com", "alternativeto.net",
    "apps.apple.com", "play.google.com", "reddit.com", "news.ycombinator.com",
]
PAPERS_SITES = [
    "arxiv.org", "dl.acm.org", "ieeexplore.ieee.org", "link.springer.com", "sciencedirect.com",
    "semanticscholar.org", "aclanthology.org", "nature.com", "researchgate.net", "openreview.net",
]
TECH_SITES = [
    "github.com", "stackoverflow.com", "developer.mozilla.org", "npmjs.com", "pypi.org", "react.dev", "nextjs.org",
    "fastapi.tiangolo.com", "supabase.com", "vercel.com", "web.dev", "docs.python.org",
]
SITES_BY_DOMAIN: dict[str, list[str]] = {"apps": APPS_SITES, "papers": PAPERS_SITES, "tech": TECH_SITES}

# --- Source-type hints (host substrings and path fragments), checked in the order used by classify_source ---
COMMUNITY_HOSTS = ("reddit.com", "news.ycombinator.com", "stackoverflow.com", "stackexchange.com", "quora.com",
                   "community.", "forum.", "forums.", "discuss.")
COMMUNITY_PATHS = ("/forums/", "/forum/", "/community/", "/comments/", "/discussions/", "/questions/", "/r/")
APP_STORE_HOSTS = ("apps.apple.com", "play.google.com", "chromewebstore.google.com", "apps.microsoft.com",
                   "addons.mozilla.org", "marketplace.visualstudio.com")
REVIEW_HOSTS = ("g2.com", "capterra.com", "getapp.com", "trustpilot.com", "producthunt.com", "alternativeto.net",
                "softwareadvice.com", "trustradius.com", "slant.co")
PAPER_HOSTS = ("arxiv.org", "dl.acm.org", "ieee.org", "springer.com", "sciencedirect.com", "semanticscholar.org",
               "aclanthology.org", "nature.com", "researchgate.net", "openreview.net", "biorxiv.org", "jstor.org",
               "wiley.com", "mdpi.com", "plos.org", "frontiersin.org", "ssrn.com")
REPO_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "npmjs.com", "pypi.org", "huggingface.co", "crates.io",
              "pkg.go.dev", "rubygems.org", "packagist.org")
TECH_DOC_HOSTS = ("developer.mozilla.org", "learn.microsoft.com", "developer.apple.com", "developer.android.com",
                  "cloud.google.com", "docs.aws.amazon.com", "developers.google.com", "web.dev", "w3.org", "react.dev",
                  "nextjs.org", "vuejs.org", "angular.dev", "svelte.dev", "fastapi.tiangolo.com", "docs.python.org",
                  "nodejs.org", "supabase.com", "vercel.com", "stripe.com", "firebase.google.com", "readthedocs.io",
                  "tailwindcss.com", "postgresql.org", "expo.dev", "flutter.dev", "docs.")
TECH_DOC_PATHS = ("/docs/", "/documentation/", "/reference/", "/guide/", "/guides/")
PRODUCT_DOC_HOSTS = ("help.", "support.", "faq.", "zendesk.com", "intercom.help", "helpscoutdocs.com")
PRODUCT_DOC_PATHS = ("/help/", "/support/", "/faq", "/pricing", "/features", "/changelog", "/release-notes")
BLOG_HOSTS = ("medium.com", "dev.to", "substack.com", "hashnode.dev", "techcrunch.com", "theverge.com", "wired.com",
              "hackernoon.com", "smashingmagazine.com", "css-tricks.com", "infoq.com")
BLOG_PATHS = ("/blog/", "/blogs/", "/news/", "/articles/", "/posts/")


def normalize_url(url: str) -> str:
    """Same page, same key: lowercase host, drop fragment, tracking params, trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), path, query, ""))


def classify_source(url: str) -> SourceType:
    parts = urlsplit(url.lower())
    host, path = parts.netloc.removeprefix("www."), parts.path

    def host_in(hints: tuple[str, ...]) -> bool:
        return any(h in host for h in hints)

    def path_in(hints: tuple[str, ...]) -> bool:
        return any(p in path for p in hints)

    # People talking first: a discussion thread on GitHub or on a product site is still a discussion.
    if host_in(COMMUNITY_HOSTS) or path_in(COMMUNITY_PATHS):
        return "community_discussion"
    if host_in(APP_STORE_HOSTS):
        return "app_store"
    if host_in(REVIEW_HOSTS):
        return "review_site"
    if host_in(PAPER_HOSTS):
        return "research_paper"
    if host_in(REPO_HOSTS):
        return "source_repository"
    if host_in(TECH_DOC_HOSTS) or path_in(TECH_DOC_PATHS):
        return "technical_docs"
    if host_in(PRODUCT_DOC_HOSTS) or path_in(PRODUCT_DOC_PATHS):
        return "product_docs"
    if host_in(BLOG_HOSTS) or path_in(BLOG_PATHS):
        return "article_or_blog"
    return "other"
