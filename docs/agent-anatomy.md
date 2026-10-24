# Agent anatomy → our code

From the slide "Anatomy of an Agent" (Day 1 · AI in 2026, p.10): **16 parts, 4 jobs: think · know · do · steer.**
Each part, and where it lives in Health Decision Arena (paths under `backend/src/ai_decision_arena/` unless noted).
The slide's last row has Orchestration and Guardrailing side by side; they get a row each here.

## THINK: the brain

| # | Part | In our code | Why we need it |
|---|---|---|---|
| 1 | LLM ✅ | `llm.py`: `get_llm()`, `call_structured()` (validated Pydantic output, retry on invalid or cut-off output) | Every agent thinks through it |
| 2 | Providers ✅ | Anthropic Claude (`langchain-anthropic`), Tavily (search), LangSmith (tracing) | One LLM provider keeps it simple; LangChain makes swapping easy |
| 3 | Versions ✅ | `config.py`: `anthropic_model`, `quick_model`, `chat_model` pinned, overridable in `.env` | Answers only change when we choose to upgrade |
| 4 | Prompting ✅ | `prompting.py` shared blocks + XML tags; **few-shot** query examples in `research/planner.py`; **chain of thought**: Judge writes `reasoning` before scores (`schemas.PerspectiveJudgement`) | Same case format for all agents; better queries; scores that follow from reasoning |

## KNOW: memory and knowledge

| # | Part | In our code | Why we need it |
|---|---|---|---|
| 5 | Goal ✅ | `FinalReport` (one best plan per perspective); Judge decides "evidence sufficient?"; `completion_node` sets status | A clear finish line: no endless loops, no stopping early |
| 6 | STM ✅ | `state.py` `ArenaState` + `checkpointing.py` Postgres checkpointer (per `thread_id`) | Pause for questions / red flags / review and resume later |
| 7 | LTM ✅ | `memory.py` + `patient_memories` table; browser `patientId` → `X-Patient-Id` (`frontend/src/lib/api/client.ts`); saved at completion and by the `remember_fact` tool; read by intake / clarification (`user_case_block`) and the chat; `GET/DELETE /api/memories` | A returning patient isn't asked the same things again; the chat remembers them |
| 8 | Knowledge base ✅ | `knowledge.py` + `knowledge_docs` table (Postgres full-text search, GIN index); curated docs `backend/knowledge/*.md` + every session's evidence; results cited as `kb_<id>` | Grounded answers with sources the patient can check; knowledge grows with every session |
| 9 | Context mgmt ✅ | Trimmed excerpts (`evidence_block`), one lane's evidence per proposer call, research limits in `config.py`, chat keeps the last 20 messages, skills load only on demand, sub-agent keeps its search results out of the chat's context | Fewer tokens, focused model, no context overflow |

## DO: action

| # | Part | In our code | Why we need it |
|---|---|---|---|
| 10 | Tools ✅ | `tools.py`: **Claude picks** `search_knowledge`, `web_search`, `remember_fact`, `load_skill`, `ask_researcher` in the chat (bounded loop `stream_with_tools`); onboarding calls Tavily from Python (`research/search.py`) | Fresh facts when needed; fixed onboarding stays fast (~30 s) |
| 11 | Skills ✅ | `skills.py` + `backend/skills/<name>/SKILL.md` (meal-planning, habit-coaching, emotional-support, explaining-test-results); only descriptions in the prompt, body via `load_skill` | Know-how only when the conversation needs it, so the prompt stays small |
| 12 | Triggers ✅ | User: `POST /api/decisions`, `/resume`, chat messages. Schedule: `triggers.py` `CheckInScheduler` (one check-in in quiet chats). Manual: `POST /api/triggers/check-ins`. Event: completion → knowledge base + memory | The agent can also start by itself (follow-up), not only when spoken to |
| 13 | Workflows ✅ | `graph.py`: LangGraph `StateGraph`, 11 nodes, fixed edges (shorter path in quick mode) | Predictable, testable steps for a safety-sensitive flow |

## STEER: control

| # | Part | In our code | Why we need it |
|---|---|---|---|
| 14 | Sub-agents ✅ | `researcher.py`: research sub-agent (own prompt, own context, own tools, returns a short cited answer to the chat agent via `ask_researcher`). Also specialist nodes (Proposer, Critic, Judge, Checker), each with 3 parallel lane calls with their own context | Independent viewpoints, nobody grades their own work, parallel speed, chat context stays small |
| 15 | Runtime ✅ | `api/runner.py` background threads; **sandbox**: `backend/Dockerfile` + `docker-compose.yml` (non-root, read-only filesystem, no capabilities, no-new-privileges, memory / CPU / process limits, port bound to localhost) | Runs keep going after the request returns; the agent cannot change its own code or harm the machine |
| 16a | Orchestration ✅ | Routing functions in `graph.py` (`route_after_judge`, `route_after_evidence_checker`...), `guarded()` → completion on failure; in the chat, the agent decides which tool or sub-agent to use | Agents decide what's needed, code turns it into the next step |
| 16b | Guardrailing ✅ | `SAFETY_RULES`; data-not-instructions tags (`<user_input>`, `<source>`, `<skill>`); clarification pause (interrupt); Pydantic validation; `limits.py` loop caps + time budget; model fallback in `llm.py` + `nodes/node_wrapper.py`; tool caps (`MAX_TOOL_ROUNDS`, `MAX_WEB_SEARCHES`); check-in cost cap; "forget me" endpoint; `SecretStr` | Health information only, humans keep control of high-risk decisions, costs stay bounded |
