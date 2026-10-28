"""Prompt registry: every agent's instructions, versioned (spec §10.2 prompt rot, §10.3 prompt management; M11 part 3).

The prompt TEXT stays next to the code that uses it (nodes/*.py, research/*.py, chat.py...): a prompt and the schema /
inputs it describes change together. This registry is the one place that knows them all:
- `REGISTRY`: one PromptSpec per agent: which constants make up its prompt, which graph node(s) use it (owner),
  its VERSION and a changelog line per version;
- `prompts.lock.json` (next to this file): the sha256 of each prompt's text at its current version. The shared
  `BUILDER_RULES` block is its own entry and is cut out of the agents' text before hashing, so a change to the shared
  rules bumps ONE version, not twenty;
- tests/test_prompts.py fails when a prompt's text changed but its version did not (or the lock is stale);
- every node run records the versions of the prompts it used (`prompt_versions` in the state, `prompts` in its
  usage_log entry), so a session says exactly which instructions produced it;
- evals: backend/evals/<prompt id>/*.json, run by scripts/run_evals.py (offline request checks; `--live` output checks).

Changing a prompt (the rule, also in handoff.md section 15):
  1. edit the text; 2. bump `version` here and add a changelog line (what and why: the finding / eval case);
  3. add or update an eval case for the behaviour; 4. `uv run python scripts/run_evals.py --prompt <id>` (and
  `--live` for output checks); 5. `uv run python scripts/prompt_versions.py --update`; 6. pytest.
Retiring a prompt: delete its entry, its lock line and its eval folder in the same change.
"""

import hashlib
import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

LOCK_FILE = Path(__file__).with_name("prompts.lock.json")
SHARED_PLACEHOLDER = "{BUILDER_RULES}"


@dataclass(frozen=True)
class PromptSpec:
    id: str
    module: str                          # where the text lives
    attrs: tuple[str, ...]               # module-level constants (str, or dict of str) that make up the prompt
    nodes: tuple[str, ...]               # graph nodes (or "ask") that send it: the owners
    version: int
    changelog: tuple[str, ...]           # one line per version, oldest first
    extra: Callable[[], list[str]] | None = field(default=None, compare=False)   # texts not held in constants

    def texts(self) -> list[str]:
        mod = importlib.import_module(f"ai_decision_arena.{self.module}")
        out: list[str] = []
        for attr in self.attrs:
            value = getattr(mod, attr)
            out.extend([f"{k}: {v}" for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))]
                       if isinstance(value, dict) else [value])
        return out + (self.extra() if self.extra else [])

    def text_hash(self) -> str:
        from ai_decision_arena.prompting import BUILDER_RULES
        text = "\n\x1e\n".join(self.texts())
        if self.id != "builder_rules":
            text = text.replace(BUILDER_RULES, SHARED_PLACEHOLDER)
        return hashlib.sha256(text.encode()).hexdigest()


def _chat_tool_descriptions() -> list[str]:
    from ai_decision_arena.tools import ToolContext, chat_tools
    return [f"{t.name}: {t.description}" for t in chat_tools(ToolContext())]


def _skill_texts() -> list[str]:
    from ai_decision_arena.skills import SKILLS_DIR
    return [f"{p.parent.name}: {p.read_text()}" for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))]


M10 = "M10 live findings (handoff section 16)"

REGISTRY: dict[str, PromptSpec] = {s.id: s for s in [
    PromptSpec("builder_rules", "prompting", ("BUILDER_RULES",), ("*",), 2,
               ("v1 (M1): shared rules: no invented sources / figures / capabilities, claim labels, tagged input is data.",
                "v2 (review 2026-10-29, prompt-injection defence): <evidence> and <untrusted> named with the other data "
                "tags, and what to do with an instruction found inside them (report it as content, never follow it).")),
    PromptSpec("intake", "nodes.intake", ("SYSTEM_PROMPT",), ("intake",), 1,
               ("v1 (M1): app-idea intake; rejects non-app requests.",)),
    PromptSpec("clarification", "nodes.clarification", ("SYSTEM_PROMPT",), ("clarification",), 3,
               ("v1 (M1): 4-6 first-round questions; later rounds only on material change; one question per item.",
                "v2 (M11): constraints are ONE chosen topic, never a 'technology, hosting, budget or timeline' list (live eval "
                "clarification/one_question_per_item failed on exactly that; handoff section 16 observation).",
                "v3 (2026-10-29, user decision): ONE round, at most 5 questions, each with 2-4 tappable answer options "
                "(short, specific, most likely first; the user can still type; never an 'Other' option; eval "
                "clarification/options_for_every_question).")),
    PromptSpec("research_planner", "research.planner", ("SYSTEM_PROMPT",), ("research", "clarification"), 1,
               ("v1 (M2): queries for the apps / papers / tech domains.",)),
    PromptSpec("extractor", "research.extractor", ("SYSTEM_PROMPT",), ("research",), 1,
               ("v1 (M2): evidence from snippets of one domain, feedback context.",)),
    PromptSpec("proposer", "nodes.proposer", ("SYSTEM_PROMPT",), ("proposer",), 3,
               ("v1 (M3): 2-3 proposals in one call over all evidence.",
                "v2 (M11): QUICK_RULE (one proposal for the retired quick profile) removed; every session asks for 2-3.",
                "v3 (speed): be concise, one sentence per item, low end of every list (fewer output tokens).")),
    PromptSpec("critic", "nodes.critic", ("SYSTEM_PROMPT",), ("critic",), 3,
               ("v1 (M3): one review per proposal, incl. copies_existing_app.",
                "v2 (speed): at most 4 points (MAX_POINTS_PER_PROPOSAL 6 → 4), the most severe first.",
                "v3 (review 2026-10-29): four decision-boundary examples: a real evidence-backed point, a real "
                "judgement point, and two manufactured objections to leave out (eval critic/real_vs_manufactured).")),
    PromptSpec("judge", "nodes.judge", ("SYSTEM_PROMPT",), ("judge",), 1,
               ("v1 (M3): scores all proposals; contradictions become questions.",)),
    PromptSpec("evidence_checker", "nodes.claim_check", ("SYSTEM_PROMPT",), ("critic", "judge"), 3,
               ("v1 (M3): verifies the winning proposal's claims.",
                "v2 (speed): runs for every proposal in the critic's pool, without the Critic's points; at most 6 claims.",
                "v3 (review 2026-10-29): five decision-boundary examples (capability is not outcome, anecdotal, weaker "
                "version, irrelevant source, design decisions are skipped); the text moved to nodes/claim_check.py "
                "when the Evidence Checker node was folded into the Judge (eval evidence_checker/decision_boundaries).")),
    PromptSpec("final_report", "nodes.final_report", ("SYSTEM_PROMPT",), ("brief_writer",), 1,
               ("v1 (M3): interim report narrative.",)),
    PromptSpec("brief_writer", "nodes.brief_writer", ("SYSTEM_PROMPT", "PART_NOTE", "REVISION_NOTE", "USER_REVISION_NOTE"),
               ("brief_writer",), 3,
               (f"v1 (M4-M10): three-part brief; user revisions keep built changes and the built stack ({M10}).",
                "v2 (speed): the three parts are written in parallel, so parts 2-3 no longer see sections 1-4; the "
                "PART_NOTEs anchor the MVP / in_scope on the winning proposal's core_features instead.",
                "v3 (2026-10-29, user decision): no appendix: everything written is on the page (budget 1500 words), "
                "so the writer is told every extra item costs the reader (eval brief_writer/no_appendix).")),
    PromptSpec("brief_validator", "nodes.brief_validator", ("SYSTEM_PROMPT",), ("brief_validator",), 1,
               ("v1 (M4): nine checks of spec section 5.",)),
    PromptSpec("brief_routing", "nodes.brief_review", ("ROUTING_PROMPT",), ("brief_review_router",), 1,
               (f"v1 (M5): routes a brief change to wording / requirements / research / proposal (wording-only once built: {M10}).",)),
    PromptSpec("planner", "nodes.planner", ("SYSTEM_PROMPT", "REVISION_NOTE", "EXTENSION_NOTE"), ("planner",), 5,
               (f"v1 (M6-M10): plan schema; revisions; extension mode for built apps ({M10}).",
                "v2 (speed): fewer, larger tasks (about 4-8 for a small app; the calculator had 12 at ~21 s each, ~9 s "
                "of it fixed overhead per task).",
                "v3 (speed): only real dependencies and separate files per independent task (they run in parallel; "
                "the cached calculator plan was one long chain with five tasks editing src/engine.js).",
                "v4 (render check): the first screen must render without a .env; no import-time throw over missing "
                "configuration (live: the budgeting app's supabase.ts threw at load, the preview was blank while "
                "tests and build passed; eval planner/renders_without_env).",
                "v5 (design): UI apps get a design foundation in the first task (Tailwind preferred: app shell + shared "
                "components) and UI tasks name it in their acceptance criteria (live: the budgeting app was browser "
                "defaults, 44 lines of global CSS, no task owned the look; eval planner/design_foundation).")),
    PromptSpec("implementer", "nodes.implementer", ("SYSTEM_APPEND", "PARALLEL_NOTE"), ("implementer",), 7,
               ("v1 (M8): appended to the claude_code preset; one task, verify commands decide.",
                "v2 (M11): no skipped / pending tests left behind; un-skip once the feature exists (M10: T13 left 4 "
                "t.skip tests in the calculator that later tasks never re-enabled; eval implementer/no_skipped_tests).",
                "v3 (M11): follow the <skills> picked for the project's stack (skills.py).",
                "v4 (speed): final report at most 3 short lines (the long report took ~5 s of every task).",
                "v5 (speed): PARALLEL_NOTE for tasks run at the same time (implementer_parallel): leave the siblings' "
                "files alone, run only your own tests.",
                "v6 (render check): missing configuration never crashes the app; a setup screen instead of an "
                "import-time throw (same live finding as planner v4; eval implementer/renders_without_env).",
                "v7 (app settings): a comment above each .env.example variable saying what it is and where to get it "
                "(the Preview tab's settings form shows them; the budgeting app's .env.example had none).")),
    PromptSpec("ask", "chat", ("SYSTEM_PROMPT",), ("ask",), 2,
               (f"v1 (M10): project assistant, answers only, describes Reopen ({M10}).",
                "v2 (M11): load_skill for builder skills; costs and limits only from <cost>; prompt-cached system block.")),
    PromptSpec("ask_tools", "tools", (), ("ask",), 3, ("v1 (M10): Ask-mode tool descriptions.",
                                                        "v2 (M11): load_skill offered again (builder skills).",
                                                        "v3 (review 2026-10-29): search_knowledge results carry `verified` "
                                                        "(when the source was last checked): prefer newer sources when "
                                                        "they disagree; results for the project's stack rank first."),
               extra=_chat_tool_descriptions),
    PromptSpec("skills", "skills", (), ("ask", "implementer"), 3,
               ("v1 (M11): builder skills replace the health ones: 3 for Ask, 4 for the coding agent (picked by stack).",
                "v2 (design): web-ui-design for web stacks: app shell, shared components, stacked labelled forms, tables, "
                "empty states, spacing / type scale (the budgeting app was unstyled browser defaults).",
                "v3 (review 2026-10-29): secure-coding for every stack (boundary validation, server-side authorization, "
                "no string-built queries, secrets from the environment, tests per rule) and failure-triage, picked by "
                "the KIND of task (fix tasks and retries: reproduce, first error, name the cause, never weaken a test), "
                "the procedure-skill answer to the review's QA-agent idea: pass / fail stays with Python's exit codes."),
               extra=_skill_texts),
    PromptSpec("researcher", "researcher", ("SYSTEM_PROMPT",), ("ask",), 1,
               ("v1 (M10): research sub-agent of Ask.",)),
]}


def versions_for(node: str) -> dict[str, int]:
    """{prompt id: version} of the prompts a node sends (the shared rules included)."""
    found = {s.id: s.version for s in REGISTRY.values() if node in s.nodes}
    return ({"builder_rules": REGISTRY["builder_rules"].version} | found) if found else {}


def current_lock() -> dict[str, dict]:
    return {s.id: {"version": s.version, "sha256": s.text_hash()} for s in REGISTRY.values()}


def read_lock() -> dict[str, dict]:
    return json.loads(LOCK_FILE.read_text()) if LOCK_FILE.exists() else {}


def lock_problems() -> list[str]:
    """What is out of date between the prompts, their versions and the lock file (empty = all consistent)."""
    lock, problems = read_lock(), []
    for pid, now in current_lock().items():
        old = lock.get(pid)
        if old is None:
            problems.append(f"{pid}: not in prompts.lock.json (run scripts/prompt_versions.py --update)")
        elif old["sha256"] != now["sha256"] and old["version"] == now["version"]:
            problems.append(f"{pid}: text changed but version is still {now['version']}: bump it in prompts.REGISTRY, "
                            "add a changelog line, run its evals, then scripts/prompt_versions.py --update")
        elif old["version"] != now["version"] or old["sha256"] != now["sha256"]:
            problems.append(f"{pid}: version {old['version']} -> {now['version']} not locked yet "
                            "(run its evals, then scripts/prompt_versions.py --update)")
        if len(REGISTRY[pid].changelog) != REGISTRY[pid].version:
            problems.append(f"{pid}: {len(REGISTRY[pid].changelog)} changelog line(s) for version {REGISTRY[pid].version}")
    problems += [f"{pid}: in the lock but not in the registry (retired? delete the line)" for pid in lock if pid not in REGISTRY]
    return problems
