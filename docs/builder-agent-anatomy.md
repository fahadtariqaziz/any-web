# Agent anatomy of the AI App Builder

From the slide "Anatomy of an Agent" (Day 1 · AI in 2026, p.10): **16 parts, 4 jobs: think · know · do · steer.**
This maps every part to the builder as it is today (2026-10-29: M0–M11, the speed work, parallel tasks, and the
**architecture review of 2026-10-29**, section 7: what it changed and what it deliberately kept).
Paths are under `backend/src/ai_decision_arena/` unless noted. (`docs/agent-anatomy.md` is the older map of the
health app this project started from; kept as history.)

Contents: 1. Is every node an agent? · 2. Node by node (LLM calls, model, prompt, tools, skills, KB) · 3. The 16 parts
· 4. Tools, skills, sub-agents and knowledge in one place · 5. How context is managed (hallucination and context rot)
· 6. Short version to say in the call · **7. The review of 2026-10-29: changed, kept, and why (the thinking)**.

---

## 1. Is every node an agent?

**No, and that is on purpose.** Three kinds of steps:

| Kind | What it means | Which ones |
|---|---|---|
| **Real agents** (the model decides which tool to use, in a loop, until done) | Open-ended work where the steps can't be known in advance | **Coding agent** (implementer), **Ask agent** (chat), **Researcher sub-agent** (called by Ask) |
| **LLM steps** (one or a few calls with a fixed job and a strict output schema, no tools) | The model thinks and writes; Python decides what happens next | intake, clarification, research (planner + extractors), proposer, critic + claim checks, judge (+ consolidates the winner's claim check in Python), brief writer (+ report summary), brief validator, brief review router (sometimes), planner |
| **Python steps** (no LLM at all) | Facts, routing, saving: things a model should not guess | await_* pauses, final report, plan review router, build check (+ secret scan), preview (+ render check), change request router, completion |

So the graph is a **workflow** (fixed steps we define) with **three agents** inside it where freedom is needed.
That keeps time and cost predictable and every decision traceable. Python owns every routing decision and every
loop; the LLM only suggests.

---

## 2. Node by node

Normal run, Claude mode. "Calls" = model calls in one pass, without retries (a retry happens only on an API error or
an invalid output; see section 3 "LLM").
Default model is **Sonnet 5.5**; effort per node is in `config.DEFAULT_NODE_EFFORT`. Local mode
(`LLM_PROVIDER=local`): every model below becomes the local Ollama model (`qwen3.5:4b`, 32K context).

### Phase 1: idea to solution

| # | Node | Kind | LLM calls | Model · effort | What its prompt tells the model | Tools / skills / KB |
|---|---|---|---|---|---|---|
| 1 | **intake** | LLM step | **1** | Sonnet · low | "You are the Intake agent… normalize what they wrote. You do NOT design the solution and do NOT add ideas of your own." Output: name, category, features, constraints, missing info, risk flags | none · none · reads long-term memory |
| 2 | **clarification** | LLM step | **1** (+1 research-planner call in parallel, used if no questions are asked) | Sonnet · low | "Decide whether the user must answer questions, and write those questions." **ONE round (user decision 2026-10-29): at most 5 questions, each with 2–4 tappable answer options** (short, specific, most likely first; the user can still type; never an "Other" option), one topic per question. Python dedupes, caps at 5 and cleans the options | none |
| – | await_clarification | Python (pause) | 0 | – | – | – |
| 3 | **research** | LLM step + Python | **1 planner** (0 if clarification already planned it) **+ 3 extractors** in parallel | planner Sonnet · low; extractors **Haiku** | Planner: "plan web searches in 3 domains" (with few-shot query examples). Extractor: "turn the useful snippets of ONE domain into structured evidence; only what the snippet says, no outside knowledge" | **Tavily** called by Python (not the model): 3 queries × 3 domains, up to 9 searches in parallel |
| 4 | **proposer** | LLM step | **1** | Sonnet · low | "Design 2–3 MEANINGFULLY DIFFERENT solutions… never present outside knowledge as evidence" | none |
| 5 | **critic** | LLM step | **2 per proposal** in parallel = **4–6** (1 critique + 1 claim check each) | Sonnet · low | Critic: "review ONE proposal against the requirements and ALL the evidence; at most 4 points, most severe first". Claim check: "verify the claims of ONE proposal against the evidence it cites; at most 6 claims" | none |
| 6 | **judge** | LLM step + Python | **1** | Sonnet · low | "First write your step-by-step reasoning, then score every proposal on each rubric criterion" (chain of thought before scores). Python computes weighted totals, picks the winner, **consolidates the winner's claim check** (made in step 5: evidence ids filtered, evidence marked verified / unsupported…) and makes ONE routing decision: proceed, or (loops on) research for thin evidence or an unverified material claim, or a question for the user. *The separate Evidence Checker node (old step 7) was folded in here on 2026-10-29: it made no call of its own and was a second routing point for the same decision* | none |

### Phase 2: the brief

| # | Node | Kind | LLM calls | Model · effort | What its prompt tells the model | Tools / skills / KB |
|---|---|---|---|---|---|---|
| 8 | **final_report** | Python | **0** | – | Python assembles winner, alternatives, scores, evidence, objections, open questions | – |
| 9 | **brief_writer** | LLM step | **4 in parallel**: 3 brief parts (sections 1–4, 5–6, 7–9) + 1 report summary | Sonnet · **medium** | "Write the problem statement and solution brief… compact… every statement labelled (verified / research_backed / user_provided / recommendation / assumption) and cited." **No appendix (user decision 2026-10-29):** everything the writer produces is on the page (alternatives in section 4, integrations and roles in section 5, validation notes at the end of section 9); the budget is 1500 words. Summary: "write ONLY from these facts: no new facts". Python writes the references section itself | none |
| 10 | **brief_validator** | Python + LLM | **0 or 1** (0 when a Python check already failed and it goes straight back for a rewrite) | **Haiku** · low | "Check the brief BEFORE the user sees it. Be strict but fair: fail a check only for a real problem a reader would notice" (9 criteria) | none |
| – | await_brief_review | Python (pause) | 0 | – | – | – |
| 11 | **brief_review_router** | Python (+ LLM) | **0**, or **1 small** call when the user didn't choose where the change goes | Sonnet · low | "Route the user's change request to the step that can make the change: requirements / research / proposal / wording" | none |

### Phase 3: planning and building

| # | Node | Kind | LLM calls | Model · effort | What its prompt tells the model | Tools / skills / KB |
|---|---|---|---|---|---|---|
| 12 | **planner** | LLM step | **1** (if Python's plan checks fail, the exact problem goes back to the model inside the same call's retry) | **Opus 5.5** · medium (local mode: local model) | "Write the plan a coding agent will follow task by task, like a senior engineer preparing work for Claude Code. Based ONLY on the approved brief: never contradict it, never add features." v3: fewer, larger tasks, only real dependencies, separate files per independent task | none |
| – | await_plan_review | Python (pause) | 0 | – | – | – |
| 13 | **plan_review_router** | Python | **0** | – | – | – |
| 14 | **implementer** | **Agent** | **1 agent session per task attempt** (up to 40 model turns each), **up to 3 tasks in parallel**, up to 2 attempts per task | Sonnet 5.5 · medium | "You are the coding agent… implement ONE task of an approved plan in the current project folder, the only place you can read or write… commands only through run_command." + `<skills>`, + note about parallel siblings | **6 tools**: Read, Write, Edit, Glob, Grep, `run_command` · **agent skills** picked by Python · no KB |
| 15 | **build_check** | Python | **0** | – | Runs install → test → build in the sandbox, then the **secret scan** (`workspace/secret_scan.py`: key-shaped strings in the source, a `.env` not git-ignored); a failure adds a fix task (max 2 rounds; a secret finding gets its own fix task, and every fix task gets the `failure-triage` skill) | sandbox commands |

### Phase 4: preview and completion

| # | Node | Kind | LLM calls | Notes |
|---|---|---|---|---|
| 16 | **preview** | Python | **0** | Starts the dev server on its own port (4100–4199), ready only after an HTTP answer |
| – | await_change_request | Python (pause) | 0 | Change / Plan a bigger change / Finish |
| 17 | **change_request_router** | Python | **0** | Change → new task C<n>; bigger change → brief writer; finish → completion |
| 18 | **completion** | Python | **0** | Final status, metrics, saves to DB, writes long-term memory and the knowledge base |

### Outside the graph

| Agent | Kind | LLM calls | Model | Prompt | Tools / skills / KB |
|---|---|---|---|---|---|
| **Ask** (chat next to the graph) | **Agent** | **1–5 per reply** (up to 4 rounds with tools, then a final answer) | Sonnet 5.5 (system block prompt-cached) | "You are the project assistant… you already know their idea, the research, the proposals, the brief, the plan and the build." Cannot change the brief, plan or app | **5 tools**: search_knowledge, web_search, remember_fact, ask_researcher, load_skill · **Ask skills** on demand · **KB yes** |
| **Researcher** (sub-agent) | **Agent** | up to **3 rounds** | Sonnet 5.5 | "Another agent asks you one research question. Find the answer and report back to it, not to the user" | **2 tools**: search_knowledge, web_search · no skills · **KB yes** |

**Totals in a normal run up to the brief:** about **15–20 model calls** (1 intake + 1–2 clarification per round + 3–4
research + 1 proposer + 4–6 critic + 1 judge + 4 brief + 0–1 validator). The graph has **21 nodes** (17 steps + 4 pauses)
since the review; it had 22. Measured live on 2026-10-26: **83 s active,
$0.42** to the first readable brief. Then 1 Opus plan call (~75 s) and one agent session per task.

**Loops (by default the fast path, `AUTO_LOOPS=false`):** the Judge and the Validator do *not* send the run back by
themselves. What they would have looped for (thin evidence, an unverified material claim of the winner, a question)
becomes an **open question in the brief**, and the user's brief review is the loop. The validator rewrites at most once,
and only for a failed Python check or a high-severity problem. With `AUTO_LOOPS=true` the thorough loops are on (Judge →
research for thin evidence OR an unverified material claim, Judge → clarification, Validator → up to 2 rewrites or
clarification), each measured at +50–90 s. User-driven loops (clarification rounds, brief review, plan review, change
requests) always work. **Stop (2026-10-29):** the user can stop any run; it finishes the step in progress, saves it, and
waits for Continue.

---

## 3. The 16 parts

### THINK: the brain

| # | Part | In our builder |
|---|---|---|
| 1 | **LLM** | `llm.call_structured()` for every graph step: validated Pydantic output, shows the model its validation error and asks again, asks for a shorter answer when cut off, repeats once on the fallback model, then fails cleanly (`LLMUnavailableError` → run status "failed"). The agents use the Claude Agent SDK (coding) and a streamed tool loop (Ask). |
| 2 | **Providers** | Anthropic Claude (`langchain-anthropic` for the graph, Claude Agent SDK for the coding agent), Tavily for web search, LangSmith for tracing. **Local switch:** `LLM_PROVIDER=local` sends every role (graph, planner, Ask, coding agent) to Ollama. |
| 3 | **Versions** | Model IDs pinned in `config.py`: Sonnet 5.5 (default, Ask, coding agent), Opus 5.5 (planner), Haiku 5.5 (extractor, validator, fallback). The planner's and the coder's models are checked against the API's model list at startup. **Prompts are versioned too** (`prompts.py`: 19 prompts, `prompts.lock.json` hashes; a test fails if a prompt changes without a version bump). |
| 4 | **Prompting** | XML tags for every input (`<user_input>`, `<evidence>`, `<proposals>`…), shared `BUILDER_RULES` added to every prompt, strict output schemas. **Few-shot where judgement must be consistent** (review 2026-10-29): query examples in the research planner; **decision-boundary examples in the claim check** (a capability in a source never proves an outcome; individual reports are anecdotal; design decisions are not claims) and **in the critic** (a real evidence-backed point vs a manufactured objection). **Chain of thought**: the Judge writes `reasoning` before its scores; Python computes the weighted totals. **Zero-shot** with schemas everywhere else (the deterministic steps have no prompt at all). 24 eval cases in `backend/evals/` (offline + live); every prompt change needs one. |

### KNOW: memory and knowledge

| # | Part | In our builder |
|---|---|---|
| 5 | **Goal** | Each step has a clear "done": a validated brief → approval → an approved plan → every task's verify commands pass → build check → a preview that answers HTTP. Completion sets completed / completed with uncertainty / failed. A task is "done" only by **exit codes**, never by what the agent says. |
| 6 | **STM** (short-term) | The graph state of one session (`state.py`) + LangGraph's Postgres checkpointer: a run can pause for days at any of the 4 pauses and resume exactly where it was. |
| 7 | **LTM** (long-term) | `memory.py`, `user_memories` table, keyed by an anonymous browser id. Written at completion (project facts, labelled `[project: name]` so projects don't mix) and by Ask's `remember_fact`. Read by every graph step through the shared case block (`<remembered_from_earlier_sessions>`) and by Ask. **Lifecycle (review 2026-10-29):** every fact is shown with its **source** ("from your answers" = confirmed by the user; "noted by the assistant" = its summary) and its **date**, so a model weighs a guess below a confirmed fact and an old fact below a new one; de-duplicated (unique user + fact); a project's facts are replaced when it completes again; at most 200 facts per user (oldest dropped); "Forget me" deletes all. Approved brief and plan versions are kept in `project_artifacts` and are never replaced by a memory summary. |
| 8 | **Knowledge base** | `knowledge.py`, `knowledge_docs` table, Postgres full-text search, results cited as `kb_<id>`. Content: **6 curated builder docs** (`backend/knowledge/`: how the builder works, exact decimals, Node test runner, Vite, accessibility, secrets) + **the evidence of every finished session**. Used by **Ask and the researcher** (`search_knowledge`). The graph uses fresh research (Tavily), not the KB. **Freshness and fit (review 2026-10-29):** every doc has a `status` (verified / deprecated: kept but never returned), a `verified_at` date (curated: the file's `verified:` line; evidence: its session's completion) and `stack` keywords; results tell Ask when a source was verified ("prefer newer sources when they disagree") and docs for the project's stack rank first (a Vite doc for a Vite project). KB = what the system knows; memory = what happened with this user; the two stay apart. |
| 9 | **Context management** | See section 5. |

### DO: action

| # | Part | In our builder |
|---|---|---|
| 10 | **Tools** | Coding agent: **6** (Read, Write, Edit, Glob, Grep + our `run_command` MCP tool; no Bash). Ask: **5** (search_knowledge, web_search, remember_fact, ask_researcher, load_skill). Researcher: **2** (search_knowledge, web_search). Graph steps: **0** tools for the model; Python calls Tavily, the sandbox and the dev-server manager at fixed steps. Every tool call is logged (`tool_calls` table, `/admin/metrics`). |
| 11 | **Skills** | **10 skills** in `backend/skills/*/SKILL.md`, loaded only when needed, versioned with the prompts. **3 for Ask** (write-a-change-request, explain-build-results, small-or-bigger-change): Ask sees one-line descriptions and loads the full text with `load_skill`. **7 for the coding agent**: picked by **stack** (testing-discipline and **secure-coding** for every project; web-ui-basics, web-ui-design, node-project-hygiene, python-project-hygiene by the plan's tech stack) or by the **kind of task** (**failure-triage** only for fix tasks and retries: reproduce, read the first error, name the cause, never weaken a test). Python puts them in the task prompt as `<skills>`. A skill is a procedure, not information: the review's "QA agent" became this procedure, with pass / fail staying with the exit codes. |
| 12 | **Sub-agents** | The **researcher** (`researcher.py`): Ask delegates a research question, the researcher searches in its own context and returns only a short answer. The **parallel coding agents** (up to 3 at once) each get their own context and their own config folder, and may not write each other's files. |
| 13 | **Runtime** | Each project lives in `generated_projects/<id>/app`. Commands run through `sandbox.run`: allowlisted executables, no shell, path guard, timeouts, output cap, secrets removed from the environment, one command per project at a time. The coding agent's hook refuses any file outside `app/`. Dev servers on ports 4100–4199, stopped after 30 min idle. (Docker per session = M12, optional.) |

### STEER: control

| # | Part | In our builder |
|---|---|---|
| 14 | **Triggers** | **User**: a new idea, answers, approvals, change requests, Ask messages, **Stop** (the run finishes its current step, saves, and waits for Continue). **Task**: one node finishing triggers the next (routing functions); the secret scan failing the build check. **Event**: idle-preview stop, startup reconcile. All 19 listed in `triggers.TRIGGERS` (`GET /api/triggers`). The four protections the review asks for: **idempotent** (one run per session; a second reply is 409; an approval is bound to the hash of what was reviewed), **durable** (the Postgres checkpoint is the truth, a restart resumes), **concurrency-controlled** (one run per project, one sandbox command at a time, parallel agents own disjoint files), **bounded retries** (per call, per task, per fix round). |
| 15 | **Workflows + Orchestration** | **LangGraph** `StateGraph` (`graph.py`): the fixed steps, conditional edges, 4 human pauses (`interrupt()`), parallel calls inside nodes, a self-loop for the implementer's task batches. Python decides every route and every loop (`limits.loops_allowed`); the LLM only suggests. `GraphRunner` runs one background run per project. |
| 16 | **Guardrailing** | Five layers, all enforced by Python, none by the model. **Input:** length limits, "is this an app request" check, clarification until the facts are there. **Evidence:** ids / URLs / quotes from Tavily, claim checks, labelled statements, references assembled by Python. **Tools and execution:** sandbox allowlist, path guard, no Bash, env scrub, one command at a time, **secret scan of the generated source** in every build check (2026-10-29). **Approvals:** nothing is planned before the brief is approved, nothing is built before the plan is approved, each approval bound to the **hash** of the exact text reviewed (a change invalidates it). **Runtime and cost:** round caps, time budget, builder AI budget $5, coding agent budget $15, $2 per task attempt, per-call / per-task timeouts, **safe Stop**. **Fail-safe:** any node error → status "failed", never a silent success; "done" only by exit codes and an HTTP / render check. **Injection:** user text, sources, evidence, files, skills and command output are wrapped as data (`<user_input>`, `<source>`, `<evidence>`, `<generated_file>`, `<skill>`, `<untrusted>`); an instruction found inside is reported, never followed. |

---

## 4. Tools, skills, sub-agents and knowledge in one place

| Who | Tools (count) | Skills | Sub-agent | Knowledge base | Long-term memory |
|---|---|---|---|---|---|
| Graph LLM steps (intake → planner) | 0 (Python calls Tavily in research) | – | – | – (fresh research instead) | read (case block) |
| Coding agent (implementer) | 6: Read, Write, Edit, Glob, Grep, run_command | 7 agent skills, picked by stack or by the kind of task | parallel siblings (own context each) | – | – |
| Ask agent | 5: search_knowledge, web_search, remember_fact, ask_researcher, load_skill | 3 Ask skills, on demand | researcher | **yes** | read + write |
| Researcher sub-agent | 2: search_knowledge, web_search | – | – | **yes** | – |
| Completion | – | – | – | **writes** session evidence | **writes** project facts |

### 4.1 Where Tavily is used (web search)

Claude never searches the web itself. **Every web search is a Tavily call**, through one wrapper
(`research/search.py`: retries, de-duplication, LangSmith trace, logged in `tool_calls` as source "search").

| Where | Who triggers it | How many | What Claude does around it |
|---|---|---|---|
| **Research node** (graph step 3) | **Python**, at a fixed step (`research/search.py: run_searches`) | 3 queries × 3 domains = up to **9 searches in parallel**, up to 5 results each; "advanced" depth for the apps domain (review / forum snippets), "basic" for papers and tech. A follow-up pass (auto loops) searches only the open questions | **Before:** 1 Claude call plans the queries (research planner). **After:** 3 Haiku calls (one per domain) turn the Tavily snippets into structured evidence. Evidence IDs, URLs and titles are copied from Tavily's results by Python, never written by the model |
| **Ask chat**, `web_search` tool | **The Ask agent decides**, only when the knowledge base didn't have the answer | at most **3 per message** | Claude reads the results (wrapped as `<source>` data) and answers with citations |
| **Researcher sub-agent**, `web_search` tool | **The researcher decides** | shares the same limit of 3 per message | Claude compares the results and sends a short answer back to Ask |

So research is **Tavily + Claude together**: Tavily finds the sources, and Claude plans what to search and pulls
the useful evidence out of the snippets. All other graph steps (proposer, critic, judge, brief…) use only that
collected evidence; they make no searches of their own.

---

## 5. How we manage context (against hallucination and context rot)

**Context rot** = the longer and noisier the context, the worse the model gets: it forgets instructions, mixes
things up, fills gaps with guesses. Our rule: **every call gets only what its job needs, and facts come from Python,
not from the model.**

### 5.1 Keep each context small and focused
- **One job per call.** Many small, focused calls instead of one huge one: each critic sees ONE proposal, each
  extractor ONE research domain, each claim check ONE proposal, the brief is written in three parts.
- **No chat history in the graph.** Graph steps don't see earlier model conversations; each step gets a fresh
  context built from the **state** (structured facts), not from the previous model's text.
- **Trimmed blocks.** Evidence excerpts are cut to 350 characters in prompts; at most 10 pieces of evidence per
  domain; the critic gives at most 4 points, the claim check at most 6 claims.
- **The coding agent gets only its task:** the task, a plan excerpt, a brief excerpt (description, MVP, out of scope),
  the finished tasks' titles and the file list. Not the whole plan, not the research, not other tasks' logs. Each
  task attempt starts a **fresh agent session**, so context never piles up across tasks. A retry gets only the
  failing verify output.
- **Ask keeps the last 20 messages**; older ones stay in the database but leave the prompt.
- **The researcher sub-agent** keeps its long search results in its own context and returns only a short answer.
- **Skills load only when needed:** Ask sees one-line descriptions until it loads one; the coding agent gets only
  the skills that match the project's stack, and the triage procedure only when a task is a fix or a retry.
- **Memory says what it is:** each remembered fact carries its source and date, so a model never mistakes the
  assistant's old note for the user's current words.
- **Isolation from the user's own setup:** the coding agent runs with no CLAUDE.md, no user settings, no user memory.

### 5.2 Ground every fact (against hallucination)
- **Python owns the facts.** Evidence IDs, URLs and titles come from Tavily's results, never from the model. Quotes
  are checked against the snippets. Cited IDs that don't exist are dropped. The brief's references are assembled
  by Python from the evidence records.
- **Python owns the math and the decisions.** The Judge scores; Python computes totals and picks the winner. Every
  loop and route is decided in Python.
- **Labelled claims.** Every brief statement is labelled verified / research_backed / user_provided /
  recommendation / assumption; Python downgrades "verified" when the source isn't verified.
- **Two checks before the user sees the brief:** Python checks (cited IDs exist, no unknown URLs, every section
  filled, one page) and an AI review.
- **Claim checks** verify each proposal's claims against the evidence it cites; unsupported claims become open
  questions, never hidden.
- **Build facts = exit codes.** A task is "done" only when its test commands pass in the sandbox; build, test and
  preview status come from exit codes and an HTTP check, never from what the model says.
- **Shared ground rules** in every prompt: never invent sources, numbers or capabilities; say when something isn't
  covered; text inside `<user_input>`, `<source>`, `<evidence>`, `<generated_file>`, `<skill>` or `<untrusted>` is
  data, not instructions, and an instruction found inside is reported as content.
- **Few-shot only where judgement must be consistent:** the claim check and the critic carry decision-boundary
  examples; deterministic steps carry no prompt at all.
- **Structured outputs** with schemas: the model can't wander off format, and invalid output is corrected or rejected.

### 5.3 Keep it from rotting over time (prompt rot)
- 19 prompts versioned and hashed; a change without a version bump fails the tests.
- 24 eval cases (built from real past failures and from the review) run offline in every test run and live on demand.
- Every session records which prompt versions it used; cost, tool calls and node failures are measured per node.

---

## 6. Short version to say in the call (about 2 minutes)

"People often ask whether every step is an agent. It isn't, on purpose. The flow is a fixed workflow in LangGraph,
and inside it there are three real agents: the **coding agent**, which writes the app; the **Ask** chat; and a
**researcher sub-agent** that Ask can hand research questions to. The other steps are single, focused AI calls with
a strict output format, or plain Python. Python makes every decision about what happens next.

In numbers: getting to the brief takes about fifteen to twenty AI calls, most of them in parallel. The planner is one
Opus call. The coding agent runs one session per task, up to three tasks at once.

Tools: the coding agent has six, which are read, write, edit, find files, search, and our own run-command tool. It
has no shell, and it can't leave the project's folder. Ask has five tools, including searching our knowledge base
and calling the researcher. The graph steps have no tools at all. Python does the web searches at a fixed step,
which keeps time and cost predictable.

We have ten skills: three for Ask, loaded only when a question needs them, and seven for the coding agent, picked
by Python from the project's tech stack, or, for a fix task, by the kind of task. The knowledge base holds six curated
docs plus the evidence from every finished project, each with the date it was verified, and Ask and the researcher use
it.

Against hallucination and context rot, the rule is: every call gets only what its job needs, and facts come from
Python, not from the model. Each critic sees one proposal. The coding agent sees only its own task and starts fresh
for every task. Sources, links and scores are handled by Python. Every claim in the brief is labelled and cited.
And a task only counts as done when its tests actually pass."

---

## 7. The review of 2026-10-29: what we changed, what we kept, and why

A production review of this document (sub-agents, knowledge base, skills, prompting, guardrails, STM, LTM, triggers,
context management, and "which nodes to remove") came in on 2026-10-29. We did not implement it as a list; we applied
**its own two criteria** to the code: *keep what provides independent validation, human control or verification;
remove what is redundant orchestration*, and *reliability, guardrails and context first; more agents and memory
features after*. Everything below is in the tests (`verify_m0.sh`), the prompt registry and the eval cases.

### 7.1 Node structure (the "koi node remove karna?" question)

| Node | Review said | What we did | Why (the reasoning) |
|---|---|---|---|
| **7 Evidence Checker** | remove as a separate node, *unless it does extra validation* | **Folded into the Judge** (`nodes/claim_check.py` keeps the LLM call used by the critic; `consolidate()` is the Python part; the Judge makes one routing decision) | It made no model call of its own, yet it was a **second routing point for the same decision** ("is the winner defensible?"). One "decide" step with all its inputs (scores, critic, claim gaps, loop limits) is easier to audit than two. Its Python work (id filtering, evidence statuses, "Unverified:" open questions) **was kept**, inside the Judge. Graph: 22 → 21 nodes, one route function fewer, one trigger row fewer. |
| **8 Final Report** | merge into a helper before the Brief Writer, *unless it must be saved / inspected on its own* | **Kept as a node** | By the review's own condition: the report **is** saved to the database at completion, served by `GET /report`, shown in the admin ReportView, and its narrative is written in parallel with the brief. Making it a helper would re-assemble it on every brief revision (three revision paths) for no saving: it makes **no model call** and takes well under a second. |
| **9 Brief Writer** (4 calls) | try 1 call | **Kept 3 parts + 1 summary** | The whole brief schema in one call **exceeds the API's strict-output grammar limit** (found in M4, `scripts/probe_schema.py`). The parts already run **in parallel**, so wall time is one call's; the validator keeps them consistent. |
| **16 Preview** | make it conditional | **Kept, always on** | The live preview *is* the product (Lovable-style), and its render check found a real bug (a blank page while tests and build passed). |
| Approval pauses, Validator, Build Check, Completion | keep | kept | They are the independent validation, human control and verification the review wants preserved. |

### 7.2 The other eight areas

| Area (part #) | Review's point | Already there | What we added on 2026-10-29 | Deliberately not done, and why |
|---|---|---|---|---|
| **Sub-agents** (12) | research sub-agents for complex ideas; an independent reviewer for high-risk projects; a QA agent; coding agents with file ownership | 3 research **domains** run as parallel LLM steps (cheaper than agents, same split); coding agents with disjoint files, own context, own config dir, sandbox | the review's **QA agent became a procedure**: the `failure-triage` skill for fix tasks and retries; pass / fail stays with Python's exit codes, so an opinion can never be mistaken for a result | an **independent reviewer agent**: the critic + claim check + judge already give three independent reads of the winner, and the evals have shown no miss that a fourth call would catch; revisit with eval data (handoff 2.6) |
| **Knowledge base** (8) | versioned, fresh, filtered by stack, with provenance | full-text search, `kb_<id>` citations, curated docs with URLs, evidence per session | `status` / `verified_at` / `stack` columns (migration), deprecated docs never returned, **results say when a source was verified**, docs for the project's stack rank first, the Ask tool told to prefer newer sources | hybrid / vector search: the review itself says "only where the existing retrieval is insufficient"; we have measured no miss yet |
| **Skills** (11) | nine recommended; audit overlap; load on demand; version them | 7 skills, versioned, picked by stack or loaded by Ask | **secure-coding** (every stack) and **failure-triage** (picked by the *kind* of task, a new mechanism) | the six "skills" for graph steps (requirements-discovery, evidence-evaluation, solution-design, risk-review, technical-writing, implementation-planning): those steps have **no tool loop**, so a skill would just be more prompt text; their prompts already carry those rules, versioned and eval'd |
| **Prompting** (4) | few-shot where judgement must be consistent; Python computes totals; evaluate every change | XML inputs, shared rules, strict schemas, few-shot queries, Judge reasoning + Python totals, 13 evals | **decision-boundary examples** in the claim check (v3) and the critic (v3); 11 new eval cases (24 total); the shared rules name every data tag | few-shot for the brief writer / planner: their prompts are long already and the validator / plan checks catch the failure modes we have seen; the brief validator's AI review stays second to the Python checks |
| **Guardrails** (16) | five layers; injection defence; dependency and secret checks; approval hashes; fail-safe; verified success | approvals by hash, sandbox, env scrub, budgets, exit-code facts, failed status on any error, tags as data | **secret scan** of the generated source in every build check (its own fix task); **safe Stop** (finishes the step, saves, waits); `<evidence>` and `<untrusted>` named in the shared rules with the expected behaviour on an embedded instruction | a dependency vulnerability scan (`npm audit`): needs the network inside the sandbox and gives advisory results; left for the Docker runtime (M12) where network policy lives |
| **STM** (6) | keep big outputs out of the checkpoint, keep ids and summaries | agent logs live in `.builder/logs/`, build output is capped, evidence excerpts are trimmed | nothing new: the review's rule was already the design | – |
| **LTM** (7) | extract → validate → scope → dedupe → version → retrieve → expire | project-scoped facts, dedupe by constraint, replaced on re-completion, Forget me | facts carry their **source and date** in the prompt (validate + retrieve), a **cap of 200 per user** (expire) | relevance filtering at load time: 40 short facts cost ~3k tokens; not worth a retrieval step until users have many projects |
| **Triggers** (14) | treat events as reliable: idempotent, durable, concurrency-controlled, bounded retries; cancellation | one run per session (409 on a second), Postgres checkpoint, hash-bound approvals, bounded retries | **Stop** (`POST /cancel`) at a checkpoint boundary, resumable; the trigger table now has 19 rows | a scheduled-maintenance trigger (stale KB, old project folders): that is the M12 cleanup CLI |
| **Context management** (9) | every node gets only what its job needs; provenance kept; stale context invalidated; parallel agents isolated; observability | all of section 5 | memory facts labelled; the Ask knowledge results dated | – |

### 7.3 One sentence per change, for the call

- **Judge absorbs the Evidence Checker:** one decision, one place; nothing it verified was dropped.
- **Final Report, Brief Writer, Preview stay:** the review's own conditions say so once you look at the code (saved and shown; API limit; the product).
- **Secret scan:** the rule "no keys in code" is now checked, not trusted.
- **Stop:** a run can be stopped without losing work, and only the user continues it.
- **Few-shot where it matters:** the claim check and the critic learn the decision boundary, not just the format.
- **Two skills:** secure-coding for every project; failure-triage only when something failed.
- **Knowledge with a date:** every source says when it was verified; the project's stack ranks first.
- **Memory with a source:** "you said" and "the assistant noted" are not the same, and the model sees which is which.
- **Everything measured:** 11 new eval cases, new tests for every change, prompts re-locked.

### 7.4 User decisions after the review (2026-10-29, same day)

- **One clarification round, five questions at most, each with answer options** (part 4 Prompting + part 16 Guardrails:
  `max_clarification_rounds = 1`, `MAX_QUESTIONS_PER_ROUND = 5`, `ClarificationQuestion.options`; Python dedupes, caps
  and cleans; the UI shows the options as tappable chips and keeps the free-text box). Why: fewer, better questions
  with suggested answers get the user to the research faster than three rounds of typing; the Judge's and the
  validator's own questions become open questions in the brief instead of a second round.
- **No appendix in the brief** (part 9 Context: `brief.py` renders every item in its section, budget 1500 words, the
  validator's word check stays). Why: an appendix the user "must still read" was content hidden below the fold.
- **A redesigned UI** (landing page with a section per functionality and animated mocks of each screen, a frosted top
  bar, gradient accents, animated stage chips, question cards, animated tabs and drawer; `motion` library). Checked
  with headless-Chrome screenshots against the offline fake API before the user saw it.
