"""Show or lock the prompt versions (prompts.py, prompts.lock.json).

    uv run python scripts/prompt_versions.py            # table + problems (exit 1 if any)
    uv run python scripts/prompt_versions.py --update   # write the lock; refuses a changed text without a version bump
"""

import json
import sys

from ai_decision_arena.prompts import LOCK_FILE, REGISTRY, current_lock, lock_problems, read_lock

update = "--update" in sys.argv
lock, now = read_lock(), current_lock()
for pid, spec in REGISTRY.items():
    old = lock.get(pid, {})
    state = "ok" if old == now[pid] else ("NEW" if not old else "CHANGED")
    print(f"{pid:18} v{spec.version}  {now[pid]['sha256'][:12]}  {state:8} nodes: {', '.join(spec.nodes)}")
problems = lock_problems()
if update:
    blocking = [p for p in problems if "text changed but version" in p or "changelog line" in p]
    if blocking:
        print("\nnot written:\n  " + "\n  ".join(blocking))
        sys.exit(1)
    LOCK_FILE.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n")
    print(f"\nwrote {LOCK_FILE.name} ({len(now)} prompts)")
    sys.exit(0)
print("\n" + ("\n".join(problems) if problems else "all prompts locked at their versions"))
sys.exit(1 if problems else 0)
