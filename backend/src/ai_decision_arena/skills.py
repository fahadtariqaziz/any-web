"""Skills: know-how the chat agent loads ON DEMAND, only when a conversation needs it.

Each skill is a folder backend/skills/<name>/ with a SKILL.md: a front-matter block (name, description) and
the instructions. Only the one-line descriptions go into the system prompt (cheap, always there); the full
instructions enter the context only when Claude calls the load_skill tool (tools.py). So adding a tenth skill
costs one line of prompt, not a page.

Same idea as Claude Code / Agent SDK skills, kept minimal: no scripts, just instructions.
"""

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
            "instructions": body.strip()}


@lru_cache
def all_skills() -> dict[str, dict]:
    """name -> {name, description, instructions}, read once per process (restart to pick up new skills)."""
    skills = (_parse(p) for p in sorted(SKILLS_DIR.glob("*/SKILL.md")))
    return {s["name"]: s for s in skills}


def skills_block() -> str:
    """The menu for the system prompt: names and descriptions only."""
    lines = "\n".join(f"- {s['name']}: {s['description']}" for s in all_skills().values())
    return f"<available_skills>\n{lines}\n</available_skills>" if lines else ""


def load_skill(name: str) -> str:
    skill = all_skills().get(name)
    if not skill:
        return f"No skill named {name!r}. Available: {', '.join(all_skills()) or 'none'}."
    return f'<skill name="{skill["name"]}">\n{skill["instructions"]}\n</skill>'
