"""Does a Pydantic schema fit the API's strict structured-output limit? ("The compiled grammar is too large")

The grammar is compiled before any generation, so a tiny prompt with max_tokens=50 answers the question for almost
nothing. Run it before giving a new, large schema to call_structured (e.g. the M6 planner).
    uv run python scripts/probe_schema.py ai_decision_arena.schemas:BriefPartOne ai_decision_arena.schemas:BriefContent
"""

import importlib
import sys

from ai_decision_arena.llm import get_llm

if len(sys.argv) < 2:
    sys.exit(__doc__)

for target in sys.argv[1:]:
    module, _, name = target.partition(":")
    schema = getattr(importlib.import_module(module), name)
    llm = get_llm(max_tokens=50).with_structured_output(schema, method="json_schema")
    try:
        llm.invoke("Fill with tiny placeholder values.")
        print(f"✅ {name}: fits")
    except Exception as exc:
        if "grammar is too large" in str(exc):
            print(f"❌ {name}: grammar too large")
        elif "parse" in str(exc).lower() or "json" in str(exc).lower():
            print(f"✅ {name}: fits (the 50-token answer was cut off, as expected)")
        else:
            print(f"⚠️  {name}: unknown ({type(exc).__name__}: {str(exc)[:150]})")
