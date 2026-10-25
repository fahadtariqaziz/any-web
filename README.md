# ai-lab-2 — AI App Builder (Lovable-style)

A LangGraph multi-agent system that turns an app or website idea into a researched, validated problem statement and
solution brief, an approved implementation plan, and a generated project with a live preview. It was copied from the
Health Decision Arena (ai-lab) and is being converted milestone by milestone: see `handoff.md` for the plan, the current
state, and how to run it (ai-lab-2 uses ports **8001** / **3001** so it can run beside ai-lab on 8000 / 3000).

Quick checks: `bash backend/scripts/verify_m0.sh` (backend tests + frontend lint and type check).


Terminal 1 — backend
cd ~/pro/ai-lab-2/backend
uv sync
FRONTEND_URL=http://localhost:3001 uv run uvicorn ai_decision_arena.api.main:app --reload --port 8001
uv sync installs the new langchain-ollama package. In the startup log, look for planner model qwen3.5-4b-32k is available. That line confirms local mode is on; if it shows a claude-… name, the backend didn't pick up .env.

Terminal 2 — frontend
cd ~/pro/ai-lab-2/frontend
NEXT_PUBLIC_API_URL=http://localhost:8001 npx next dev -p 3001

Then test
1. Open http://localhost:3001 and start a small idea, for example "a simple tip calculator web page".
2. Answer the clarification questions and approve the brief and the plan as usual.
3. To check that Ollama is doing the work, run ollama ps in a third terminal while a step runs. qwen3.5-4b-32k should be listed.