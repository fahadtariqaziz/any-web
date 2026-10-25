"""M4 live check: the brief writer + validator on the cached M3 debate state (calculator idea).

Needs backend/.cache/debate_calculator.json (written by scripts/verify_m3.py). Runs the real nodes in the order the
graph would: brief_writer → brief_validator, and again while the validator asks for a revision (bounded by
max_brief_revisions). 2-6 Claude calls.
    uv run python scripts/verify_m4.py
Writes backend/.cache/brief_calculator.json (the full state) for M5/M6.
"""

import json
import re
import sys
from pathlib import Path

from ai_decision_arena.brief import SECTION_TITLES, URL_RE, cited_objects
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.brief_validator import brief_validator_node
from ai_decision_arena.nodes.brief_writer import brief_writer_node
from ai_decision_arena.schemas import BRIEF_CHECK_IDS, ProblemBrief

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
DEBATE_CACHE = CACHE_DIR / "debate_calculator.json"
BRIEF_CACHE = CACHE_DIR / "brief_calculator.json"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


if not DEBATE_CACHE.exists():
    sys.exit(f"{DEBATE_CACHE} is missing: run scripts/verify_m3.py first.")

settings = get_settings()
state = json.loads(DEBATE_CACHE.read_text())
known = {e["evidence_id"]: e for e in state["evidence"]}
known_urls = {e["source_url"].rstrip("/") for e in state["evidence"]}
print(f"model: {settings.anthropic_model} · {len(known)} evidence records · winner {state['verdict']['winning_proposal_id']} "
      f"· max_brief_revisions {settings.max_brief_revisions} · word budget {settings.brief_word_budget}")

history = []
for attempt in range(settings.max_brief_revisions + 1):
    state.update(brief_writer_node(state))
    state.update(brief_validator_node(state))
    v = state["brief_validation"]
    failed = [c for c in v["checks"] if not c["passed"]]
    history.append((state["brief"]["revision"], v["verdict"], v["word_count"], len(failed)))
    print(f"\n=== draft revision {state['brief']['revision']}: {v['word_count']} words, verdict {v['verdict']}")
    for c in failed:
        print(f"  ✗ [{c['source']}/{c['severity']}] {c['check_id']}: {c['issue'][:180]}")
    if v["verdict"] != "revise":
        break

brief = ProblemBrief.model_validate(state["brief"])
markdown = state["brief_markdown"]
v = state["brief_validation"]
print("\n" + "=" * 100 + "\n" + markdown + "=" * 100)
print(f"\nhistory (revision, verdict, words, failed checks): {history}")
print(f"validator: {v['reason']}")
if v["llm_summary"]:
    print(f"reviewer: {v['llm_summary']}")
if v["clarification_questions"]:
    print(f"questions for the user: {v['clarification_questions']}")

print("\n=== checks")
check(v["verdict"] in ("approve", "clarify"), f"validator ended with approve or clarify ({v['verdict']})")
check(all(f"## {t}" in markdown for t in SECTION_TITLES.values()), "all ten sections present in the markdown")
cited = {i for _, obj in cited_objects(brief) for i in obj.evidence_ids}
check(cited <= set(known), f"every cited evidence id exists ({len(cited)} cited; unknown: {sorted(cited - set(known))})")
unlabelled = [o for _, o in cited_objects(brief) if getattr(o, "label", None) in ("verified", "research_backed") and not o.evidence_ids]
check(not unlabelled, "every verified / research-backed statement cites evidence")
urls = {u.rstrip(".,;:/") for u in URL_RE.findall(markdown)}
check(all(u.rstrip("/") in known_urls for u in urls), f"every URL in the brief comes from the evidence ({len(urls)} URLs)")
check(bool(brief.references) and all(str(r.url) == known[r.evidence_id]["source_url"] for r in brief.references),
      f"references assembled from the evidence ({len(brief.references)})")
verified_ok = all(any(known[i].get("verification_status") == "verified" for i in o.evidence_ids)
                  for _, o in cited_objects(brief) if getattr(o, "label", None) == "verified")
check(verified_ok, "'verified' labels only on statements with a checker-verified source")
numeric = [c for c in brief.success_criteria if c.target and re.search(r"\d", c.target)]
check(all(c.basis in ("user_requirement", "evidence") for c in numeric), f"numeric success targets have a basis ({len(numeric)} numeric)")
check(v["word_count"] <= settings.brief_word_budget * 1.1,
      f"about one page: {v['word_count']} words in sections 1-9 (budget ~{settings.brief_word_budget})")
llm_ids = [c["check_id"] for c in v["checks"] if c["source"] == "llm"]
check(not llm_ids or sorted(llm_ids) == sorted(BRIEF_CHECK_IDS), f"LLM review covered the nine criteria ({len(llm_ids)})")
check(v["verdict"] != "clarify" or bool(v["clarification_questions"]), "a clarify verdict carries questions")
check(len(history) <= settings.max_brief_revisions + 1, "revisions stayed within the cap")

CACHE_DIR.mkdir(exist_ok=True)
BRIEF_CACHE.write_text(json.dumps(state, indent=2, default=str))
print(f"\n💾 full state saved to {BRIEF_CACHE}")
print("\nM4 VERIFY:", "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)")
sys.exit(0 if not failures else 1)
