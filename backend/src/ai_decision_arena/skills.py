"""Skills: reusable know-how, loaded only when it is needed (spec §10.5; builder skills since M11).

Each skill is backend/skills/<name>/SKILL.md: a front-matter block (name, description, audience, applies_to) and
instructions. Two audiences:
- ask:   the Ask-mode assistant sees only the one-line descriptions (<available_skills>) and loads a skill's full text
         with the load_skill tool when a question needs it (writing a change request, explaining build results...);
- agent: the coding agent gets the skills whose `applies_to` keywords match the approved plan's tech stack /
         dependencies / testing strategy (Python picks them; "*" = every project), as <skills> in its task prompt.
         A skill with `phases` (review 2026-10-29) is picked by the KIND of task instead: "fix" = a fix task from the
         build or render check, "retry" = a second attempt after a failed verification (failure-triage).
Skill texts are versioned in the prompt registry (prompts.py, id "skills"): editing one is a prompt change.
"""

import re
from functools import lru_cache
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"      # backend/skills


def _parse(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        header, _, body = raw[3:].partition("\n---")
        for line in header.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return {"name": meta.get("name", path.parent.name), "description": meta.get("description", ""),
            "audience": meta.get("audience", "ask"),
            "applies_to": [w.strip().lower() for w in meta.get("applies_to", "").split(",") if w.strip()],
            "phases": [w.strip().lower() for w in meta.get("phases", "").split(",") if w.strip()],
            "instructions": body.strip()}


@lru_cache
def all_skills() -> dict[str, dict]:
    """name -> skill, read once per process (restart to pick up new skills)."""
    skills = (_parse(p) for p in sorted(SKILLS_DIR.glob("*/SKILL.md")))
    return {s["name"]: s for s in skills}


def _for(audience: str) -> dict[str, dict]:
    return {n: s for n, s in all_skills().items() if s["audience"] == audience}


def skills_block() -> str:
    """Ask's menu for the system prompt: names and descriptions only."""
    lines = "\n".join(f"- {s['name']}: {s['description']}" for s in _for("ask").values())
    return f"<available_skills>\n{lines}\n</available_skills>" if lines else ""


def load_skill(name: str) -> str:
    skill = _for("ask").get(name)
    if not skill:
        return f"No skill named {name!r}. Available: {', '.join(_for('ask')) or 'none'}."
    return f'<skill name="{skill["name"]}">\n{skill["instructions"]}\n</skill>'


def agent_skills_for(stack_text: str, phase: str | None = None) -> list[dict]:
    """The coding-agent skills whose keywords occur (as words) in the plan's stack text, plus the "*" ones; skills
    declared for task phases are picked only when `phase` (fix / retry) matches, whatever the stack."""
    words = set(re.findall(r"[a-z0-9.+#-]+", stack_text.lower()))
    chosen = []
    for s in _for("agent").values():
        if s["phases"]:
            if phase and phase.lower() in s["phases"]:
                chosen.append(s)
        elif "*" in s["applies_to"] or any(k in words for k in s["applies_to"]):
            chosen.append(s)
    return chosen


def agent_skills_block(stack_text: str, phase: str | None = None) -> str:
    chosen = agent_skills_for(stack_text, phase)
    if not chosen:
        return ""
    body = "\n".join(f'<skill name="{s["name"]}">\n{s["instructions"]}\n</skill>' for s in chosen)
    return f"<skills>\n{body}\n</skills>"
