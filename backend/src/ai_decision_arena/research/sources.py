"""Pure-Python helpers for URLs: normalize for de-duplication, guess the source type,
and the per-perspective domain lists used to steer Tavily.

The source type here is a cheap first guess from the domain. Being a "medical reference"
does NOT make a source reliable for a claim; that is the extractor's and Evidence Checker's job.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_decision_arena.schemas import SourceType

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}

# --- Domain lists per perspective (Python-owned, so a wrong LLM guess can't break a lane) ---
# research lane → "prefer" (boost, never empty the results)
RESEARCH_DOMAINS = [
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "cochranelibrary.com", "cochrane.org",
    "nature.com", "thelancet.com", "bmj.com", "nejm.org", "jamanetwork.com",
    "sciencedirect.com", "frontiersin.org", "plos.org", "mdpi.com", "springer.com", "wiley.com",
]
# doctor lane → "prefer"
DOCTOR_DOMAINS = [
    "mayoclinic.org", "clevelandclinic.org", "nhs.uk", "medlineplus.gov", "cdc.gov", "who.int",
    "nice.org.uk", "hopkinsmedicine.org", "health.harvard.edu", "msdmanuals.com", "aafp.org",
    "uptodate.com", "webmd.com", "healthline.com", "medicalnewstoday.com",
]
# patient lane → "restrict" (tested earlier: "prefer" returned no forum results at all)
# (patient.info and quora.com removed 2026-10-20: they mostly returned professional articles / opinion,
#  which the extractor re-labelled as "doctor" and which used up the patient lane's hit budget.)
PATIENT_DOMAINS = [
    "reddit.com", "healthunlocked.com", "inspire.com", "patientslikeme.com", "drugs.com", "mumsnet.com",
]

RESEARCH_HOST_HINTS = (
    "pubmed", "ncbi.nlm.nih.gov", "cochrane", "nature.com", "thelancet", "bmj.com", "nejm.org",
    "jamanetwork", "sciencedirect", "frontiersin", "plos.org", "mdpi.com", "springer", "wiley.com",
    "biomedcentral", "elsevier", "oup.com", "academic.", "journals.", "medrxiv", "biorxiv", "diabetesjournals",
)
GUIDELINE_HOST_HINTS = (
    "who.int", "cdc.gov", "nice.org.uk", "nih.gov", "diabetes.org", "heart.org", "cancer.org", "cancer.gov",
    "aafp.org", "acc.org", "idf.org", "ada.", "escardio", "guideline", "sign.ac.uk", "rcog", "nhs.uk",
)
REFERENCE_HOST_HINTS = (
    "mayoclinic", "clevelandclinic", "medlineplus", "msdmanuals", "merckmanuals", "hopkinsmedicine",
    "health.harvard.edu", "uptodate", "webmd", "healthline", "medicalnewstoday", "verywellhealth",
    "drugs.com", "medscape", "patient.info", "everydayhealth", "healthdirect", "betterhealth",
)
COMMUNITY_HOST_HINTS = (
    "reddit.com", "healthunlocked", "inspire.com", "patientslikeme", "mumsnet", "quora.com",
    "stackexchange", "community.", "forum.", "forums.", "discuss.",
)
COMMUNITY_PATHS = ("/forums/", "/forum/", "/community/", "/comments/", "/reviews", "/discussions/", "/questions/", "/r/")


def normalize_url(url: str) -> str:
    """Same page, same key: lowercase host, drop fragment, tracking params, trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), path, query, ""))


def classify_source(url: str) -> SourceType:
    parts = urlsplit(url.lower())
    host, path = parts.netloc.removeprefix("www."), parts.path
    # Patient voices first: a forum thread on a reference site is still a patient source.
    if any(h in host for h in COMMUNITY_HOST_HINTS) or any(p in path for p in COMMUNITY_PATHS):
        return "patient_community"
    if any(h in host for h in RESEARCH_HOST_HINTS):
        return "research_paper"
    if any(h in host for h in GUIDELINE_HOST_HINTS):
        return "clinical_guideline"
    if any(h in host for h in REFERENCE_HOST_HINTS):
        return "medical_reference"
    return "health_article"
