"""Query planning: Claude turns the clarified idea into targeted searches for all three research domains.

Quick sessions skip the Claude call and use fixed query templates with the project name: one general query and the
key-topic query per domain are enough for a short summary.
"""

import json

from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.prompting import BUILDER_RULES, user_case_block
from ai_decision_arena.schemas import DOMAINS, KEY_TOPIC, ResearchPlan, SearchQuery
from ai_decision_arena.state import ArenaState

SYSTEM_PROMPT = """You are the research planner of an AI application builder. Three domains of web research run for the
user's idea. Together they must answer: which existing products solve this problem and what their users complain
about or praise; what is known about the underlying problem and which approaches are established (papers,
technical literature); and what is technically feasible (libraries, frameworks, APIs, reference implementations,
risks).

Domains and their topics:
- apps: existing products, app-store and review-site feedback, community discussions (G2, Capterra, Product Hunt,
  app stores, Reddit, Hacker News). Topics: existing_solutions, user_complaints, must_have_features,
  pricing_and_adoption.
- papers: research papers, surveys, technical reports, authoritative documentation (arXiv, ACM, IEEE, Springer,
  ScienceDirect). Topics: problem_background, established_approaches, known_limitations.
- tech: open-source repositories, libraries, frameworks, APIs, official technical docs, Stack Overflow (GitHub,
  npm, PyPI, MDN, framework docs). Topics: libraries_and_frameworks, apis_and_integrations, architecture_patterns,
  feasibility_and_risks.

Rules:
- Return exactly {per_domain} queries per domain ({total} in total). Group them by domain, most important topic first.
- Each query combines the idea with ONE topic of that domain. Spread the topics. The key topics are
  user_complaints (apps), established_approaches (papers) and feasibility_and_risks (tech): include each of them.
- Make queries specific to THIS idea: the product type, the audience, the must-have features, the platform and
  technology constraints. Use the words people and documents actually use.
- Queries are short keyword searches, not sentences. No years unless recency matters.
- preferred_domains: only well-known sites specific to this idea you are sure about; empty list otherwise. The
  standard sites of each domain are added automatically.
- If <focus> is non-empty this is a FOLLOW-UP search: target ONLY those open questions, still one domain per
  query, and still cover all three domains.

<examples>
Few-shot examples of good and bad queries (for other ideas; never copy them, write queries for THIS idea):
Idea: habit tracker app for university students, mobile, free.
- apps, good: "habit tracker app reviews complaints students"   (user_complaints)
- apps, bad: "What is the best habit tracker?"   (a sentence, not specific to the audience)
- papers, good: "habit formation app intervention study adherence"   (established_approaches)
- tech, good: "react native habit tracker open source offline sync"   (libraries_and_frameworks)
Idea: bakery website with cake pre-orders for pickup.
- apps, good: "bakery online pre-order website small business reviews"   (existing_solutions)
- tech, good: "pre-order website stripe pickup time slots integration"   (apis_and_integrations)
- tech, bad: "website"   (no topic, too broad)
</examples>
""" + BUILDER_RULES

DOMAIN_ORDER = {d: i for i, d in enumerate(DOMAINS)}

# Quick sessions: one general query + the key-topic query per domain, no LLM call.
QUICK_QUERY = {
    "apps": ("{term} app alternatives features", "existing_solutions"),
    "papers": ("{term} research study approaches", "problem_background"),
    "tech": ("{term} open source implementation library", "libraries_and_frameworks"),
}
# The key topic of each domain is always searched on the first pass (fixed fallback query when Claude skipped it).
KEY_QUERY = {
    "apps": "{term} reviews complaints what users dislike",
    "papers": "{term} study evaluation approaches limitations",
    "tech": "{term} implementation feasibility risks libraries",
}


def search_term(state: ArenaState) -> str:
    return (state.get("project_name") or "").strip() or state.get("question", "")[:80]


def _key_query(domain: str, term: str) -> SearchQuery:
    return SearchQuery(query=KEY_QUERY[domain].format(term=term), domain=domain, topic=KEY_TOPIC[domain],
                       preferred_domains=[])


def quick_plan(state: ArenaState) -> ResearchPlan:
    """No LLM: one general query + the key-topic query per domain."""
    term = search_term(state)
    queries: list[SearchQuery] = []
    for domain in DOMAINS:
        query, topic = QUICK_QUERY[domain]
        queries.append(SearchQuery(query=query.format(term=term), domain=domain, topic=topic, preferred_domains=[]))
        queries.append(_key_query(domain, term))
    return ResearchPlan(search_term=term, queries=queries)


def plan_queries(state: ArenaState, focus: list[str] | None = None) -> ResearchPlan:
    settings = get_settings()
    if settings.session_mode == "quick" and focus is None:
        return quick_plan(state)
    per_domain = settings.queries_per_domain
    user_content = f"""{user_case_block(state)}
<focus>{json.dumps(focus or [], indent=2)}</focus>"""

    plan = call_structured(
        ResearchPlan,
        SYSTEM_PROMPT.replace("{per_domain}", str(per_domain)).replace("{total}", str(per_domain * len(DOMAINS))),
        user_content,
        max_tokens=2500,
        run_name="research_planner_llm",
    )
    # Python enforces the budget per domain even if Claude returns more, and fixes the domain order.
    kept: list[SearchQuery] = []
    count = {d: 0 for d in DOMAINS}
    for q in plan.queries:
        if count[q.domain] < per_domain:
            count[q.domain] += 1
            kept.append(q)
    if focus is None:
        kept = ensure_key_topics(kept, plan.search_term or search_term(state), per_domain)
    plan.queries = sorted(kept, key=lambda q: DOMAIN_ORDER[q.domain])
    return plan


def ensure_key_topics(queries: list[SearchQuery], term: str, per_domain: int) -> list[SearchQuery]:
    """Every domain searches its key topic on the first pass. If Claude spent a domain's whole budget elsewhere,
    the domain's last (lowest-priority) query is replaced by the fixed key-topic query; if the budget has room, the
    key query is appended. (Only on the first pass: follow-up searches are focused on the open questions.)"""
    result = list(queries)
    for domain in DOMAINS:
        lane = [q for q in result if q.domain == domain]
        if any(q.topic == KEY_TOPIC[domain] for q in lane):
            continue
        if len(lane) >= per_domain:
            result.remove(lane[-1])
        result.append(_key_query(domain, term))
    return result
