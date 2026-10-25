# ai-lab-2 — Handoff: AI App Builder (Lovable-style)

> **Read this first in every new session.** It is the always-current record: where the project stands, how it is built,
> the plan we follow, and what is next. **Update it after every major change** (structure, decisions, progress, next step).
>
> **New agent / new session? Start here (10 minutes):**
> 1. Read section 0 (where we are), "▶ Next step" at the very end, and the next milestone's block in section 8.
> 2. Read **section 15 (how to work here)** and **section 16 (gotchas)** in full: they are the lessons of M0–M10.
> 3. Check the machine: `git status` (clean = the user committed the last milestone; if not, ask), the user's dev
>    servers (`lsof -nP -iTCP:8001 -sTCP:LISTEN`, `lsof -nP -iTCP:3001 -sTCP:LISTEN`; reuse them, never start a second
>    one), `bash backend/scripts/verify_m0.sh` (must end with `M0 VERIFY: PASS`).
> 4. The product spec is saved verbatim in `docs/app-builder-spec.md` (milestones cite it as "spec §4.3").
> 5. To see the whole product working, open the reference project: http://localhost:3001/c/e39ceeb5-cf6b-4950-b518-b656ec65515b
>    (the calculator built in M9 and extended live in M10: dark theme, percent key, then a scientific mode through the
>    brief-first "bigger change"; its conversation shows every pause). Its preview idle-stops after 30 min: press Start.
>
> **Working rule (agreed 2026-10-24):** one milestone at a time. For each: build → run its verify script(s) → report
> the real result → the user commits and pushes (**Claude never commits or pushes**) → wait for "pushed" → next
> milestone. Ask the user when a decision is theirs (section 13) or before a live run that costs real money.

---

## 0. Status at a glance

| | |
|---|---|
| **Spec** | `docs/app-builder-spec.md` — the user's original brief, verbatim (clarification §1, research §2, proposals §3, brief §4.1–4.10, validation §5, review §6, planning §7, implementation §8, preview + isolation §9, platform §10.1–10.11, constraints §12, outcome §13). The milestone blocks below quote the parts each one needs. |
| **Concept (decided 2026-10-24)** | An AI application builder like Lovable: the user describes an app or website; the system clarifies, researches, proposes, critiques, judges, writes a validated problem statement + solution brief, gets approval, plans (Opus 5.5), implements (Sonnet 5.5) in an isolated session folder, and shows a live preview beside the chat. |
| **Where we are** | **M0–M10 done and pushed (2026-10-25; last commit `1a8c0c7` "Frontend UI with live preview."). The pipeline works end to end:** idea → clarification → research (3 domains) → proposals / critic / judge / checker → validated brief → **user approval** → Opus plan → **user approval** → Sonnet coding agent builds task by task (verified by real commands) → build check → **live preview** → change requests → finish. Proven by the M9 E2E over HTTP: a 12-task Opus plan built 12/12 on the first attempt, build + preview + one change request, agent cost $0.74 (section 14). **M10: the Lovable-style builder UI** is the main UI: `/` = "What do you want to build?" + recent projects, `/c/<id>` = conversation left (questions, review cards, change requests, Ask mode) + live preview / Brief / Plan / Build / Activity right. The admin view (`/admin`, `/decisions/<id>`) stays as the detailed view; both link to each other. Also in M10 (from the user's live browser testing): **Ask about app** (project assistant, never changes anything), **Reopen** a finished project, **Plan a bigger change** = brief edited first → approval → a **plan extension** with only the new tasks → approval → only those tasks built, resizable chat | preview split, **Download code** (folder picker / zip). Proven live on the reference calculator: 24/24 tasks, build check 4 passed, scientific results checked independently (section 14). |
| **Milestones** | M0 harness · M1 intake + clarification · M2 research · M3 debate · M4 brief writer + validator · M5 brief review · M6 Opus planner + plan review · M7 workspace / sandbox / processes · M8 coding agent (Claude Agent SDK) · M9 build check / preview / change requests · M10 Lovable UI. Details: section 8 (✅ blocks), section 14 (progress log with real numbers), section 12 (decisions). |
| **Next milestone** | **M11 — Platform hardening** (section 8), done in parts, each verified and committed by the user. **Part 1 (cost + usage) done 2026-10-25, waiting for the user's commit**: every builder model call is metered (tokens + USD per node run in `usage_log`, `usage_events` table), session LLM budget, `GET /usage` (per stage / first build / each change / step), `GET /api/metrics`, Cost card in the Build tab, cost per change in the chat; `verify_m11.py` PASS. Next parts: `tool_calls` log, prompt registry + evals, builder knowledge / skills / cleanup, then a brand-new idea end to end (never done since M10). |
| **Models (verified 2026-10-24 via `client.models.list()`)** | `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` are all available to the key in `backend/.env`. Configured default: `ANTHROPIC_MODEL=claude-sonnet-5-5`. |
| **Environment (verified 2026-10-24/25)** | macOS, zsh · uv 0.12.21 · Python 3.13.12 · Node 22.22 · npm 10.9 · Postgres 16.15 running, DB `ai_decision_arena_2` at Alembic head `a5b6c7d8e9f0` (M11 `usage_events`) · `claude-agent-sdk` 0.2.174 (ships its own Claude Code CLI 2.1.310) · `psutil` 7.2 · Docker CLI 29.4 present but **daemon not running** · ports **8000/3000 are the original ai-lab** → ai-lab-2 runs on **8001/3001** (the user starts them with `--reload`; section 11) · previews use ports **4100–4199** · generated apps in `generated_projects/` (git-ignored). |
| **Tests** | `bash backend/scripts/verify_m0.sh` = 244 pytest + eslint + tsc, ~30 s. Offline: fake LLM, fake Tavily, `FakeAgent` for the coding agent, in-memory checkpoints, no DB; but sandbox commands, git and dev servers (`python3 -m http.server {port}`) run for REAL under tmp dirs. Live checks: `backend/scripts/verify_m1..m11.py` (real APIs, node level; m10 = UI contract + rendered page) and `scripts/api_flow.py --auto` (full HTTP E2E); what each needs, writes and costs: section 11. No frontend unit tests (lint + tsc + `next build` + headless-Chrome DOM checks + the user's browser check). Free UI walk-through of every pause: `scripts/fake_api.py` (section 11). |

---

## 1. Target product in one paragraph

User prompt → **clarification** (2–3 rounds, pauses for answers) → **research** in 3 domains (existing apps & user feedback ·
papers & technical literature · feasibility & implementations) → **proposer** (2–3 solution proposals in one call) → **critic** → **judge**
(scores, picks the strongest, may loop to research / clarification) → **evidence checker** → **brief writer** (one-page problem
statement + solution brief with labelled claims and real references) → **brief validator** (deterministic + LLM checks) →
**user review** (approve or request changes; changes route back to the right node) → **planner** (Opus 5.5, Claude-Code-style
implementation plan) → **user approval** → **implementer** (Sonnet 5.5 coding agent, one task per step, verified by real
commands) → **build check** → **preview** (dev server per session, health-checked) → **change requests** from the chat →
done. Every generated project lives in `generated_projects/<session_id>/`, isolated from the builder and from other sessions.

---

## 2. Current architecture (started as a copy of the ai-lab health app; 2.1 and 2.3 are kept current)

### 2.1 Graph today (`backend/src/ai_decision_arena/graph.py`, 21 nodes + completion)
```
START → intake → clarification ──(need answers, ≤3 rounds)──► await_clarification ──► clarification
                     │ enough info
                     ▼
                 research (3 domains: apps / papers / tech, parallel) ◄──────────────────┐
                     ▼                                                                      │
                 proposer (2–3 proposals, 1 call) → critic (per proposal) → judge (1 call)─┤
                                                           ├──(ask user)──► clarification   │
                                                           ▼                                │
                                                     evidence_checker ──(material gap)──────┘
                                                           ▼
                                                     final_report → brief_writer → brief_validator ──(revise ≤2)──► brief_writer
                                                                                       ├──(clarify, loop allowed)──► clarification
                                                                                       └──(approve)──► await_brief_review (pause)
await_brief_review → brief_review_router ──(approved, hash guard)──► planner (Opus 5.5) → await_plan_review (pause)
                                         ├──(wording)──► brief_writer      ├──(requirements)──► clarification
                                         ├──(research)─► research          └──(proposal)──────► proposer
await_plan_review → plan_review_router ──(approved, brief + plan hashes)──► implementer (Sonnet agent, 1 task attempt/step)
                                       └──(changes, ≤ max_plan_revisions)──► planner
implementer ──(a task pending)──► implementer   ──(all done / failed / blocked / budget)──► build_check
build_check ──(failed, fix round left: fix task F<n> added)──► implementer   ──(else)──► preview → await_change_request (pause)
await_change_request → change_request_router ──(change: task C<n>)──► implementer ──(finish)──► completion → END
                                             └──(replan = "Plan a bigger change")──► brief_writer (edits the approved brief)
                                                 → brief_validator → await_brief_review (WORDING-ONLY once built) → planner
                                                 (EXTENSION mode: only new tasks, built tasks keep their status) → await_plan_review
completion → END, but a finished built project can be REOPENED by the API (`{"type":"reopen"}`: update_state as
await_change_request, then the run continues at change_request_router).
Pauses (interrupt): await_clarification, await_brief_review, await_plan_review, await_change_request. Draw it:
`cd backend && uv run python scripts/draw_graph.py` (mermaid, phases 1–10).
Any node that raises → error stored (nodes/node_wrapper.py) → completion (status failed).
```

### 2.2 Tech stack (unchanged)
| Area | Choice |
|---|---|
| Orchestration | LangGraph 1.2 (`StateGraph`, conditional edges, `interrupt()`, Postgres checkpointer) |
| LLM | Anthropic Claude only via `langchain-anthropic` 1.7 (`ChatAnthropic.with_structured_output(method="json_schema")`) |
| Web research | Tavily |
| Tracing | LangSmith |
| Backend | Python 3.13 + FastAPI + Pydantic 2, managed with `uv` |
| Persistence | PostgreSQL 16 (Homebrew) + SQLAlchemy 2 / Alembic; LangGraph `checkpoint*` tables in the same DB |
| Frontend | Next.js 16 + React 19 + TypeScript + Tailwind 4 |
| Runtime (optional) | Docker for the backend (`docker-compose.yml`, sandboxed container) |

### 2.3 Folder layout
```
ai-lab-2/
├── handoff.md                      # this file
├── docker-compose.yml              # backend container (Postgres stays on the host)
├── docs/                           # app-builder-spec.md (the spec), requirements.md, pivot-medical.md, agent-anatomy.md — history
├── generated_projects/             # git-ignored: <thread_id>/{app,.builder}, .shared/ (tool links + package caches)
├── backend/
│   ├── .env (not in git; template .env.example), pyproject.toml, uv.lock, alembic.ini, Dockerfile
│   ├── migrations/versions/        # Alembic migrations (10 so far; head a5b6c7d8e9f0 = usage_events)
│   ├── knowledge/*.md              # curated knowledge docs (STILL health: emergency signs, medication... M11 replaces)
│   ├── skills/*/SKILL.md           # chat skills (STILL health: meal-planning, habit-coaching... M11 replaces)
│   ├── .cache/*.json               # cached real states for the verify scripts (git-ignored; section 11)
│   ├── scripts/                    # run_graph, run_intake, run_research, api_flow (HTTP end to end), check_env, draw_graph,
│   │                               #   probe_schema (grammar limit), load_knowledge, print_helpers, verify_m0.sh, verify_m1..m10.py,
│   │                               #   spike_agent_sdk.py, fake_api.py (offline API with the test fakes, port 8002), verify_m11.py
│   ├── tests/                      # pytest: conftest (FakeLLM, fake search, FakeAgent, process_manager fixture,
│   │                               #   finish_session), test_graph, test_limits, test_sources, test_schemas, test_nodes,
│   │                               #   test_research, test_brief, test_brief_review, test_plan, test_workspace,
│   │                               #   test_implementer, test_delivery, test_pipeline_fake, test_api (TestClient), test_usage
│   └── src/ai_decision_arena/      # package name kept (rename = churn, no value now)
│       ├── graph.py, state.py, schemas.py (~1200 lines), config.py, limits.py, prompting.py, llm.py, progress.py,
│       │   pricing.py (price table, tokens → USD), usage.py (UsageMeter, usage_log, session_cost) — M11
│       ├── brief.py (brief references / labels / rendering / deterministic checks), plan.py (plan checks / rendering / hashes)
│       ├── nodes/  intake, clarification, research, proposer, critic, judge, evidence_checker, final_report (+ completion),
│       │           brief_writer, brief_validator, brief_review (await + router), planner (+ await + router), implementer, delivery (build_check, preview,
│       │           await_change_request, change_request_router), node_wrapper
│       ├── research/  planner (queries), search (Tavily), extractor (snippets → Evidence), sources (domains, url utils)
│       ├── workspace/  paths (session folders, safe_path, tool_path_problem), sandbox (one command), processes (dev
│       │               servers, M7), agent (Claude Agent SDK adapter, M8)
│       ├── chat.py (Ask mode: project assistant), tools.py, researcher.py, skills.py, knowledge.py, memory.py, triggers.py, checkpointing.py
│       ├── db/  engine, models (10 tables), repository
│       └── api/  main (decisions endpoints), runner (background threads), chat (transcript + Ask), memories, triggers, schemas, errors
└── frontend/src/
    ├── app/(chat)/   `/` (NewProject) and `/c/[threadId]` (BuilderView) — the Lovable-style builder (BuilderShell layout)
    ├── app/(admin)/  `/admin`, `/decisions/[threadId]` — full pipeline view: DecisionView renders ONE panel per state
    │                 (NowPanel while running; ClarificationForm / BriefReviewPanel / PlanReviewPanel / ChangeRequestPanel
    │                 per pause; finished: AppView + PlanView + BriefView + ReportView), PipelineStepper (10 stages)
    ├── components/   builder/ (M10: BuilderShell, ProjectsDrawer, ProjectListContext, NewProject, useStartProject, BuilderView,
    │                 ChatPane, ActionCards, Composer, Messages, StageChips, WorkingChip, WorkPane, PreviewPane),
    │                 session/ (admin panels + BuildViews: PreviewCard, BuildCard, TaskList; RiskFlagBanner), report/, debate/, evidence/, ui/
    ├── hooks/  useDecision (poll 2 s running, 5 s paused/interrupted, stop when finished), useLive (useBrief, usePlan,
    │           useImplementation, usePreview...), useFetch, useStoredList, useNow
    └── lib/  api/client.ts, api/types.ts (hand-written mirror of API models), pipeline.ts (STAGES, NODE_INFO, progress
              parsing), chatStages.ts (chat working-chip labels per node), format.ts (status labels / tones)
```

### 2.4 Mechanisms we keep (platform, not health-specific)
- `llm.call_structured(schema, system, user)`: validated Pydantic output, self-correcting retries, truncation handling, fallback model, `LLMUnavailableError`.
- `nodes/node_wrapper.wrap_node`: session mode, `active_seconds`, exception → `ErrorRecord` in state → `completion` (status failed); interrupts re-raised.
- `graph.guarded()` edges: any stored error short-circuits to completion.
- Clarification split in two nodes: LLM decision (`clarification`) and human pause (`await_clarification` with `interrupt()` + validation loop). **Every new pause copies this split.**
- `limits.loops_allowed()`: Python decides every loop (round caps + active-time budget); the LLM only suggests.
- Python-owned trust boundaries: evidence ids/URLs/titles come from Tavily hits, never from the LLM; quotes are checked against snippets; cited ids are filtered to known ids; weighted totals computed in Python.
- `progress.report()` custom stream events → `GraphRunner` progress lines → frontend "now" panel.
- `api/runner.GraphRunner`: one background run per thread, checkpoint is the truth, `interrupted` state resumable with `{"type":"continue"}`.
- `config.Settings` (pydantic-settings, `.env` overrides, validated rubric), `session_mode` context var.
- Chat tool loop (`tools.stream_with_tools`, bounded rounds), research sub-agent (`researcher.py`), skills loader, knowledge base (Postgres FTS), long-term memory keyed by a browser id, scheduled trigger thread.
- Frontend: polling hook, resume flow, discriminated `pending` payloads, stepper derived from status, live snapshot tabs.

### 2.5 Health-app leftovers still in the code (checked 2026-10-25, after M10)
Everything on the main path (prompts, schemas, state, DB columns, research domains, rubric, admin UI, builder UI, Ask
mode: chat / tools / researcher prompts) was converted in M1–M10. Still health-flavoured, all OFF the build path:
- `backend/knowledge/*.md` (emergency-warning-signs, medication-safety...): still loaded in `knowledge_docs` (kind
  `curated`) but **not searchable** since M10 (`knowledge.INCLUDE_CURATED = False`) → M11 replaces them with builder
  docs and turns it back on.
- `backend/skills/*` (meal-planning, habit-coaching, emotional-support, explaining-test-results): the chat no longer
  offers `load_skill` / the skills block (M10) → M11 builder skills.
- `triggers.py` check-ins for quiet **quick** chats (`QUIET_CHATS_SQL` `mode = 'quick'`): the UI no longer starts quick
  sessions, so it finds only old ones → M11 replaces it with the idle-preview trigger. `memory.py` docstrings say
  "patient"; `config.py` quick-profile settings (`quick_model`, `QUICK_OVERRIDES`) still exist for old sessions → M11.
- DB: `knowledge_docs.condition` column (feeds a generated FTS column) → M11.

### 2.6 Gaps still open (planned)
Prompt registry / versions, eval cases, `tool_calls` table, builder knowledge + skills, idle trigger beyond previews
(M11, parts 2–4) · Docker runtime per session (M12). (Per-node token + USD accounting: done in M11 part 1.)
No prompt caching yet: one Ask reply costs ~$0.05 (brief + plan + build context resent each time, measured); the graph
prompts are one-shot. Candidate for the prompt-registry part (system prompts stable → `cache_control`).
M10 leftovers (small, pick up in M11): ~~only the coding agent's cost is metered~~ (fixed in M11 part 1: the Build tab's
Cost card splits builder AI / coding agent per stage and per change; the chat card says "Coding agent, all tasks");
C-task titles use the change ROUND ("C2 Change request 3"
when a Finish took round 2; the transcript links tasks by that title, so rename carefully); the chat header keeps the
intake `project_name` after the brief renamed the project; a coding agent may leave `t.skip(...)` tests behind (seen:
4 skipped in the calculator) — the build check only counts failures.
Not planned yet: auth / multi-user isolation of the API (sessions are keyed by thread_id + a browser user id only);
streaming the brief / plan while they are written.

---

## 3. Reuse map: what changes, what stays

### 3.1 Node by node
| Node | Reuse | What changes |
|---|---|---|
| `intake` | logic as-is | prompt, `IntakeResult` fields, validation message ("describe an app or website"), `is_app_request` |
| `clarification` + `await_clarification` | **as-is** (split, dedupe, merge, interrupt loop) | prompt (audience, objectives, features, constraints, outcomes), field names, `max_clarification_rounds` 2 → 3 |
| `research` + `research/*` | structure as-is (planner → parallel Tavily → parallel extractor) | 3 lanes become 3 **domains**, prompts, topics, domain lists, source classifier, evidence vocab, drop patient-story top-up |
| `proposer` | call pattern + id assignment + citation filter | **one call** producing 2–3 `SolutionProposal`s from all evidence (not per lane) |
| `critic` | parallel fan-out + evidence-id filter | fan-out per **proposal**, prompt |
| `judge` | scoring, Python weighted total, routing + loop limits | one call scoring all proposals; `winning_proposal_id`; `domain_status`; rubric keys |
| `evidence_checker` | as-is | verifies the **winning proposal** only; prompt wording |
| `final_report` | pattern only (Python assembles facts, LLM writes narrative) | **replaced** by `brief_writer` (section 4) |
| `completion` | as-is | persists brief + plan + runtime instead of the health report; runs at the real end (after preview) |
| `chat.py` tools, researcher, skills, knowledge, memory, triggers | kept as platform capabilities | re-pointed at the builder (section 7); not on the main path until M11 |

### 3.2 Concept mapping (old → new)
| Old (health) | New (app builder) |
|---|---|
| `is_health_concern` | `is_app_request` (idea for an app, website, tool, service) |
| `condition_name` / `condition_category` | `project_name` / `project_category` ∈ {web_app, website, mobile_app, saas, internal_tool, api_service, ai_agent, game, other} |
| `case_summary` | `idea_summary` |
| `health_profile` | `project_profile` (audience, platform, timeline, budget, team, existing assets) |
| `symptoms` | `requested_features` |
| `constraints` | `constraints` (tech preferences, budget, compliance, hosting, deadlines) |
| `red_flags` / `withdrawn_red_flags` | `risk_flags` / `withdrawn_risk_flags` (legal, privacy, safety, payments, minors…); informational only, **no routing effect** |
| lanes `research / doctor / patient` | domains `apps / papers / tech` (`DOMAINS`, `DOMAIN_LABELS`) |
| `ResearchTopic` (routine, diet…) | apps: `existing_solutions`, `user_complaints`, `must_have_features`, `pricing_and_adoption` · papers: `problem_background`, `established_approaches`, `known_limitations` · tech: `libraries_and_frameworks`, `apis_and_integrations`, `architecture_patterns`, `feasibility_and_risks` |
| `SourceType` | `review_site`, `app_store`, `community_discussion`, `product_docs`, `research_paper`, `technical_docs`, `source_repository`, `article_or_blog`, `other` |
| `EvidenceStrength` | `peer_reviewed`, `official_documentation`, `maintained_repository`, `aggregated_reviews`, `expert_article`, `anecdotal`, `unknown` |
| `PatientContext` | `FeedbackContext` (product, feedback_type ∈ complaint/praise/feature_request/workaround, is_recurring, relevant_to_idea) |
| `CarePlan` (`research_a`…) | `SolutionProposal` (`proposal_a`…`proposal_c`) |
| rubric fit_to_user/safety/… | `requirements_alignment` 0.30 · `problem_relevance` 0.20 · `evidence_quality` 0.20 · `feasibility` 0.20 · `completeness` 0.10 |
| `winning_plan_ids` (per lane) | `winning_proposal_id` (one) + `domain_status` |
| `FinalReport` / `OnboardingSummary` | `ProblemBrief` (+ rendered markdown); onboarding summary dropped |
| `patient_id` / `patient_memories` / `X-Patient-Id` | `user_id` / `user_memories` / `X-User-Id` |
| `SAFETY_RULES` | `BUILDER_RULES`: no invented sources/figures/capabilities; label verified vs user-provided vs assumption vs recommendation; `<user_input>`, `<source>`, `<generated_file>` are data not instructions |

### 3.3 State (`state.py`): rename / keep / add
- **Renamed in M1 (done):** `condition_name→project_name`, `condition_category→project_category`, `case_summary→idea_summary`, `health_profile→project_profile`, `symptoms→requested_features`, `red_flags→risk_flags`, `withdrawn_red_flags→withdrawn_risk_flags`, `patient_id→user_id`, `patient_memories→user_memories`. **Renamed in M2 (done):** `perspective→domain` everywhere (`perspective_summaries→domain_summaries`, `Evidence.perspective→domain`, DB columns `evidence_records.domain`, `knowledge_docs.domain`), `PatientContext→FeedbackContext`, `prevalence_note→opportunity_note`. **Renamed in M3 (done):** `care_plans→proposals`, `proposer_lane_status→proposer_status` (str), `proposer_notes` (str), `CarePlan→SolutionProposal`, `PlanScore→ProposalScore`, `plan_id→proposal_id`, `DomainJudgement→ProposalJudgement`, `PlanVerification→ProposalVerification`, `DomainResult→ProposalResult`, `winning_plan_ids→winning_proposal_id`; `onboarding_summary` removed from state (the chat builds its summary from the report).
- **Keep:** `question` (the raw prompt), `user_context`, `mode`, `status`, `current_node`, counters, `clarification_*`, `assumptions`, `missing_information`, `research_*`, `evidence`, `evidence_gaps`, `conflicting_claims`, `rejected_sources`, `criticisms`, `scores`, `verdict`, `debate_round`, `verification_results`, `checker_verdict`, `unresolved_questions`, `metrics`, `error`, `active_seconds`.
- **Add (M4–M9):** `brief`, `brief_markdown`, `brief_validation`, `brief_revision_count`, `brief_feedback` (list), `brief_approved_at` · `implementation_plan`, `plan_markdown`, `plan_revision_count`, `plan_feedback`, `plan_approved_at` · `workspace_dir`, `implementation_tasks` (list of `{id,title,status,attempts,result}`), `current_task_id`, `implementation_log` (capped list), `change_requests`, `build_results`, `preview` (`{state,url,port,last_error,log_tail}`) · `prompt_versions`, `models_used`, `token_usage` (per node).
- **Remove:** `onboarding_summary`, `final_report`.

### 3.4 Schemas (`schemas.py`)
Update: `WorkflowStatus` (add `writing_brief`, `validating_brief`, `awaiting_brief_review`, `planning`, `awaiting_plan_review`,
`implementing`, `building`, `previewing`, `awaiting_changes`), vocabularies above, `IntakeResult`, `ClarificationResult`, `SearchQuery`,
`ResearchPlan` (every domain covered), `Evidence`, `ExtractedEvidence`, `ExtractionResult` (summary of what the domain says about the
problem / alternatives / feasibility), `ProposedSolution`/`SolutionProposal`, `ProposerOutput`, `CriticismCategory`
(`unsupported_claim`, `contradicts_evidence`, `copies_existing_app`, `missing_requirement`, `infeasible`, `security_privacy_risk`,
`weak_assumption`, `scope_too_large`, `better_alternative`), `PerspectiveJudgement→ProposalJudgement`, `Verdict`.
New: `ProblemBrief` (sections 4.1–4.10, every claim item carries `label ∈ verified|research_backed|user_provided|recommendation|assumption`
and `evidence_ids`; `references` are **assembled by Python** from cited ids), `BriefValidation`, `FeedbackRouting`, `ImplementationPlan`
(phases → tasks with `id`, `depends_on`, `files`, `acceptance_criteria`, `verify_commands`), `TaskResult`, `BuildResults`, `PreviewStatus`.
Keep the rules at the top of `schemas.py` (required lists, limits in descriptions, cross-field validators).

### 3.5 Routing conditions (`graph.py`)
Keep `route_after_clarification`, `route_after_judge` (decision names unchanged), `route_after_evidence_checker` (→ `brief_writer`
instead of `final_report`), `guarded`. Remove `skips_double_check` / quick-mode node skipping (the builder always runs critic + checker).
Add: `route_after_brief_validator`, `route_after_brief_review`, `route_after_plan_review`, `route_after_implementer` (self-loop while
tasks remain), `route_after_build_check`, `route_after_change_request`. Hard guard: `implementer` is reachable only when
`brief_approved_at` and `plan_approved_at` are set (checked in the route, not only in the UI).

### 3.6 Config (`config.py`)
Rubric keys/weights as above; `max_clarification_rounds=3`; new: `planner_model="claude-opus-5-5"`, `implementer_model="claude-sonnet-5-5"`,
`max_brief_revisions=2`, `max_review_rounds=6`, `max_plan_revisions=3`, `max_task_attempts=2`, `max_build_fix_rounds=2`,
`task_timeout_seconds`, `command_timeout_seconds=120`, `install_timeout_seconds=600`, `preview_port_range="4100-4199"`,
`preview_idle_minutes=30`, `session_token_budget`, `session_usd_budget`, `generated_projects_dir`. Remove patient-lane and check-in settings.
Startup check: the configured planner/implementer models must appear in `client.models.list()`; otherwise log a warning and fall back to
`anthropic_model` (never silently assume a model exists).

---

## 4. Target graph

```
START → intake → clarification ⇄ await_clarification
            │
            ▼
        research (apps · papers · tech) ◄───────────────────────────────────────────┐
            ▼                                                                       │
        proposer → critic → judge ──(request_more_research)─────────────────────────┤
                              ├──(request_clarification)──► clarification           │
                              ▼ proceed / insufficient_evidence                     │
                        evidence_checker ──(material gap, loops allowed)────────────┘
                              ▼
                        brief_writer ◄──────────────(revise, ≤ max_brief_revisions)──┐
                              ▼                                                      │
                        brief_validator ──(clarify: requirement gap)──► clarification│
                              ▼ ok                                                   │
                        await_brief_review ──(request_changes: wording)──────────────┘
                              │   ├──(requirements)──► clarification
                              │   ├──(research)──────► research       (research_focus = feedback)
                              │   └──(proposal)──────► proposer       (feedback as criticism)
                              ▼ approve
                        planner (Opus 5.5) ◄──(request_changes)── await_plan_review
                              ▼                                       ▲
                        await_plan_review ─────────────────────────────┘
                              ▼ approve
                        implementer (Sonnet 5.5, ONE task per step) ──(tasks left)──► implementer
                              ▼ all tasks done / failure cap
                        build_check ──(fails, ≤ max_build_fix_rounds)──► implementer (fix task)
                              ▼
                        preview (start dev server, health check)
                              ▼
                        await_change_request ──(change)──► implementer (change task)
                              │               ├──(replan)──► brief_writer → brief review → planner (extension)
                              ▼ finish
                        completion → END
```

| Node | Kind | Model | Writes (owner) |
|---|---|---|---|
| `brief_writer` | LLM (1 call) + Python assembly | default | `brief`, `brief_markdown`, `brief_revision_count` |
| `brief_validator` | Python checks + LLM (1 call) | default (Haiku acceptable later) | `brief_validation`, `unresolved_questions`, `status` |
| `await_brief_review` | human pause | — | `brief_feedback`, `brief_approved_at`, routing hint |
| `planner` | LLM (1 call, large output, streaming) | `claude-opus-5-5` | `implementation_plan`, `plan_markdown`, `plan_revision_count`, `implementation_tasks` (derived) |
| `await_plan_review` | human pause | — | `plan_feedback`, `plan_approved_at` |
| `implementer` | coding agent for **one task**, then Python runs `verify_commands` | `claude-sonnet-5-5` | `implementation_tasks[i]`, `current_task_id`, `implementation_log`, `token_usage` |
| `build_check` | Python only (install / test / build in sandbox) | — | `build_results` |
| `preview` | Python only (process manager + HTTP health check) | — | `preview` |
| `await_change_request` | human pause | — | `change_requests`, new task(s) |

---

## 5. Human pauses: clarification and approvals

Mechanics (same for every pause; proven by `await_clarification`):
1. A dedicated `await_*` node calls `interrupt(payload)`; **no LLM call in that node** (LangGraph re-runs the node from its first line on resume).
2. The payload carries `type` and everything the UI needs to render (questions / brief markdown / plan markdown / preview status).
3. The API exposes it as `pending` on `GET /api/decisions/{id}`; the client answers with `POST /resume` whose body is a discriminated union on `type`; the API checks `type` matches, the node re-validates and re-interrupts with `error` on bad input.
4. The reply is stored in state (feedback, approval timestamp); a pure-Python `route_after_*` reads it.
5. Checkpoints make every pause survive restarts; `{"type":"continue"}` resumes an interrupted run.

| Pause `type` | Payload | Resume body | Routes to |
|---|---|---|---|
| `clarification` (exists) | `questions`, `round` | `{answers}` | `clarification` |
| `brief_review` | `brief_markdown`, `brief`, `validation_summary`, `unresolved_questions`, `round` | `{action: approve \| request_changes, feedback, target: auto \| requirements \| research \| proposal \| wording}` | approve → `planner`; `auto` → small `FeedbackRouting` LLM call picks the target; else the named node |
| `plan_review` | `plan_markdown`, `plan`, `round` | `{action: approve \| request_changes, feedback}` | approve → `implementer`; changes → `planner` |
| `change_request` | `preview`, `build_results`, task summary | `{action: change \| replan \| finish, request}` | change → `implementer` (new task C<n>); replan → `brief_writer` (brief first, M10) → brief review → `planner` (extension); finish → `completion` |
| (finished) `reopen` | — (`DecisionStatus.reopen_actions`) | `{type: reopen, action: change \| replan, request}` | written as an `await_change_request` reply, then the same routes as above (M10) |

Rules: implementation never starts before **both** approvals (route guard); every revision is re-validated before it is shown again;
user-driven loops are bounded by `max_review_rounds` (then only wording edits are accepted); each approval records what was approved
(hash of the markdown) so a later edit invalidates the approval.

---

## 6. Session isolation and execution

**Layout** (`generated_projects/` is git-ignored; `session_id = thread_id`):
```
generated_projects/<thread_id>/
├── app/        # the generated project; the ONLY directory the coding agent and commands may touch
└── .builder/   # brief.md, plan.json, tasks.json, logs/<task>.log, runtime.json (pid, port, started_at), agent-session ids
```
**Modules (new, `backend/src/ai_decision_arena/workspace/`):**
- `paths.py`: `safe_path(session_dir, relative)` — resolves symlinks, rejects anything outside `app/`, `..`, `~`, absolute paths outside; unit-tested against traversal and symlink escape.
- `sandbox.py`: `run(session_dir, argv, timeout, env)` — `cwd=app/`, **scrubbed env** (minimal `PATH`, `HOME=<session>/.builder/home`, no `ANTHROPIC_*`, `TAVILY_*`, `LANGSMITH_*`, `DATABASE_URL`), executable allowlist (`npm npx pnpm node python python3 uv pip pytest git ls cat mkdir cp mv rm`), per-call timeout, output cap (20 kB), new process group, kill on timeout; returns `{argv, exit_code, stdout_tail, stderr_tail, duration}`; the LLM never sets these fields.
- `processes.py`: dev-server registry (`project_runtimes` table): allocate a port from `preview_port_range`, start with `PORT` injected, health-check `http://127.0.0.1:<port>/` (any HTTP answer within 60 s), stop (process group), restart, idle cleanup trigger.
- `agent.py` (M8): the coding agent adapter — see section 8 / M8 for the decision between Claude Agent SDK and an own tool loop. Either way: cwd pinned to `app/`, path guard + command policy enforced in a pre-tool hook, max turns / time / tokens per task, the agent's own settings and the user's Claude Code config are **not** loaded, generated files are treated as untrusted content.
**Policy:** no secrets are written into `app/` (generated apps that need keys get a `.env.example`); no `git push`, `npm publish`, `sudo`, `docker`, `curl | sh`, process signals to unknown pids; destructive operations outside the task's files require a user approval pause (reuse `change_request`-style interrupt) or are denied.
**Preview:** the frontend iframes `http://localhost:<port>`; the backend reports `preview.state ∈ starting|ready|failed|stopped`, `url`, `last_error`, `log_tail`; `preview.ready` is set only after a successful health check.
**As built in M7 (2026-10-25), differences from the plan above:**
- `run(ws, command, timeout=, env=)`: `command` is a plan string (full `command_problems` check incl. shell operators)
  or an argv list (no shell anywhere, so `;` inside `python3 -c "a; b"` is allowed; every other check applies).
  Arguments naming an existing path must stay inside `app/` after symlinks. Never raises for the command's failure:
  `CommandResult` (`ok`, `exit_code`, `refused`, `timed_out`, tails, duration); `ok` is the only success signal.
- PATH = `app/node_modules/.bin` + `generated_projects/.shared/bin` (symlinks to the allowlisted tools found on the
  builder's PATH **minus the builder's own virtualenv**) + `/usr/bin:/bin`. Env vars: HOME/TMPDIR in `.builder/`,
  `CI=1`, `npm_config_prefix` in the session (no global installs on the host), `PIP_REQUIRE_VIRTUALENV=1`,
  `GIT_CEILING_DIRECTORIES=generated_projects` (git in `app/` would otherwise find **ai-lab-2's own repo**),
  package caches shared under `.shared/` (`share_package_cache=true`; npm/uv/pip caches are integrity-checked).
  Extra env names that look like secrets are refused (`ValueError`).
- Dev servers: `ProcessManager.start(ws, command)` replaces `{port}` (Vite ignores `$PORT`:
  `npm run dev -- --port {port} --strictPort`), injects `PORT`, logs to `.builder/logs/dev-server.log`, and returns
  `ready` only after an HTTP answer on 127.0.0.1/::1 (any status) or `failed` with the exit code / timeout + log tail.
  Registry: `project_runtimes` (`DbRuntimeStore`; `MemoryRuntimeStore` when `PERSIST_RESULTS=false` / tests), mirrored in
  `.builder/runtime.json`; a partial unique index keeps one active runtime per port. Dev servers are **not** stopped at
  API shutdown: `reconcile()` at startup adopts those whose pid AND start time match (so `--reload` keeps previews),
  marks the rest failed, and kills sandbox commands whose **owner** builder process died (`.builder/run/<pid>.json`).
  `stop_idle()` exists; the trigger that calls it comes with M9 (previews) / M11 (triggers).
- **Not contained on the host (v1), by design until M12:** memory / CPU limits, network access, and what a project's
  own scripts run (`npm test` executes `package.json` scripts, which can call any program). The allowlist gates the
  top-level command only. What v1 does guarantee: no builder secrets in the env, cwd + paths, process groups,
  timeouts, output caps, audit log.

**Coding agent as built in M8 (`workspace/agent.py`, 2026-10-25):** Claude Agent SDK `claude-agent-sdk` 0.2.174 (it runs
its own bundled Claude Code CLI 2.1.310, not the user's install). `cwd=app/`, `model=implementer_model`,
`effort=implementer_effort`, system prompt = the `claude_code` preset + our `SYSTEM_APPEND` (nodes/implementer.py),
`tools=[Read, Write, Edit, Glob, Grep]` + in-process MCP tool `run_command` (→ `sandbox.run`), `permission_mode="dontAsk"`,
PreToolUse hook = `paths.tool_path_problem` (absolute paths must resolve inside app/, relative ones via `safe_path`, Glob
patterns may not climb out), `setting_sources=[]`, `skills=[]`, `CLAUDE_CONFIG_DIR=.builder/claude-config`,
`max_turns` / `max_budget_usd` / wall-clock timeout per attempt, log `.builder/logs/<task>.log`. **Why no built-in Bash:**
the SDK merges `env` OVER the builder's environment, so the CLI subprocess (and its Bash) would see `DATABASE_URL`,
Tavily/LangSmith keys; our MCP tool runs commands in the sandbox's env-from-nothing instead (and those names are also
emptied in the CLI's env).

**v2 (M12, optional):** run each session's commands and dev server in a Docker container (`node:22` / `python:3.13`, only the session dir mounted, memory/CPU/pids limits) — the Docker daemon must be running; v1 uses host subprocesses with the controls above.

---

## 7. Platform capabilities (for the builder itself, not for generated apps)

| Area | Exists | Improve / introduce (milestone) |
|---|---|---|
| **10.1 Hallucination prevention** | Python-owned evidence ids/URLs, quote check, id filtering, critic/judge/checker, assumptions list, unresolved questions | Claim labels + Python-assembled references in the brief; validator rejects unknown ids and unlabelled claims; build/test/preview facts come only from subprocess exit codes and HTTP checks; "not verified" shown in UI (M4, M9, M10) |
| **10.2 Prompt rot** | Prompts inline in nodes, shared blocks in `prompting.py` | `prompts/` registry: one module per agent with `VERSION`, owner, changelog; `prompt_versions` recorded per session; eval cases per agent in `backend/evals/<agent>/*.json` + `scripts/run_evals.py`; rule: change a prompt → bump version → run its cases (M11) |
| **10.3 Prompt management** | XML-tag separation of user input / evidence / instructions | Registry above; system prompts stable for prompt caching (`cache_control` on the system block via `ChatAnthropic`); structured outputs everywhere (already); one place for shared rules (`BUILDER_RULES`) (M1, M11) |
| **10.4 Tool management** | Chat tools with Pydantic schemas, bounded rounds, `<source>` wrapping, `handle_tool_error` | Tool registry (research, workspace, sandbox, preview, knowledge, memory) with schemas, permission boundaries (path guard, allowlist, network only for package installs), timeouts/retries, `tool_calls` log table + LangSmith (M7, M8, M11) |
| **10.5 Skills & subagents** | `skills/` loader, research sub-agent, lane fan-out | Builder skills (`nextjs-app`, `fastapi-service`, `testing`, `ui-basics`); subagents: `researcher` (exists), `reviewer` (before a task is marked done), `debugger` (on failing verify); spawn only on review/failure, capped; task ownership in `implementation_tasks` (M8, M11) |
| **10.6 Memory** | STM = state + Postgres checkpoint; LTM = `patient_memories` per browser id; context trimming | Rename to `user_memories` (preferences like preferred stack); approved brief/plan versions in `project_artifacts`; invalidate on re-approval; cap `implementation_log` and summarize old tool results; scope every read by `user_id` + `thread_id` (M1, M8, M11) |
| **10.7 Guardrails** | Data-not-instruction tags, `SecretStr`, loop caps, time budget, model fallback, forget-me endpoint, container sandbox for the backend | Workspace path guard, command policy, env scrub, process limits, approval pause for destructive ops, security event log, no secrets in generated code, generated files untrusted in prompts (M7, M8) |
| **10.8 Triggers / events** | Routing functions, interrupts, `GraphRunner`, check-in scheduler | Explicit transition table (section 4 + 5); scheduler repurposed: stop idle previews, clean orphan processes on startup (M9, M11) |
| **10.9 Prompting strategy** | Roles, structured schemas, reasoning-first judge, few-shot queries | `BUILDER_RULES`; per-task context only (task + plan excerpt + brief excerpt + file list); stop/escalate rules in implementer; regression cases (M1, M8, M11) |
| **10.10 Knowledge** | `knowledge_docs` (FTS) with curated docs + session evidence | Curated builder docs (stack cheat-sheets with sources) replace health docs; session evidence kept per `thread_id`; freshness = `retrieved_at` shown; no vector DB until a measured need (M11) |
| **10.11 Evaluation / observability / cost** | LangSmith traces, metrics at completion, progress lines; **M11 part 1:** `usage_log` per node run (tokens + USD from `usage_metadata` × `pricing.PRICES`), `session_llm_budget_usd` stops automatic loops, `usage_events` + `GET /api/metrics` (per node / day / model, node failures), `GET /usage` per session | eval runner + E2E regression script (M11 part 3) |

---

## 8. Milestones (do in order; each ends with its verify script green, then the user commits)

Conventions: `uv run pytest` must stay green after every milestone; real-API checks live in `backend/scripts/verify_mN.py` and print
`PASS`/`FAIL`; API contract changes land in `frontend/src/lib/api/types.ts` in the same milestone; `handoff.md` progress log updated.
Each milestone ends with its **Commit:** line, the short commit message the user uses (`M<N>: <what>`).
**Standard test idea:** "A simple calculator web app" — the smallest buildable project. Every live verify script uses it
(plus one richer idea where the questions must adapt); the M8/M9 end-to-end builds target it first, bigger ideas after.

### M0 — Test harness + baseline (no product change) ✅ done 2026-10-24
- Add dev deps: `pytest`, `httpx`; `backend/tests/conftest.py` with a **fake `call_structured`** fixture (returns canned schema instances per schema type) and an `InMemorySaver` graph fixture.
- Tests: graph compiles with the expected nodes; routing functions; `limits.loops_allowed`; `sources.normalize_url/classify_source`; API smoke with `TestClient` (lifespan patched to use `InMemorySaver`, `PERSIST_RESULTS=false`).
- `backend/scripts/verify_m0.sh`: `uv run pytest -q`, `cd frontend && npm run lint && npx tsc --noEmit`.
- Document ports 8001/3001 in README/handoff. **Verify:** script green. **Done when:** ≥ 8 tests pass without network.
- **Commit:** `M0: test harness and verify script`

### M1 — Vocabulary + intake + clarification for app ideas ✅ done 2026-10-24
- Rename state fields / schemas / config per 3.2–3.6 (one commit-sized change); `BUILDER_RULES`; new intake prompt + `IntakeResult`; clarification prompt (first round 4–6 questions: audience, objective, core features, constraints/platform/budget/timeline, success outcomes; later rounds only on material change; dedupe), `max_clarification_rounds=3`.
- Alembic migration: rename columns (`condition_*→project_*`, `red_flags→risk_flags`, `patient_id→user_id`), table `patient_memories→user_memories`; API header `X-User-Id`; frontend types/wording for these fields.
- **Verify:** pytest (fake LLM: non-app input rejected, 3-round cap, dedupe) + `scripts/verify_m1.py` runs real intake + first clarification round for 2 prompts and prints the questions (cheap).
- **Commit:** `M1: app-builder vocabulary, intake and clarification`

### M2 — Research in three domains ✅ done 2026-10-24
- `DOMAINS=(apps, papers, tech)`, labels, topics, Tavily steering lists in `sources.py` (apps: g2, capterra, producthunt, trustpilot, app stores, reddit, HN; papers: arxiv, acm, ieee, springer, sciencedirect, semanticscholar; tech: github, stackoverflow, mdn, npm, pypi, framework docs), `classify_source`, planner prompt + `_ensure_required_topics` (≥1 `user_complaints`, `established_approaches`, `feasibility_and_risks`), extractor prompt + `FeedbackContext`, remove patient-story top-up.
- **Verify:** pytest (classifier, required-topic fix-up, dedupe) + `scripts/verify_m2.py`: real research pass for one idea; asserts every evidence URL came from a Tavily hit, every domain has queries, summaries present.
- **Commit:** `M2: research in three domains`

### M3 — Proposer, critic, judge, evidence checker for solutions ✅ done 2026-10-24
- `SolutionProposal` + prompts; proposer single call (2–3 proposals, ids `proposal_a..c`, citation filter); critic per proposal in parallel (new categories incl. `copies_existing_app`); judge single call + rubric + `winning_proposal_id` + `domain_status` + unchanged routing; checker on the winner.
- **Verify:** pytest routing with fakes (proceed / more research / clarification / insufficient, caps) + `scripts/verify_m3.py` runs the debate on the cached M2 state.
- **Commit:** `M3: solution proposals, critic and judge`

### M4 — Brief writer + validator ✅ done 2026-10-25
Spec: `docs/app-builder-spec.md` §4 (the document) and §5 (validation). Inputs: the clarified requirements, the evidence, the
winning proposal + alternatives, the Critic / Judge / Checker outputs (all in state after `final_report`). Cached test state:
`backend/.cache/debate_calculator.json` (written by `verify_m3.py`).

**The brief's sections, in this order (spec §4.1–4.10).** Every item carries `label ∈ verified | research_backed |
user_provided | recommendation | assumption` and `evidence_ids`; the LLM cites ids only, **Python renders the references**.
1. **Project overview** — proposed name (if any), concise description, intended users / stakeholders / audience, the domain and context of the problem.
2. **Problem statement** — the specific problem or unmet need; who experiences it and in what context; the current process / existing alternatives / how users cope today; the gap between the current situation and the desired outcome; practical consequences of leaving it unresolved; supporting evidence or measurable indicators when available. Specific, concise, **solution-neutral** (describe the problem before assuming a feature or technology is the answer).
3. **Research findings and evidence** — the most relevant findings from existing apps and user feedback; from papers and technical literature; from feasibility analysis, open-source implementations and technical docs; limitations of existing solutions and the opportunity to improve; citations for important claims; evidence gaps clearly flagged.
4. **Proposed solution** — how the recommended app addresses the problem; main capabilities and user-facing features; the key user journey; MVP features vs future enhancements; why this approach beats the alternatives considered.
5. **Functional and non-functional requirements** — functional requirements; non-functional (performance, security, privacy, reliability, accessibility, scalability); integrations, data inputs/outputs, user roles where applicable; measurable / testable acceptance criteria for critical requirements when there is enough information.
6. **Proposed architecture and technology** — high-level architecture and major components; responsibilities of frontend, backend, database, external services, AI/agent components as applicable; how components communicate and how data flows; technologies recommended from evidence, feasibility and the user's constraints; key decisions and trade-offs; **unverified technology choices are never presented as mandatory**.
7. **Scope and deliverables** — what the initial implementation includes; exclusions / out of scope; expected deliverables (application, backend services, integrations, documentation); dependencies on external services, datasets, APIs, infrastructure.
8. **Success criteria** — measurable outcomes that show the problem is solved (task completion rate, time saved, error reduction, adoption, reliability, model performance… as relevant); target values and evaluation methods only when justified by evidence or the user's requirements; **never invent numerical targets without a baseline** (a criterion may have `target = null`, `basis = none`).
9. **Constraints, assumptions and risks** — technical, financial, regulatory, resource, timeline constraints; confirmed requirements separated from assumptions; unresolved questions and dependencies; the main implementation / security / privacy / operational risks with mitigations.
10. **References** — the most relevant sources for the problem, the solution and the architecture; prefer authoritative / primary sources; claims linked to sources; research findings distinguished from agent recommendations. **Assembled by Python** from the evidence ids used in sections 1–9 (title, URL, domain, verification status).
Length: about one page. Prioritise problem, evidence, solution, essential features, architecture, success criteria; detailed requirements or references that do not fit go to a short **appendix** (same document, rendered after the main part).

**Validator (spec §5): nine checks**, each `{check_id, passed, severity, issue, fix_instruction}`:
1. the problem is clearly stated and consistent with the clarified requirements;
2. the solution addresses the identified problem rather than merely copying existing apps;
3. major recommendations are supported by research or explicitly labelled as assumptions;
4. features and architecture are technically plausible within the known constraints;
5. the scope distinguishes essential (MVP) functionality from optional enhancements;
6. success criteria are measurable where possible and contain no fabricated targets;
7. important risks, dependencies and unresolved questions are disclosed;
8. research claims have supporting sources wherever possible;
9. the document is concise, internally consistent, and understandable to technical and non-technical readers.
Deterministic Python checks run **before** the LLM call and fail hard: every `evidence_ids` entry exists; every `verified` /
`research_backed` item has ≥ 1 evidence id; a success criterion with a numeric target must have `basis ∈ user_requirement |
evidence`; all ten sections present; word budget respected. Verdict ∈ `approve | revise | clarify`.
Routing (`route_after_brief_validator`): approve → `await_brief_review` (M5; until then → `completion`); revise → `brief_writer`
with the validation feedback, at most `max_brief_revisions` (=2) times, then proceed with the open issues listed as unresolved;
clarify (critical information missing or a material contradiction) → `clarification` when a round is left (spec §5 last paragraph),
else proceed flagged.
- Build: `ProblemBrief` + `BriefValidation` schemas, `brief_writer` node (Python facts → one LLM call → `render_brief_markdown`),
  `brief_validator` node, state fields `brief`, `brief_markdown`, `brief_validation`, `brief_revision_count`, `unresolved_questions`,
  `WorkflowStatus` + `writing_brief` / `validating_brief`, graph wiring after `final_report`, `GET /api/decisions/{id}/brief`,
  `types.ts`, a read-only `BriefView` (markdown) in the admin session page. `final_report` stays as the data step before the brief.
- **Verify:** pytest (deterministic checks, revision cap, clarify route, references assembled from ids only) +
  `scripts/verify_m4.py` on `backend/.cache/debate_calculator.json` (2–3 Claude calls): prints the markdown, asserts all ten
  sections, every cited id exists, no URL in the brief that is not in the evidence, ≤ ~900 words before the appendix.
- **Commit:** `M4: problem brief writer and validator`

### M5 — Brief review pause + API + admin UI ✅ done 2026-10-25
Spec §6: show the document in a readable format; ask the user to confirm it describes the problem and the intended solution;
an **explicit accept option plus a text field** for changes or additions; feedback goes to the appropriate node and the document is
updated; **revalidate before showing it again**; repeat until the user explicitly accepts. A misunderstanding of the requirements →
`clarification`; a research or proposal quality issue → `research` / `proposer`; wording → `brief_writer`. **No planning or code
generation before approval** (spec §12: brief approval and plan approval are separate checkpoints).
- `await_brief_review`, `FeedbackRouting`, resume union `BriefReviewResume`, `project_artifacts` table, `types.ts`, `BriefReviewPanel` in `DecisionView`, stepper stages.
- **Verify:** pytest API tests (wrong type → 409, approve → planner next, request_changes targets) + `scripts/api_flow.py --auto` extended to approve the brief.
- **Commit:** `M5: brief review pause and API`

### M6 — Planner (Opus 5.5) + plan review pause ✅ done 2026-10-25
Spec §7: a Claude-Code-style implementation plan on `claude-opus-5-5` (availability checked at startup, never assumed), based on
the approved brief: phases, milestones and actionable tasks; project structure, dependencies, architecture, APIs, frontend
components, backend services, database design, integrations; AI models / agents / tools / workflows only where the project needs
them; testing strategy, acceptance criteria and expected outputs per major task; task dependencies and execution order; risks and
technical decisions to settle before implementation. Detailed enough that the implementer never has to make a major architectural
decision or contradict the approved brief. Presented for approval; revised on request.
- `call_structured(..., model=...)` parameter; `ImplementationPlan` + Python checks (unique ids, DAG, allowlisted commands); planner prompt; `render_plan_markdown`; `await_plan_review`; API + UI panel; model availability check at startup.
- **Verify:** pytest (DAG/command checks, revision cap, guard "no implementer without both approvals") + `scripts/verify_m6.py` on a cached approved brief (one Opus call).
- **Commit:** `M6: Opus planner and plan review`

### M7 — Workspace, sandbox, processes ✅ done 2026-10-25
- `workspace/paths.py`, `sandbox.py`, `processes.py`, `project_runtimes` table, `generated_projects/` in `.gitignore`, orphan cleanup at startup.
- **Verify:** pytest (traversal, symlink escape, env scrub, timeout kill, output cap, allowlist) + `scripts/verify_m7.py`: creates a workspace, runs `npm init -y`, starts a tiny static server, health-checks, stops.
- **Commit:** `M7: session workspace and sandbox`

### M8 — Implementer (coding agent, one task per step) ✅ done 2026-10-25
Spec §8: implement on `claude-sonnet-5-5` according to the approved plan; use tools, skills and subagents where they improve
quality; manageable tasks with tracked progress; validate through automated tests, error handling, linting and quality checks;
fix issues **before** marking a task complete; stay aligned with the approved brief and plan; accept user instructions through
the chat during implementation; apply changes without overwriting working code; keep a clear record of progress and unresolved
issues; **report genuine progress and test results only** (a build, test, install or preview counts as successful only when the
operation itself confirmed it: exit codes and HTTP checks, never the model's say-so).
- **Spike first (≤ 1 h):** Claude Agent SDK (`claude-agent-sdk` 0.2.x on PyPI, needs the installed Claude Code CLI) with `cwd=app/`, `model="claude-sonnet-5-5"`, built-in Read/Write/Edit/Bash/Glob/Grep, a `PreToolUse` hook enforcing section 6, `max_turns`, no settings sources loaded. Fallback if the spike fails any of: cwd/hook enforcement, API-key auth from `.env`, usage/cost reporting, independence from the user's Claude Code config → own loop with `stream_with_tools` + 5 tools (`read_file`, `write_file`, `edit_file`, `list_files`, `run_command`).
- `implementer` node: picks the next ready task, runs the agent with task + plan/brief excerpts + file list, then Python runs `verify_commands`; status/attempts; self-loop edge; `max_task_attempts`; budget caps; progress lines; `.builder/tasks.json`.
- **Verify:** pytest with a fake agent (task bookkeeping, attempts, caps) + `scripts/verify_m8.py`: trivial plan (static page + one test) implemented end to end; verify commands pass for real.
- **Commit:** `M8: implementer coding agent`

### M9 — Build check, preview, change requests, completion ✅ done 2026-10-25
Spec §9 (preview + isolation): run the generated app in an isolated environment; show it in a preview panel; refresh it when
changes are applied; show useful build / runtime errors when it fails to start. Each session has a unique id and its own
`generated_projects/<session>/` folder with source, configuration, dependencies and artifacts; generated code never modifies the
builder; sessions cannot touch each other's files or runtime; conversation, approved brief, plan and execution state stay
associated with the session; sessions can be resumed; file access, terminal commands, package installation and execution are
restricted to the session's environment; resource usage and processes are managed so one project cannot disrupt another.
- `build_check` (install/test/build from `plan.commands`), `preview` (processes.py), `await_change_request`, routing, `GET /api/decisions/{id}/preview` (+ `restart`, `stop`), `GET /implementation` (tasks + log tail), completion persists brief/plan/runtime, `types.ts`.
- **Verify:** pytest (routes, fix-round cap, preview ready only after health check) + `scripts/verify_m9.py`: full pipeline `--auto` on a tiny idea; `curl` of the preview URL returns HTTP 200.
- **Commit:** `M9: build check, preview and change requests`

### M10 — Lovable UI ✅ done 2026-10-25
Spec §9 (interface): left = the conversation (initial prompt, clarification answers, document review, plan approval, change
requests), context and progress preserved through the session; right = the live preview of the running app.
- `/` and `/c/[id]`: left = chat (prompt → questions → stage chips → brief card with Approve / Request changes + target → plan card → task progress → change composer), right = `PreviewPane` (iframe, state chip, errors, refresh/restart). `/admin` keeps the detailed view with new stages. Remove health wording, update `pipeline.ts`, `chatStages.ts`, `format.ts`, layout metadata.
- **Verify:** `npm run lint`, `tsc --noEmit`, `next build`; manual checklist in the progress log (new idea → answer → approve brief → approve plan → preview visible → one change request applied).
- **As built (user's answers 2026-10-25: open question 4 = full pipeline, 3 = keep the chat as "Ask" mode):**
  `/` = NewProject (prompt, example chips, recent projects); `/c/<id>` = BuilderView: left `ChatPane` (stage chips,
  first message, clarification one question at a time, research summary, then reviews / change requests / Ask
  messages in time order, then the live area: working chip + newest progress line, `BuildProgressCard` while
  building, `BriefReviewCard` / `PlanReviewCard` (Approve buttons + "read it" → right tab; changes are typed in the
  message box), `AppRunningCard` (Finish), finished note); right `WorkPane` tabs Preview (`PreviewPane`: browser
  bar with state dot, URL, reload, phone width, new tab, Start/Restart; iframe reloads when `started_at` changes;
  failed → dev server error + log; stopped → Start) · Brief (`BriefView`) · Plan (`PlanView defaultOpen`) · Build
  (`BuildCard` + `TaskList`) · Activity (`NowPanel` + `ActivityFeed`). The tab follows the project (brief review →
  Brief, plan review → Plan, building → Build, built → Preview, else Activity) until the user picks one; the choice
  holds until the suggestion changes. One message box whose modes depend on the pause: answer (+ Skip) · Change the
  brief (target select in the card) · Change the plan · "Request some change in app" (one coding-agent task C<n>) /
  "Plan a bigger change" (replan: the planner rewrites the plan for approval) · "Ask about app" (from the report on);
  mode chips have hover hints. Labels chosen by the user after the browser check (2026-10-25). Light
  theme (reuses the admin cards). **Resizable split** (user's request): drag the border (`ResizeHandle`) to set the
  chat width (320–900 px, the preview keeps ≥ 420 px and fills the rest), remembered in localStorage
  (`builder:chatWidth`, read with `useSyncExternalStore`, server snapshot null = default 400 / 440 px), double-click
  resets, arrow keys ±24 px. **Download code** (user's request; button right of the tabs, enabled once built and
  while the builder is not running): Chrome / Edge → folder picker (File System Access API), the project is written
  into a NEW subfolder `<project-slug>/` (confirm before overwriting an existing one; every path re-checked in the
  browser: no `/`, `..`, `\`, `:`); other browsers → `<project-slug>.zip`. Backend `workspace/export.py`:
  `GET /code` (JSON, base64) and `GET /code.zip`; only `app/`, without node_modules / dist / .next / coverage / .git /
  caches / venvs, `.env*` except `.env.example`, symlinks; 5 MB per file, 50 MB total. The result popup says where
  it was saved, how to run it (plan install + dev commands) and what was left out. Mobile: Chat | Preview switch. Projects drawer from the top bar (all sessions,
  intake-rejected ones hidden). Old `components/chat/*` and `useStartChat` deleted. Admin: "Open in the builder"
  link, nav "Builder", `RiskFlagBanner` (informational, replaces the emergency wording), "Feedback context",
  "Project facts".
  Backend: `GET /api/chats/{id}` adds `reviews` (brief + plan replies with `at`, replans from the change pause shown
  only as change turns) and `changes` (with the `C<n>` task + status, matched via `delivery.change_task_title`);
  `DecisionStatus.has_build`; Ask context (`chat.build_context`) adds `<current_stage>`, `<brief>`, `<plan>` (no task
  descriptions), `<build>` (measured facts only), `<user_requests>`; prompt: answers only, never claims a change;
  chat tools without `load_skill`, researcher / tool prompts re-pointed at app projects; knowledge search excludes
  curated (health) docs; new sessions from the UI are `mode: "full"`.
  **Reopen (added after the user's browser check, open question 6):** a finished, built project takes another change
  or a new plan: `POST /resume {"type": "reopen", "action": "change" | "replan", "request"}` (409 unless finished; 422
  unless the action is in `DecisionStatus.reopen_actions` = `delivery.reopen_actions(state)`: built, finished at the
  change pause, same limits as the pause). The API writes `delivery.reopen_update` (a new `change_requests` entry,
  `reopened: true`) with `graph.update_state(..., as_node="await_change_request")` and continues the run: the router
  makes task C<n> (or replans) exactly like an answered pause; completion runs again at the next Finish (its saves are
  upserts). UI: after Finish the message box offers "Ask about app" (default, so a question never reopens by
  accident) / "Request some change in app" / "Plan a bigger change"; the finished note says so; Ask's prompt knows a change reopens the project.
- **Commit:** `M10: Lovable UI with live preview` (pushed by the user as `1a8c0c7` "Frontend UI with live preview.")

### M11 — Platform hardening (prompts, evals, cost, knowledge, memory, triggers, skills)
Spec §10.1–10.11 (platform-level requirements; section 7 of this file maps each one to what exists and what to add). They apply to
the builder itself, **not** to every generated app: a generated project gets only the AI infrastructure its approved requirements need.
- `prompts/` registry + versions in state/DB; `backend/evals/` cases + `scripts/run_evals.py`; `token_usage`/USD per node + session budget + `/metrics`; `tool_calls` log; curated builder knowledge docs + builder skills (replace health ones); `user_memories`; idle-preview trigger (replaces check-ins); `chat.py` re-pointed as "ask about this project" (optional).
- **Verify:** pytest + `scripts/run_evals.py` (fake-LLM cases offline; real cases behind `--live`).
- **Commit:** `M11: platform hardening`
- **Done in parts** (agreed way of working: each part verified, then the user commits it):
  - **Part 1 — cost + usage ✅ 2026-10-25** (commit `M11.1: cost and usage tracking`). `pricing.py`: `PRICES` per
    model ($/MTok input, output, cache read, cache write 5 m = 1.25× input, 1 h = 2× input; Haiku 5.5's > 100K-token
    tier; `PRICES_AS_OF` 2026-10-06 from the claude-api reference), `tokens_from_langchain` (langchain's
    `input_tokens` INCLUDES cache tokens: subtracted), `tokens_from_anthropic` (raw usage excludes them), `cost_usd`
    (unknown model → $0 + flagged "unpriced", never guessed). `usage.py`: `UsageMeter` in a ContextVar (worker threads
    of a node copy it; a lock guards the shared object), `record()`, `metering()`. `llm._call_structured` records
    EVERY attempt that got a response (retries, truncations, the fallback model: all billed). `wrap_node` meters each
    node run → ONE `usage_log` entry `{node, at, seconds, calls, failed_calls, models, input/output/cache tokens,
    cost_usd, unpriced_models, error?}` (also when the node failed) + a `usage_events` row (best effort, PERSIST only).
    The coding agent is NOT metered there (its Agent-SDK cost stays in `implementation_log`: one source per cost).
    Ask: each streamed round (and the researcher sub-agent's) is recorded in `ToolContext.meter` (the stream's
    generator runs across threadpool steps, so the meter travels in the context object, not the ContextVar) → one
    `usage_events` row "ask" per reply. Budget: `session_llm_budget_usd=5` → `loops_allowed` blocks research /
    debate / clarification loops (user-driven steps still run). `usage.session_cost(state)`: totals, per stage
    (node → Clarification / Research / Proposals / Brief / Plan / Build), first build, each change request (=
    everything between that reply and the next reply at the change pause, incl. a replan's brief + plan + new tasks),
    steps. API: `GET /api/decisions/{id}/usage` (+ `ask_usd` from usage_events, budgets, `prices_as_of`,
    `llm_measured_since` = null for sessions from before M11), `GET /api/metrics?days=7` (usage_events totals / by
    node / by day / calls per model / node failures + the coding agent's spend from completed sessions'
    `decision_sessions.metrics`), `ChangeTurn.cost_usd`, completion metrics `llm_cost_usd`, `llm_calls`. UI: Cost card
    in the Build tab (`components/session/CostCard.tsx`: builder AI / coding agent / Ask / **Total so far**; **Limits for
    this project** with "$x left of $y" bars: builder AI $5 = no more AUTOMATIC research / clarification loops, coding
    agent $15 = no new task attempt starts, pending tasks → skipped; an attempt already running may overshoot by up to
    its own $2 cap; both limits count the whole project incl. every change; the chat's app card shows "Total cost so
    far"), both limits are set in `backend/.env` (`IMPLEMENTATION_BUDGET_USD=15`, `SESSION_LLM_BUDGET_USD=5`, also
    documented in `.env.example`); settings are cached per process, so restart the API after changing them
    (`--reload` watches .py files, not .env), "Change request N · cost $x" in the chat, "Coding agent, all
    tasks $x" instead of the ambiguous "Agent cost". `frontend/scripts/shot_tab.mjs <url> <tab> <png>` = screenshot +
    text of one builder tab.
  - Part 2 — `tool_calls` log (agent hook decisions + sandbox commands → table, `/api/metrics` failure counters).
  - Part 3 — prompt registry (VERSION + changelog, versions per session) + eval cases + `run_evals.py`; prompt caching.
  - Part 4 — builder knowledge docs + skills, idle trigger, removal of the quick profile and health leftovers, M10
    leftovers; then the first brand-new idea end to end (~$2–3, ask first).

### M12 — Optional: Docker runtime per session, session list/resume polish, cleanup CLI
- **Verify:** `scripts/verify_m12.py` runs one session's dev server in a container (requires the Docker daemon).
- **Commit:** `M12: Docker runtime per session`

---

## 9. Tests and validation checkpoints per phase

| Phase | Offline tests (pytest, fake LLM) | Live check (script, real API) |
|---|---|---|
| Clarification (M1) | non-app rejection, round cap, no repeated questions, merged facts | questions for 2 prompts look specific |
| Research (M2) | classifier, required topics, URL de-dupe, no evidence without hits | URLs ⊆ Tavily hits; 3 domains covered |
| Proposal / evaluation (M3) | citation filtering, winner selection, all 4 judge decisions, loop caps | debate on cached state ends with a winner |
| Brief + validation (M4–M5) | unknown ids rejected, unlabelled claims rejected, revision cap, clarify route, API 409/422 paths | brief ≈ 1 page, references all resolvable |
| Planning (M6) | DAG/ids/commands checks, approval guard | Opus plan parses and passes checks |
| Workspace (M7) | traversal, symlink, env scrub, timeout, allowlist | server starts, health OK, stops |
| Implementation (M8) | task state machine, attempts, budget | trivial plan implemented, verify commands pass |
| Preview (M9) | ready only after health check, fix-round cap | HTTP 200 from preview URL |
| UI (M10) | lint, tsc, build | manual E2E checklist |
| Platform (M11) | prompt registry, cost math (test_usage: prices, token split, meter in threads, every retry billed, node entry on failure, budget, attribution, /usage), eval runner | verify_m11 (token split = API usage, node cost = tokens × price, usage_events, Ask metered, /usage sums, page); eval cases pass |

---

## 10. Preserving existing functionality and integrating safely

- The original health app keeps running untouched in `/Users/dev/pro/ai-lab` (own repo, DB `ai_decision_arena`, ports 8000/3000). ai-lab-2 replaces the health concept **by design**; what we preserve is the platform mechanics (section 2.4), checked by pytest after every milestone.
- One milestone per commit; `uv run pytest` and the frontend `lint` + `tsc` must be green before the user commits.
- State/DB renames happen once (M1) with an Alembic migration (downgrade provided) and a verify script; no further renames later.
- API paths stay `/api/decisions/...` (renaming to `/api/projects` is cosmetic; only if we ever want it, last).
- Every API model change is mirrored in `types.ts` in the same milestone; `pending.type` stays a discriminated union so the UI can only render what the backend sends.
- New nodes are added after the judge; existing routing names (`proceed`, `request_more_research`, `request_clarification`, `insufficient_evidence`) are kept.
- Python keeps the final say on loops, approvals, file paths, commands, and "did it build" facts.

---

## 11. How to run (ai-lab-2 on 8001/3001, side by side with ai-lab)
```bash
# backend (terminal 1)
cd backend
uv sync                                   # first time
uv run alembic upgrade head               # after new migrations
FRONTEND_URL=http://localhost:3001 uv run uvicorn ai_decision_arena.api.main:app --reload --port 8001

# frontend (terminal 2)
cd frontend
npm install                               # first time
NEXT_PUBLIC_API_URL=http://localhost:8001 npx next dev -p 3001     # http://localhost:3001

# checks
cd backend && uv run pytest -q            # from M0
uv run python scripts/check_env.py        # keys work
```
**Live checks and what they cost** (real APIs; run long ones in the background with `python -u ... > /tmp/x.log 2>&1`).
Costs marked "measured" come from the agent's `ResultMessage` or (since M11) from `usage_log` / `GET /usage`; the
others are rough guesses from before M11 (re-measure them when you next run them, and replace the guess here):

| Script | Needs | Writes | Cost / time |
|---|---|---|---|
| `verify_m1.py` intake + clarification | — | — | cents (guess), < 1 min |
| `verify_m2.py` research | — | — | Tavily + cents (guess), ~1 min |
| `verify_m3.py` debate (`--fresh` = redo research) | research cache, else runs research | `.cache/research_calculator.json`, `.cache/debate_calculator.json` | ~$0.2–0.5 (guess), 2–4 min |
| `verify_m4.py` brief writer + validator | debate cache | `.cache/brief_calculator.json` | ~$0.2 (guess), ~2 min |
| `verify_m5.py` brief review | brief cache | — (artifact row in DB) | ~$0.1 (guess), ~2 min |
| `verify_m6.py` Opus plan | brief cache | `.cache/plan_calculator.json` | ~$0.5 (guess), ~4 min |
| `verify_m7.py` workspace / sandbox / processes | — | — | free, seconds |
| `verify_m8.py` coding agent, 2-task plan | plan cache | a workspace | $0.05 measured, ~30 s |
| `verify_m9.py` build / preview / change | plan cache | a workspace + project_runtimes row | $0.09–0.10 measured, ~1 min |
| `verify_m10.py [--session id] [--ask] [--skip-build]` builder UI (35 checks incl. real resize drags and Download-code clicks via `frontend/scripts/check_resize.mjs` / `check_download.mjs`) | dev servers on 8001/3001, one built session, Chrome for the DOM / drag checks | (`--ask`: 2 chat messages in that session) | free (`--ask`: cents, 1 Sonnet call), ~1 min incl. `next build` |
| `verify_m11.py [--session id]` cost + usage: token split vs the API's own usage, intake + clarification metered, one Ask reply metered (throwaway thread id), `/usage` sums, `/api/metrics`, Cost card on the page | dev servers on 8001/3001, one built session, Chrome | 3 `usage_events` rows under `verify-m11-<hex>` (not the reference project) | measured ~$0.08 (intake $0.008, clarification $0.012, Ask $0.055), ~1 min |
| `fake_api.py` offline API (port 8002) for UI work | nothing (fake LLM / search / agent from tests/conftest.py, in-memory everything) | a throwaway tmp generated-projects folder | free; a full session in seconds |
| `api_flow.py --auto [--change "..."]` full E2E over HTTP | dev servers on 8001/3001 | a real session | agent $0.74 measured + research/brief/plan LLM calls (unmetered, guess $1–2); ~15 min active |

**UI work without paying (M10):** `cd backend && uv run python scripts/fake_api.py` (API on 8002), then
`cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8002 npx next build && npx next start -p 3002` (a production server:
a second `next dev` would fight the user's dev server over `.next/dev`). Create a session on 8002, resume its pauses
with curl / httpx, and look at http://localhost:3002/c/<id> (or headless Chrome, section 16). Afterwards run
`verify_m10.py` (it rebuilds `.next` against 8001).

`.cache/` is git-ignored: a fresh clone runs verify_m3 → m4 → m6 once to rebuild the chain. The cached
calculator state carries a CONDITIONAL report (M3's Judge asked for clarification), so sessions built from it end
`completed_with_uncertainty` even when the build is perfect. Verify scripts with `PERSIST_RESULTS` on save their
sessions into the real DB: they show up in `/admin`'s recent sessions (named "A simple calculator web app").

**Generated projects:** `generated_projects/<thread_id>/app` (the project) + `.builder/` (brief.md, plan.md, plan.json,
tasks.json, runtime.json, logs/<task>.log = the agent's tool calls, logs/commands.jsonl = every sandbox command,
logs/dev-server.log). `generated_projects/.shared/` = tool symlinks + npm/uv/pip caches. Safe to delete old session
folders by hand (stop their preview first: `POST /api/decisions/<id>/preview/stop`); no cleanup CLI yet (M12).
Previews keep running after "finish" until the idle stop (30 min without `GET /preview`).

Database: local Postgres `ai_decision_arena_2` (`backend/.env`). Tables: `decision_sessions`, `evidence_records`, `decision_reports`,
`user_feedback`, `chat_messages`, `user_memories`, `knowledge_docs` (its `condition` column is renamed in M11), LangGraph `checkpoint*`,
`project_artifacts` (M5: approved brief / plan versions), `project_runtimes` (M7: one dev server per session),
`usage_events` (M11: one row per node run with model calls + one per Ask reply). Planned: `tool_calls`.

---

## 12. Decisions log
- 2026-10-24: Copied from ai-lab into ai-lab-2; new GitHub repo `github.com/fahadtariqaziz/any-web`.
- 2026-10-24: Root `.gitignore`; `__pycache__`, `backend/.cache/`, generated graph images untracked.
- 2026-10-24: Separate local database `ai_decision_arena_2`; `docker-compose.yml` default DB updated to match.
- 2026-10-24: **Concept decided: Lovable-style AI app builder** (this plan). Health app history kept in `docs/`.
- 2026-10-24: Reuse `intake, clarification, await_clarification, research, proposer, critic, judge, evidence_checker, completion`; replace `final_report` with `brief_writer`; add `brief_validator, await_brief_review, planner, await_plan_review, implementer, build_check, preview, await_change_request`.
- 2026-10-24: Proposals are **not per lane** anymore: one proposer call → 2–3 proposals over all evidence; critic per proposal; one winner.
- 2026-10-24: Risk flags are informational (no emergency routing).
- 2026-10-24: Models: planner `claude-opus-5-5`, implementer `claude-sonnet-5-5`, other agents `ANTHROPIC_MODEL` (Sonnet 5.5), fallback Haiku 5.5. Availability verified; a startup check keeps it honest.
- 2026-10-24: Package name `ai_decision_arena`, API prefix `/api/decisions`, `ArenaState` name kept (no churn).
- 2026-10-24: Quick-mode node skipping removed (builder always runs critic + checker); quick settings may stay as a speed profile.
- 2026-10-24: Generated projects in `generated_projects/<thread_id>/app` (git-ignored); v1 host subprocess sandbox, v2 Docker.
- 2026-10-24: Workflow: Claude builds + verifies with a script per milestone; the **user commits/pushes**.
- 2026-10-24: Standard test idea for every live verify and the first end-to-end builds: **"A simple calculator web app"** (user's call: if the smallest project builds, bigger ones follow).
- 2026-10-24 (M1): risk flags are informational only; `limits.loops_allowed` no longer blocks on them. `max_clarification_rounds` = 3.
- 2026-10-24 (M3): one Proposer call makes 2–3 proposals over ALL evidence; one Critic call per proposal (parallel); one Judge call scores all and Python picks the winner; the checker verifies the winner only. Material contradictions found by the Judge become clarification questions when a round is available. Quick mode runs every node (one proposal, quick settings). The interim `FinalReport` = winner + alternatives (M4 replaces the user-facing document). The chat's first summary is built from the report in Python (no LLM call). Health demo scripts (`run_debate`, `run_report`, `demo_data`, `schemas_demo`) deleted; health report components replaced by `ProposalDetails`.
- 2026-10-25 (M11 part 1): **cost accounting** (section 8, M11 part 1 has the details). Choices: one source per cost
  (builder model calls → `usage_log`; coding agent → the Agent SDK's own `total_cost_usd` in `implementation_log`,
  never re-derived from its tokens); every billed attempt counts (self-correction retries, truncated answers, the
  fallback model); prices live in one table with a date, and an unknown model is flagged, not guessed; the session
  LLM budget ($5) only stops AUTOMATIC loops, never a step the user asked for; per-change cost is attributed by time
  window between replies at the change pause (1-second `at` resolution is fine for humans; fast offline tests may
  tie, so tests check membership, not exact splits); `usage_events` is best effort (the checkpoint stays the truth;
  `/api/metrics` is for trends). M11 is done in parts, each committed by the user (`M11.1`, `M11.2`, ...).
- 2026-10-25 (M10): **bigger changes go through the brief, and a plan for a built app only adds work** (user's
  answer after the browser check: "Plan a bigger change: make it scientific calculator as well" came back as plan v2
  WITHOUT the feature, because the approved brief lists scientific mode as out of scope, and approving it would have
  reset all tasks to pending and rebuilt the app from T1, possibly losing C1/C2). Now: replan (at the change pause or
  via reopen) → `brief_feedback` entry (source `change_request`, target wording) + both approvals cleared →
  `brief_writer` in "user" mode (the prompt moves an added capability into the MVP / in-scope lists) → validator →
  brief review → approve → planner in **extension mode** whenever a `built_part` exists (plan tasks no longer pending):
  output `PlanExtension` (only new tasks, ids after the highest built id, depends_on / feature_coverage may cite built
  ids; inputs `<built_plan>`, `<built_tasks>`, `<later_changes>` (C / F tasks), `<project_files>`,
  `<requested_change>`), validated MERGED (`plan.extension_schema_for` → `merge_extension` → full ImplementationPlan
  checks + MVP coverage), stored as a normal ImplementationPlan; built tasks (and C / F tasks) keep their status, new
  ones are pending; the markdown marks built tasks and says "N new tasks"; plan review payload `new_task_count`. The
  First live run (user, session `e39ceeb5`, "make it scientific calculator as well"): brief draft 3 put scientific
  mode in the MVP, but listed the percent key and themes as out of scope / later although C1 (dark theme) and C2
  (percent) were built → every agent now sees `<changes_built_after_approval>` (done C-task requests, in the user's
  words; `prompting.built_changes_block` inside `<user_input>`), the writer must keep them in scope and label what they
  state user_provided (first only the writer had them, and the validator then flagged the percent rule's "you said"
  label as unsupported); the extension planner gets
  them as `<later_changes>`. Second live finding: the user's correction ("keep percent and theme in scope", target
  auto) was routed by the FeedbackRouting LLM to **proposal**: the debate re-ran (~4 min) and the new brief swapped
  Big.js for Decimal.js, i.e. described a different app than the built one → once `workspace_dir` exists the brief
  review is **wording-only** (`wording_only_reason: "built"`; auto → wording without the routing call; proposal /
  research / requirements refused by the node and the API), and user-mode writer revisions get `<built_app>` (plan
  tech_stack, dependencies, architecture) to keep. The
  session `e39ceeb5` was restored to its checkpoint after C2 (`update_state(<checkpoint fa7a3b58>, {}, as_node="preview")`
  + `invoke(None)`; the history with the faulty plan v2 is kept).
- 2026-10-25 (M10): open question 6 → **finished projects can be reopened** (user's answer after the browser check:
  Ask on a finished calculator could only say "send it in Change mode", which no longer existed). Implemented as a
  `reopen` reply that writes a change request as the `await_change_request` node (`update_state(as_node=...)`), so no
  graph change and the same router / limits / completion. The chat's "reply sent, poll not caught up" state is now
  time-based (`sentAt` vs `useDecision().lastUpdate`, like the admin view's `resuming`), because a finished project
  has no pause key.
- 2026-10-25 (M10): open question 4 → the builder UI runs the **full** pipeline (quick profile no longer started; its
  settings stay for old sessions until M11). Open question 3 → the tool chat stays as **Ask mode** beside the builder:
  available once the report exists, at any stage, never changes anything (changes go through the pauses), context =
  case + report + evidence highlights + brief + plan + measured build facts + the user's earlier requests. Ask has no
  skills and no curated knowledge until M11 replaces the health ones. The conversation is assembled from the checkpoint
  (clarification answers, `brief_feedback`, `plan_feedback`, `change_requests`, all with `at`) + `chat_messages`; no new
  table. The builder page is light-themed so the admin cards (BriefView, PlanView, BuildViews, NowPanel, ActivityFeed)
  are reused unchanged. Approve / Finish are buttons in the chat cards; every free-text reply goes through the one
  message box (mode switch).
- 2026-10-25 (M9, after the E2E): **preview isolation**: `port_is_free` first tries to CONNECT on 127.0.0.1 / ::1
  (anything accepting = taken), and `ready` additionally requires `listens_on(pid, port)` (psutil: the started process
  tree holds the LISTEN socket). Reason: macOS lets a SO_REUSEADDR bind to 127.0.0.1:4100 succeed while a Node app
  listens on `*:4100`; a second session got 4100 and its health check was answered by the OTHER session's app (a
  crashed dev server looked "ready"). Frontend: `useDecision` keeps polling every 5 s while paused / interrupted (a
  pause answered elsewhere, e.g. by `api_flow.py` or another tab, used to leave the page stale forever); a finished
  built session shows `AppView` (preview card with Start/Restart, build check, tasks) above the plan; the plan card
  counts plan tasks and shows "+N added later" for F/C tasks. `BuildViews.tsx` holds the shared cards.
- 2026-10-25 (M9): `build_check` runs `plan.commands` install → test → build (stops at the first failure; facts =
  exit codes). Failing + fix round left (`max_build_fix_rounds=2`, reset by every change request) + budget left →
  task `F<n>` (verify = the failing command; the output goes into its description inside `<untrusted>`), back to the
  implementer; otherwise the preview starts anyway and shows the errors. Tasks created after planning (F = fix, C =
  change) carry their own `spec` (a `PlanTask`) in `implementation_tasks`; their commands come from the checked plan,
  never from an LLM. `preview` = `get_manager().start(ws, plan.commands.dev)` (a restart each time: "refresh after
  changes"). One process-wide `ProcessManager` (`processes.get_manager()`), shared by the preview node (graph threads)
  and the API; `IdleStopper` thread in the lifespan (`preview_idle_check_seconds=300`, `preview_idle_minutes=30`;
  `GET /preview` touches). Change requests: `ChangeRequestReply {action: change | replan | finish, request}`,
  `max_change_requests=10` (then finish only); change → task `C<n>` verified by `plan.commands.test` (or build; `ls` only
  if a plan has neither); replan (**superseded in M10: now brief first, then a plan extension**) → `plan_feedback` entry (source change_request) + plan approval cleared → planner →
  plan review again (bounded by `max_plan_revisions`); finish → completion, the preview keeps running until the idle
  stop. Completion: `completed_with_uncertainty` also when the last build check failed or the preview is not ready;
  metrics `build_passed`, `preview_state`, `change_requests`. Statuses `building`, `previewing`, `awaiting_changes`.
  `ProcessManager` uses an RLock and `status()` runs under it (a GET during a stop marked the server "failed").
- 2026-10-25 (M8): **Claude Agent SDK** for the coding agent (user's answer to open question 1), after
  `scripts/spike_agent_sdk.py` passed all hard requirements (13 s, $0.02): hook sees every call and its deny is
  enforced, cwd = app/, no Bash offered, apiKeySource `ANTHROPIC_API_KEY`, cost + usage in `ResultMessage`, user config
  not loaded. Implementer = one task ATTEMPT per graph step (self-loop; every attempt is a checkpoint). Task status is
  set by Python only: `done` iff every verify command exits 0 in the sandbox (the agent's report is recorded, never
  trusted); otherwise `pending` while `attempts < max_task_attempts` (=2; the retry prompt carries the failing output
  as `<untrusted>`), then `failed`; dependants of failed/blocked/skipped tasks → `blocked`; once
  `implementation_budget_usd` (15) is spent the remaining tasks → `skipped`. Per attempt: `implementer_max_turns=40`,
  `implementer_task_budget_usd=2`, `implementer_task_timeout_seconds=900`, `implementer_effort=medium` (the claude-api
  reference recommends starting Sonnet 5.5 at medium for agentic coding). The prompt carries only the task, a plan
  excerpt, a brief excerpt (description, MVP, out of scope), finished task titles and the file list (spec §10.9). The
  implementer node raises unless `plan_is_approved`, and `route_after_plan_review` / `route_after_implementer` check it
  too. Completion: a built session with any task not done → `completed_with_uncertainty`; metrics get task counts +
  cost. Workspace also holds `.builder/brief.md`, `plan.md`, `plan.json`, `tasks.json`. UI: status `implementing`,
  stage "Build" (9 stages), node text; the task list / log view comes with M9's `GET /implementation`.
- 2026-10-25 (M7): `workspace/` package as in section 6 "As built". New dependency `psutil` (process start times:
  pid reuse can never make us kill a stranger). `command_problems(command, shell_operators=True)`: argv lists skip the
  shell-operator check; `--opt=/abs` and `--opt=../x` are now refused (value after `=` is checked like a path).
  Settings: `generated_projects_dir` (repo root), `command_timeout_seconds=120`, `install_timeout_seconds=600` (npm
  install/ci, pnpm install/add, uv sync/add, pip install), `command_output_cap_bytes=20000`, `share_package_cache=true`,
  `preview_port_range=4100-4199`, `preview_health_timeout_seconds=60`, `preview_idle_minutes=30`. The API creates
  `app.state.processes` and runs `reconcile()` at startup. No graph / API / frontend change (M8/M9 consume it).
- 2026-10-25 (M6): `call_structured(model=, effort=, timeout=)`; with `model` set, the fallback chain is [that model, the session's default model]. `effort` goes to `ChatAnthropic(output_config={"effort": ...})`; langchain-anthropic 1.7.6 merges it with the structured-output `format` (checked in its source). Planner settings: `planner_model=claude-opus-5-5`, `planner_effort=high` (Opus 5.5 defaults to medium and cannot disable thinking), `planner_max_tokens=16000` (non-streaming is fine up to ~16k), `planner_timeout_seconds=600`. `llm.resolve_model()` reads `GET /v1/models` once per process: listed → used; not listed → `anthropic_model` with a progress line; list unreadable → kept unchecked (the call's own fallback chain covers it). The API logs the planner / implementer availability at startup (`check_models`). The plan schema fits the strict-output grammar in ONE call (probed). Plan checks live in the schema validators so `call_structured` sends the exact problem back: unique `T<n>` ids, `depends_on` only on EARLIER tasks (order = topological order, so no cycle is possible), known phases, ≥ 1 acceptance criterion and verify command per task, relative file paths, every command passes `schemas.command_problems` (argv only, no shell operators, executable allowlist = the M7 sandbox's, no push/publish, no absolute or `..` paths, no `rm -rf .`). MVP coverage is enforced by `plan.plan_schema_for(mvp_features)`, a runtime subclass named `ImplementationPlan` (the fake LLM handles subclasses via the MRO). Guards: the planner raises unless `brief_is_approved`; `route_after_plan_review` requires `plan_is_approved` (plan hash AND brief hash), the M8 implementer route must use it. Plan review: approve / request_changes (feedback required); after `max_plan_revisions=3` rewrites only approval is accepted (node re-asks, API 422). Approved plans go to `project_artifacts` (kind `plan`). `implementation_tasks` = `{id, title, phase, depends_on, status: pending, attempts: 0, result: null}`. No server-side refusal `fallbacks` parameter (the claude-api reference recommends it for Opus 5.5): our client-side fallback to the default model covers refusals as structured-output failures; revisit when moving off langchain.
- 2026-10-25 (M5): the review pause is split like clarification: `await_brief_review` (interrupt only, validates the reply, re-asks with `error`) + `brief_review_router` (Python; ONE small `FeedbackRouting` LLM call only for `target="auto"`). Routes: wording → `brief_writer` (edits the reviewed draft: `revision_mode` = "user", detected from `current_node == "brief_review_router"`), requirements → `clarification` (+ `research_focus` with the correction), research → `research` (`research_focus` = the feedback), proposal → `proposer`. The user's change requests reach EVERY agent as `<brief_feedback>` inside `<user_input>` (`prompting.user_case_block`, rule in `BUILDER_RULES`): no per-node plumbing. User-driven loops do not consume `research_retry_count`; they are bounded by `max_review_rounds=6`, after which only wording (auto → wording without an LLM call) or approval is accepted (node re-asks; API 422). Approval stores `brief_approved_at` + `brief_approved_hash` (sha256 of the markdown); `route_after_brief_review` only proceeds when `brief_is_approved(state)` (hash matches the current markdown), otherwise back to the pause. The approved version goes to the new `project_artifacts` table (version per thread+kind, unique content hash, failure to save = progress line only, the checkpoint stays the truth); `GET /artifacts`. The brief's draft number now only grows within a session. Quick-mode chat has no review UI yet: it links to the session page (M10 builds the real one).
- 2026-10-25 (M4): the brief writer makes **three** strict structured calls (sections 1–4, then 5–6 and 7–9 in parallel with sections 1–4 as context): the whole brief schema exceeds the API's grammar limit. Python owns: references (from cited ids only), the `verified` label (needs a checker-verified source, else downgraded to `research_backed`), `required_by_user` technology (only with label `user_provided`), the one-page budget (900 words over sections 1–9, labels/citations/URLs not counted): the renderer moves list items beyond per-list caps to the appendix and, while the page is over budget, shrinks the caps level by level (`CAP_LEVELS` 1.0/0.75/0.5/0; floors keep the MVP, scope, user journey, 3 functional requirements, 2 success criteria and 2 risks in the main part); only a brief too long at the smallest caps fails `det_word_budget`. Reason: in the first live run the LLM needed two full rewrites (1561 → 1080 → 1012 words) for length alone. M5 E2E still needed two (1021 → 940 → 861): the writer now aims at 80% of the budget with ≤ ~20-word items, and `det_word_budget` passes up to budget × 1.10 (`WORD_BUDGET_TOLERANCE`, "approximately one page"). Validator: deterministic checks first; if one fails and a revision is left, revise **without** the LLM call; revise also on any high-severity LLM criterion; clarify only when the reviewer says the brief cannot go forward without the user AND `loops_allowed` permits (bumps `research_retry_count`, resets `brief_revision_count`); otherwise approve, listing remaining medium/high failures as open issues (appendix C + `unresolved_questions`, status `completed_with_uncertainty`). Approve currently routes to `completion` (M5 inserts `await_brief_review`). `GET /brief` returns only a draft whose validation verdict is approve and whose `brief_generated_at` matches the brief (no unvalidated draft is ever shown). The brief lives in the checkpoint only; `project_artifacts` (DB) comes with M5.
- 2026-10-24 (M2): the word is **domain** everywhere (code, state, API, DB columns, UI), keys `apps / papers / tech`. Tavily steering is "prefer" for all three (never exclusive); the apps domain searches with `advanced` depth. `SearchQuery` validates that a topic belongs to its domain; each domain's key topic (`user_complaints`, `established_approaches`, `feasibility_and_risks`) is always searched on the first pass (`planner.ensure_key_topics`). Patient-story top-up removed.

## 13. Open questions (for the user; 1, 3, 4, 6 answered 2026-10-25)
1. ~~**Coding agent (M8):** OK to spike the Claude Agent SDK first?~~ **Answered 2026-10-25: yes, use the Claude Agent SDK** (own tool loop stays the fallback if the spike fails a hard requirement).
2. **Preview runtime:** start the Docker daemon for v2 later, or stay on host subprocesses for now? (v1 works without Docker.)
3. ~~**Chat after preview:** keep the tool-using chat (`chat.py`) as "ask about this project", or retire it?~~ **Answered 2026-10-25: keep it as "Ask" mode** (built in M10).
4. ~~**Quick mode / patient chat UI:** retire the "quick" profile entirely in M10?~~ **Answered 2026-10-25: the builder runs the full pipeline**; the quick profile is no longer started (code removal in M11).
6. ~~**Continue a finished project?**~~ **Answered 2026-10-25: yes, "reopen"** (built in M10).
5. Rename LangSmith project from `ai-decision-arena` (shared with ai-lab) to `ai-app-builder`? (one `.env` line)

## 14. Progress log
- 2026-10-24: Project set up as ai-lab-2. `.gitignore` + first push. New DB `ai_decision_arena_2` created, migrated, knowledge docs loaded. `backend/.venv` rebuilt.
- 2026-10-24: Codebase + graph analysed; environment and model availability verified; this plan written (the old health-app handoff lives in git history).
- 2026-10-24: **M0 done.** `pytest` + `httpx` dev deps; `backend/tests/` with a fake `call_structured` (builds valid schema instances from the prompt text) and a fake Tavily search; 48 tests: graph shape + routing, loop limits, URL/source classifier, schema validators, intake/clarification/proposer/judge nodes, full pipeline pause→resume→report on InMemorySaver (full + quick mode + failure path), API start/poll/resume/report/409/422/404 with TestClient on an in-memory graph. `scripts/verify_m0.sh` = pytest + eslint + tsc, all green. README rewritten for the new concept and ports 8001/3001.

- 2026-10-24: **M1 done.** Scripted word-boundary rename across 42 files (backend + frontend); `ProjectCategory`, new `IntakeResult` / `ClarificationResult`; `BUILDER_RULES` replaces `SAFETY_RULES`; intake + clarification prompts rewritten for app ideas (first round 4–6 questions on users/problem, objective, must-have features, platform/constraints, alternatives, success; later rounds only on material change); Alembic `c1a2b3d4e5f6` renames the session columns and `patient_memories→user_memories` (upgrade, `alembic check`, downgrade, upgrade all verified); `X-User-Id` header; `ToolContext.project`; UI labels. Verify: 49 pytest + eslint + tsc green; `scripts/verify_m1.py` (real Claude, calculator + bakery ideas + off-topic rejection) PASS. Leftovers by design: research/proposer/critic/judge/report prompts and `demo_data.py` still health-flavoured (M2/M3), `RedFlagBanner` naming/wording (M10), `knowledge_docs.condition` column (M11).

- 2026-10-24: **M2 done.** Scripted `perspective→domain` rename across 46 files; new `Domain`, `SourceType`, `EvidenceStrength`, `ResearchTopic` (+ `TOPICS_BY_DOMAIN`, `KEY_TOPIC`), `FeedbackContext`; `sources.py` (site lists per domain, host/path classifier for 9 source types), `search.py`, `planner.py` (domain prompt, few-shot, quick plan, key-topic fix-up), `extractor.py` (domain prompt, `opportunity_note`), `nodes/research.py` rewritten; Alembic `d2e3f4a5b6c7` renames the two `perspective` columns (round-trip verified); `tools.web_search` takes a domain; frontend `DOMAIN_META`, source/strength labels, progress parser updated. Verify: 70 pytest (21 new: classifier, key topics, quick plan, budget/order, de-dupe, hit selection, evidence assembly) + eslint + tsc green; `scripts/verify_m2.py` on the calculator idea PASS (9 queries, 45 hits, 22 evidence records: apps 7 / papers 3 / tech 12, every URL from a real hit). Observed: the papers domain is thin for a calculator (expected: little literature), and the extractor labelled two Wikipedia pages `research_paper` / `technical_docs`; acceptable first guesses, revisit source-type guidance in M11 evals.

- 2026-10-24: **M3 done.** New debate schemas (`ProposedSolution`, `SolutionProposal`, `ArchitectureSketch`, `Criticism` as the critic's output, `ProposalScore`, `DomainCoverage`, `ProposalJudgement`, `Verdict` with `winning_proposal_id` / `domain_status` / `material_contradictions`, `ProposalVerification`, `ProposalResult`, interim `FinalReport`); rubric `requirements_alignment 0.30 / problem_relevance 0.20 / evidence_quality 0.20 / feasibility 0.20 / completeness 0.10`; `prompting.py`, `proposer.py`, `critic.py`, `judge.py`, `evidence_checker.py`, `final_report.py`, `chat.py` (project assistant), `graph.py` (no quick-mode skipping) rewritten; API `DebateView` / `Counters.proposals`; frontend `types.ts`, `DebateView`, `ReportView`, new `ProposalDetails`, rubric/labels/wording, chat summary. Verify: 78 pytest + eslint + tsc green; `scripts/verify_m3.py` on the calculator idea PASS: 23 evidence records, 3 proposals (lean static / expression-line PWA / math.js), 5 critic points each with real evidence ids, judge totals 7.8 / 5.6 / 5.0, winner proposal_a, decision `request_clarification` (two material contradictions: "simple" vs overbuilt B/C, "exact decimal" vs 1/3 rounding), checker 10 claims (verified 4 / partially 3 / unavailable 1 ...), report conditional with concrete next steps. Research + debate states cached in `backend/.cache/*_calculator.json` for M4.

- 2026-10-24: Original product spec saved verbatim to `docs/app-builder-spec.md`; M4–M11 milestone blocks now quote the spec
  parts they implement (brief sections 4.1–4.10, the nine validation checks, review rules, planning, implementation, preview
  and isolation, platform requirements). Requested after a new session noticed the spec was missing from the repo.

- 2026-10-25: **M4 done.** New `brief.py` (pure Python: `cited_objects`, `normalize`, `assemble_references`, `render_brief_markdown` with fit-to-page caps, `count_words`, `deterministic_checks`), schemas `BriefItem` / section models / `BriefPartOne|Two|Three` / `BriefContent` / `ProblemBrief` / `BriefReference` / `BriefReview` / `ValidationCheck` / `BriefValidation`, nodes `brief_writer` (3 calls: 1–4, then 5–6 ∥ 7–9) and `brief_validator`, `route_after_brief_validator`, statuses `writing_brief` / `validating_brief`, settings `max_brief_revisions=2` (quick 0) and `brief_word_budget=900`, clarification reads `<brief_questions>`, evidence block shows `checked="..."` after verification, completion → `completed_with_uncertainty` when the brief has open issues. API `GET /api/decisions/{id}/brief` + `has_brief`; frontend types, `getBrief`/`useBrief`, `BriefView` (markdown + validation checks) above the report, stepper stage "Brief", node texts, labels. `scripts/probe_schema.py` (grammar-limit probe), `run_graph.py` prints/saves `brief.md`. Verify: 99 pytest (20 new in `test_brief.py`: references from ids only, label normalisation, rendering + appendix overflow, fit-to-page floors, word count, all six deterministic checks, revise-without-LLM, revision prompt, cap → approve with open issues, high-severity revise, clarify route + loop limits, full pipeline incl. the clarify loop) + eslint + tsc green; `scripts/verify_m4.py` on the cached calculator debate PASS: draft 0 = 955 words (over budget at the smallest caps → one rewrite), draft 1 = 890 words, approve; 18 references all from evidence, no foreign URL, no numeric target, 9 LLM criteria reviewed, 4 medium open issues. First live attempt failed with the grammar-size error (→ 3-part writer); second run needed two rewrites for length alone (→ fit-to-page renderer).

- 2026-10-25: **M5 done.** `nodes/brief_review.py` (`await_brief_review_node`, `brief_review_router_node`, `FeedbackRouting` for auto), `route_after_brief_review` with the `brief_is_approved` hash guard, schemas `BriefReviewReply` / `FeedbackRouting` / `ReviewTarget`, status `awaiting_brief_review`, state `brief_feedback` / `brief_review_round_count` / `brief_review_route` / `brief_approved_at` / `brief_approved_hash`, setting `max_review_rounds=6`, `<brief_feedback>` in every agent's case block, writer `revision_mode` ("user" edits the reviewed draft), Alembic `e3f4a5b6c7d8` (`project_artifacts`; upgrade / check / downgrade / upgrade verified), `repository.save_artifact` / `list_artifacts`, API `BriefReviewResume` (422: no feedback, non-wording after the cap; 409: wrong pause), `GET /artifacts`, `BriefResponse.approved_at` / `review_round`; frontend `BriefReviewPanel` (approve + feedback + target), pending union, NODE_INFO, chat link, ClarificationForm round count fixed (2 → 3); `api_flow.py` reviews the brief (`--auto` approves) and defaults to port 8001; `draw_graph.py` phase 7. Quality fixes from the E2E runs (also M4 code): the artifact save read `thread_id` from the state (never set by the API) → `get_config()`; success-criteria overflow was bulleted table rows → text lines; appendix grouped per main section instead of one heading per list; validator revises on ≥ 2 medium LLM failures (one goes forward as an open issue); the reviewer gets the main-part word count and ignores the appendix for length; writer aims at 80% of the budget, uses the low end of list ranges, no repeats; `det_word_budget` tolerance 10%. Verify: 115 pytest (12 in `test_brief_review.py`, + API round trip / wording-only 422, + appendix and medium-failure tests) + eslint + tsc green. Live: `verify_m4.py` PASS (891 → 889 → 911 words, rewrites for real issues only, final draft 15/15 checks); `verify_m5.py` PASS (auto routing wording / requirements / research all correct; wording change "PlainCalc + dark mode later" applied, revalidated, shown as round 2; approval hash = stored artifact hash, version 1 in `ai_decision_arena_2`); `api_flow.py --auto` against the dev server on 8001: full session clarification → research → debate → brief → review → approve → completed_with_uncertainty, artifact version 1 saved (second run; the first exposed the thread_id bug).

- 2026-10-25: **M5 browser test by the user** (admin view, calculator idea with answers: precedence, 10-entry history, offline PWA): review panel, checks badge, stepper "Brief · Your review" and open-issues callout work. Fixed from the screenshots: (1) the validator's LLM call was truncated at `max_tokens=3500` twice and fell back to Haiku (~1.5 min each) → 7000 tokens + "issue ≤ 2 sentences, fix 1 sentence" in prompt and schema; (2) bold sub-headings directly after a list were swallowed by the last bullet (markdown lazy continuation) → blank lines around every sub-heading (test checks it); (3) a 7th MVP feature moved to the appendix → MVP (8), user journey (7) and in-scope (6) are never moved; (4) admin header / footer / page title still said "Health Decision Arena", "not medical advice", "Patient chat" → AI App Builder wording (the rest of the UI wording stays for M10); (5) the reviewer failed 942 words against 900 although the rule allows 990 → it now gets `<word_limit>` (budget × 1.10). Verify after the fixes: 117 pytest + eslint + tsc green; `verify_m4.py` PASS (first draft 881 words approved, 2 low notes, no truncation).

- 2026-10-25: **M6 done.** `plan.py` (pure Python: `plan_schema_for` MVP-coverage subclass, `render_plan_markdown`, `plan_hash`, `plan_is_approved`, `tasks_from_plan`), `nodes/planner.py` (`planner_node`, `await_plan_review_node`, `plan_review_router_node`), schemas `ImplementationPlan` / `PlanTask` / `PlanPhase` / `FeatureCoverage` / `PlanCommands` / `PlanReviewReply` + `command_problems` / `path_problems` / `ALLOWED_EXECUTABLES`, statuses `planning` / `awaiting_plan_review`, state `implementation_plan` / `plan_markdown` / `plan_revision_count` / `implementation_tasks` / `models_used` / `plan_feedback` / `plan_review_route` / `plan_approved_at` / `plan_approved_hash`, settings `planner_*`, `implementer_model`, `max_plan_revisions=3`; `llm.py` per-call model / effort / timeout + `available_models` / `resolve_model`; API `PlanReviewResume` (422: no feedback, changes after the cap), `GET /plan`, `has_plan`, startup `check_models`; frontend types, `getPlan` / `usePlan`, `PlanReviewPanel`, `PlanView` (collapsed, above the brief), stage "Plan" (8 stages), node texts, chat link; `api_flow.py` reviews the plan (`--auto` approves); `draw_graph.py` phase 8. Verify: 156 pytest (38 new in `test_plan.py`: allowed / refused commands, paths, 11 plan-check cases, MVP coverage, render + tasks, model resolution, planner model / effort / timeout, unapproved-brief guard, revision with previous plan, revision cap, both-hash route guard, plan artifact, startup check) + eslint + tsc green. Live `verify_m6.py` PASS: 14 models listed, `claude-opus-5-5` available and used, plan in 206 s on the first try (no self-correction), 4 phases / 11 tasks (Vite + Vitest; T1 scaffold → engine slices each with its own test file → UI, keyboard, live region → acceptance suite → `npm run build`), all 18 commands pass the sandbox policy, 7/7 MVP features covered, approval hash = stored artifact (version 1). State cached in `backend/.cache/plan_calculator.json` for M7/M8.

- 2026-10-25: **M7 done.** `workspace/paths.py`, `sandbox.py`, `processes.py`; `ProjectRuntime` model + `save_runtime` /
  `get_runtime` / `list_runtimes`; Alembic `f4a5b6c7d8e9` (upgrade / check "No new upgrade operations" / downgrade /
  upgrade verified); settings; `generated_projects/` git-ignored; startup reconcile in the API lifespan. Verify:
  207 pytest (51 new in `test_workspace.py`: session ids, traversal, symlink escapes incl. a prefix-sibling folder,
  option paths, 8 refused commands audited, symlinked argument, env built from nothing (no secret names, not the
  builder's venv), cwd + exit code, timeout kills the whole group, children killed after exit, output tail cap, git
  cannot reach the surrounding repo, dev server ready only after HTTP then stopped and port free, two sessions two ports,
  crash → failed with output, no HTTP → killed, refused dev command, restart, dead server noticed, idle stop, ports run
  out, reconcile adopt / lost, orphan killed but not a reused pid, a live owner's command left alone, a server being
  started elsewhere not failed) 8× in a row without a flake + eslint + tsc green. Live `verify_m7.py` PASS 3× (24 checks):
  `npm init -y` 0.5 s; 4 refused commands; the builder has `ANTHROPIC_API_KEY` but the sandboxed node sees 20 variables,
  none secret; `git status` in `app/` → 128 "not a git repository" although `generated_projects/` is inside ai-lab-2's
  repo; a hanging node killed at 2 s; two `npm start` servers ready in 0.3–0.4 s on 4100 / 4101, HTTP 200 with their own
  page, `project_runtimes` rows ready; a new manager adopts both; stop frees both ports; audit log 8 commands. Bug found
  on the way: the dev API's `--reload` re-ran `reconcile()` mid-verify and SIGTERMed the verify's live command (2 of 4
  runs) → run files carry the owner process; reproduced on purpose afterwards (worker 97632 → 97771 mid-command): the
  command ran to its own timeout.

- 2026-10-25: **M8 done.** Spike `scripts/spike_agent_sdk.py` PASS (see decisions). `workspace/agent.py` (SDK adapter,
  `AgentRun`), `paths.tool_path_problem`, `nodes/implementer.py` (`implementer_node`, `pick_next_task`, prompt,
  verify, records), `route_after_implementer`, graph wiring (plan approved → implementer → completion), state
  `workspace_dir` / `current_task_id` / `implementation_log` / `implementation_cost_usd`, status `implementing`, settings
  `implementer_*` / `implementation_budget_usd` / `max_task_attempts`, completion status + metrics, `draw_graph.py`
  phase 9, frontend stage "Build" + node text + status label; dependency `claude-agent-sdk`. Verify: 218 pytest (11 new
  in `test_implementer.py`: dependency order, transitive blocking, safety net, file-tool guard incl. symlink / other
  session / .builder / Glob, task-by-task build with real `ls` verify, prompt context, "agent says ok but verify fails →
  failed + dependant blocked", retry with failing output passes, session budget skip, refusal without both approvals,
  route) + eslint + tsc green. Live `verify_m8.py` PASS 3× in a row on a trivial 2-task plan (static calculator page +
  node:test, no package download) from the cached approved calculator brief: both tasks done on the first attempt
  (5 turns each, ~10 s each, $0.05–0.06 per session), every verify command re-run independently afterwards passes, no
  denied call, no API key in app/, ai-lab-2's `git status` unchanged. The agent ran the verify commands itself before
  finishing (log). NOT yet tried: the full 11-task Opus calculator plan (Vite + Vitest, `npm install` from the
  network) — natural first run for M9's end-to-end check.

- 2026-10-25: **M9 built.** `nodes/delivery.py` (4 nodes), routes `route_after_build_check` /
  `route_after_change_request` (implementer now → build_check), `implementer.task_spec` / `add_task` / `next_task_id`,
  `processes.get_manager` / `set_manager` / `IdleStopper`, settings `max_build_fix_rounds` / `max_change_requests` /
  `preview_idle_check_seconds`, state `build_results` / `build_fix_round` / `preview` / `change_requests` /
  `change_route`, API (`ImplementationResponse`, `PreviewResponse`, `ChangeRequestResume`, 3 endpoints + restart),
  frontend types / client / `ChangeRequestPanel` / stage "Preview" (10 stages) / 4 node texts / 3 status labels,
  `api_flow.py` (change-request pause: own GET of the preview URL, `--change`, exit 1 unless every preview GET was
  200), `draw_graph.py` phase 10. Verify: 228 pytest (10 new in `test_delivery.py`: preview after a passing build with a
  real server, failing build → fix task that fixes it, fix-round cap then preview, change → C1 + rebuild + restarted
  preview, replan → planner with the request + new approval, change cap, empty change refused, broken dev server
  reported with its own output, route, idle stopper; test_api now walks implementation → preview (real GET 200) →
  restart → finish) + eslint + tsc green. Live `verify_m9.py` PASS 2× (real agent, real server, real DB; tiny 2-task
  plan, no package download): tasks done first attempt, build passed, preview ready on 4100, our GET 200 with the
  page, `project_runtimes` row ready; change "add a footer" → C1 done, build 2 passed, preview restarted (new pid),
  our GET shows the footer; finish; no key in app/; repo untouched; 41 s and $0.09–0.10 per run.
  Found on the way: the stop/status race above (test_idle_stopper caught it).

- 2026-10-25: **M9 full E2E PASS** (`api_flow.py --auto --change "Add a dark theme toggle ..."` against the dev
  servers on 8001/3001, session `e39ceeb5`): clarification 2 rounds, 45 sources, 3 proposals, 10 claims checked, brief
  approved (14/15 checks), Opus plan 4 phases / 12 tasks (vanilla JS, hand-written recursive-descent parser, vendored
  Big.js, node:test) in 222 s; the agent built **12/12 tasks on the first attempt** (5–10 turns, $0.03–0.11 each);
  build check 1 (`npm install` incl. big.js from the network, `npm test`, `npm run build`) passed; preview ready on
  4100, our GET 200; change → C1 done first attempt (14 turns, $0.08, `src/theme.js` + `tests/theme.test.js`), build
  check 2 passed, preview restarted, GET 200; finish. Agent cost $0.74 total; build phase ≈ 5 min. Independent
  re-check afterwards: the served page contains the `theme-toggle` button (aria-label, aria-pressed); our own
  `npm test` in the sandbox → 85/85 pass. Status `completed_with_uncertainty` comes from the research report
  (`is_conditional`: a thin domain or unverified winner claims), not from the build (build passed, 13/13 tasks done).
  The user's screenshots showed two UI problems (stale page while another client resumed; "13 tasks" counting the
  change task; a finished session hid the built app) → fixed (decisions). Re-running the tests while the E2E app
  still held 4100 exposed the preview isolation bug → fixed + regression test
  (`test_a_foreign_wildcard_listener_is_never_mistaken_for_our_preview`). After the fixes: 229 pytest 3× green,
  eslint + tsc green, `verify_m9.py` PASS again (chose 4101 because 4100 was taken).

- 2026-10-25: **M10 done.** New `frontend/src/components/builder/` (14 files, see 2.3 and the M10 block), routes `/`
  and `/c/<id>` rewritten, old chat components deleted; admin wording / links; backend transcript `reviews` / `changes`,
  `has_build`, Ask context + prompts, curated-knowledge filter, `change_task_title`; `scripts/verify_m10.py`,
  `scripts/fake_api.py`. Verify: 230 pytest (new: the transcript of a session with a wording change, approvals, one
  change request and finish, in order with C1 done; `build_context` contains brief / plan / build / requests; Ask
  409 before the report) + eslint + tsc + `next build` green. `verify_m10.py --ask` on the M9 E2E session `e39ceeb5`
  PASS 25/25: API contract, 4 pages 200, rendered DOM (first message, change request + "C1 done", stage chips, five
  tabs, Ask box, approvals, admin → builder link, home), Ask answer streamed in 1.4 s and saved. A manual Ask
  question on the same session answered from the measured build facts (12 + C1 done, build round 2 passed, preview
  on 4100), said what it could not know (how the toggle works), and refused "make the buttons bigger" pointing to
  Change mode. Offline walk-through with `fake_api.py` + headless-Chrome screenshots at every pause (question 1 of
  2 with Skip; brief card + Brief tab; wording change + Ask in the timeline; plan card + Plan tab; app running with
  a REAL dev server in the iframe; after the change: "C1 done", round 2). Fixed from the screenshots: lower-case
  project names, stage chips wrapping, a green tick on "completed with uncertainty".
  Later the same day, at the user's request: renamed modes ("Ask about app", "Request some change in app", "Plan a
  bigger change" + hover hints) and the resizable chat | preview split (verify_m10 30/30 with real drags: 440 → 843 px
  across the iframe, clamps 320 / 900, survives reload, double-click reset).
  Then "Download code" (user's request): 233 pytest (export: source + vendor kept, node_modules / dist / .git /
  __pycache__ / .env / .env.local / symlinked file and folder left out, zip has one top-level folder; API: /code and
  /code.zip on a built session, 409 before a build); verify_m10 35/35: real click in folder mode wrote the
  calculator's 34 files (69,654 bytes, every name and size equal to `app/`, nothing else), zip mode downloaded
  `simple-calculator-web-app.zip` with the same names.
  Then the bigger-change fix (decisions): 234 pytest (`test_bigger_change_updates_the_brief_first_then_plans_only_the_new_work`:
  replan → brief writer edits with the request → brief review → PlanExtension with built plan / tasks / real file
  list → tasks {T1, T2 done, T3 pending}, plan review `new_task_count` 1 → only T3 run by the agent → build + preview;
  `test_a_plan_extension_must_merge_into_a_valid_plan`: reused ids, unknown dependency, missing MVP feature refused;
  API: reopened bigger change → brief review → plan review); verify_m10 35/35. Not yet run live (brief revision
  ~$0.2 + Opus extension ~$0.5 + the new tasks).
  **Browser checklist for the user (needs a full paid run, ~$2–3):** at http://localhost:3001 type a new idea →
  answer the questions one by one in the chat → the right pane shows Activity while the agents work → brief card:
  read it in the Brief tab, try one change request (e.g. wording), then Approve → plan card + Plan tab → Approve and
  build → Build tab with tasks ticking, build progress card in the chat → Preview tab shows the app → type one
  change in "Request some change in app" → after it: "C<n> done", the preview reloads with the change → try "Ask about
  app" → "Plan a bigger change" (brief → plan extension) → Download code → Finish → Reopen with a change.
  Also: the projects drawer (top-left), phone width (Chat | Preview switch), the admin "Open in the builder" link.
  **User's browser check (same day), session `e39ceeb5`:** Ask answered "tell me short about our problem statement"
  correctly and, asked to add a percent feature, said percent was out of scope of the approved brief, proposed rules
  and refused to claim a change, but pointed at a reopen that did not exist → **Reopen** built (decisions). Verify
  after it: 232 pytest (2 new: reopen change → C1 → build → preview → paused → finish → replan → plan review 2; the
  limit and not-finished refusals) + eslint + tsc + `next build`; `verify_m10.py` 23/23; offline walk-through
  (finished: Ask / Change the app / New plan, note; reopened: "Change request 2", C1 done, round 3). **Live on
  `e39ceeb5` with the user's percent request:** reopened, C2 done on the first attempt (38 turns, $0.21; session agent
  total $0.95), build check 3 passed, preview restarted on 4100 in 70 s. Independent re-check: the served page has
  a `data-action="percent"` key; sandbox `npm test` 95/95 (was 85); `calculate(tokenize(...))`: 430-20% = 344,
  430+20% = 516, 50*20% = 10, 20% = 0.2, 50/20% = 250; keys `430-20%=` through the app's reducer → 344.

- 2026-10-25: **M10 live end to end on the reference project `e39ceeb5` (user in the browser) — "make it scientific
  calculator as well" via Plan a bigger change:** brief draft 3 (scientific in scope; percent / theme wrongly out of
  scope → built-changes fix) → user correction misrouted to proposal (→ wording-only-after-build fix) → draft 6 (Big.js,
  percent + theme in scope, scientific in MVP) approved → Opus **plan extension: 10 new tasks T13–T22 on 12 built**,
  approved → the agent built only T13–T22, all on the first attempt, **$1.08** (project agent total $2.04: first build
  $0.66, C1 $0.08, C2 $0.21) → build check 4 passed → preview restarted with Basic / Scientific, DEG / RAD, ±, ( ).
  Independent re-check in the sandbox: `npm test` 180 tests, 176 pass, 0 fail, 4 skipped (T13's table tests skipped
  "needs parentheses", never un-skipped; the same rows pass in scientific.test.js); `calculate(tokenize(...))`:
  sin(30°)=0.5, sin(180°)=0, cos(90°)=0, tan(90°)=Error, sin(π÷6) rad=0.5, (1+2)×3=9, 2^3^2=512, −2^2=−4, ln(e)=1,
  log(1000)=3, √16=4, √(−4)=Error, 0.1+0.2=0.3, 430−20%=344, 50×20%=10, 8÷0=Error; initial state basic / deg. Also
  verified with the user: Download code into `/Users/dev/Documents/lovablecode` (34 files byte-identical, checked
  read-only with shasum). M10 pushed as `1a8c0c7`.

- 2026-10-25: **M11 part 1 — cost + usage.** Offline: 244 pytest (10 new in `test_usage.py`: langchain/raw token
  split, prices incl. Haiku's long-prompt tier and an unpriced model, meter across ContextThreadPoolExecutor threads,
  a truncated + a valid attempt both billed, node entry also on failure and none for a pause node, LLM budget blocks
  loops, attribution to stages / first build / change / replan, a pre-M11 session, `/usage` over the API after a
  build + reopened change) + eslint + tsc + `next build`; Alembic upgrade / check / downgrade / upgrade clean.
  **Live `verify_m11.py`: PASS** — raw call: derived tokens = the API's usage (18 in / 4 out, 0 cache); intake 1 call
  2,349 in / 336 out **$0.0081**, clarification 1 call 3,891 in / 441 out **$0.0122** (= tokens × Sonnet 5.5 price),
  rows in `usage_events`; one Ask reply on the reference calculator's state (throwaway thread) **$0.0548**; `/usage` of
  `e39ceeb5`: total $2.04 = agent $2.04 (builder AI not measured: the project predates M11), first build $0.66 +
  C1 $0.08 + C2 $0.21 + scientific $1.08 (the same numbers as answered by hand last session); `/api/metrics` counts
  the 3 rows; the Build tab's Cost card shows "$2.04 so far" (headless Chrome, screenshot checked by eye).

## 15. How to work on this repo (the loop every milestone follows)

1. **Start:** follow "Start here" at the top. Read the milestone block in section 8 (it quotes the spec parts it needs;
   the full text is `docs/app-builder-spec.md`). Check `git status` is clean (the user commits after each milestone;
   if it is not clean, ask before continuing).
2. **Map before you change:** grep every identifier / literal you will touch across `backend/src backend/scripts backend/tests
   frontend/src` (quote the globs: `--include='*.py'`). Decide what is a mechanical rename and what needs new content.
3. **Mechanical renames by script** (M1, M2 pattern): write a small Python script (word-boundary `re.sub`, longest names first,
   plus literal replacements), run it, then **grep for leftovers**. Identifiers joined by underscores (`uq_patient_memories_fact`,
   `_perspective_result`, `where_perspectives_agree`) are NOT matched by `\b` renames: handle them by hand.
4. **Hand edits with asserts:** use a Python `edit(path, [(old, new), ...])` helper that asserts `old in text`, so a missed
   replacement fails loudly instead of silently leaving stale code. Whole-file rewrites (`cat > file <<'EOF'`) for new prompts/modules.
5. **Keep the trust boundaries in Python:** ids, URLs, totals, loop decisions, routing, approvals, "did it build" facts are
   computed in Python, never taken from the LLM. New LLM outputs get a Pydantic schema with cross-field validators.
6. **Tests first, offline:** `cd backend && uv run pytest -q` (no network, no DB; fake LLM in `tests/conftest.py`). When you add a
   node/module that calls `call_structured`, add its module path to `LLM_USERS` and a builder to `DEFAULT_BUILDERS` (builders derive
   plan ids / evidence ids / source indexes from the prompt text with the regexes at the top of conftest).
7. **Frontend:** `cd frontend && npm run lint && npx tsc --noEmit`; mirror every API model change in `src/lib/api/types.ts`.
8. **DB change?** Write the Alembic migration by hand (renames: `op.alter_column(..., new_column_name=...)`, `op.rename_table`, raw
   `ALTER INDEX / CONSTRAINT / SEQUENCE ... RENAME`), then `uv run alembic upgrade head`, `uv run alembic check` (must print
   "No new upgrade operations detected"), `uv run alembic downgrade -1`, `uv run alembic upgrade head`.
9. **Live verify:** `backend/scripts/verify_mN.py` runs the real APIs at node level (cheap), prints ✅/❌ lines and `MN VERIFY: PASS|FAIL`,
   exits 0/1. Standard idea: "A simple calculator web app" (+ one richer idea when behaviour must adapt).
10. **Regression gate:** `bash backend/scripts/verify_m0.sh` (pytest + eslint + tsc) must pass before you report.
10a. **New or bigger LLM schema?** Probe it first: `uv run python scripts/probe_schema.py ai_decision_arena.schemas:Model`
    (grammar limit, section 16). Give review-style outputs enough `max_tokens` (a 9-check review needed 7000, not 3500).
10b. **End to end over HTTP** once per milestone that changes the graph: `uv run python scripts/api_flow.py --auto` against
    the dev backend on 8001 (the user usually has `uvicorn --reload` on 8001 and `next dev` on 3001 running from their own
    terminal: check `lsof -iTCP:8001 -sTCP:LISTEN` and reuse them, don't start a second server). Node-level verify scripts
    missed two real bugs that only the API path showed (thread_id not in state; appendix rendering).
10c. **Browser check by the user** for new screens: tell them how to test at http://localhost:3001/admin and what to look
    for; lint + tsc only prove the code compiles. Their screenshots found 5 bugs in M5.
10d. Long live runs go in the background with unbuffered output (`uv run python -u script.py > /tmp/x.log 2>&1`); without
    `-u` the log stays empty until the end.
11. **Handoff:** update section 0 (status table), tick the milestone in section 8, add to 12 (decisions), 14 (progress log, with the
    real verify numbers), 16 (new gotchas), and rewrite "▶ Next step". Then tell the user the commit name from the milestone's
    **Commit:** line and the files in `git status`. **Never run `git commit` / `git push`.** Wait for "pushed" before the next milestone.
12. **Ask the user** only for decisions that are theirs (section 13) and before live runs that cost real money (the full
    E2E: tell them the estimate first); otherwise choose, state the assumption in the handoff, continue.
13. **Facts, not claims** (the product's own rule applies to us): a build, test, preview or "it works" is reported only
    after a command or HTTP request confirmed it. Re-check the agent's output independently (re-run its tests in the
    sandbox, GET the preview, read the generated code), and when a check fails, read the cause from the state or the
    log before explaining it (a guessed cause was wrong once in M8).
14. **Intermittent failure = real bug until proven otherwise.** M7's reconcile kill (reloader), M9's stop/status race
    and M9's port sharing all first looked like flakes. Repeat the run, find the mechanism, add a regression test.
15. **While a long live run is going:** do not edit backend files (the user's `uvicorn --reload` restarts the API and
    redoes the in-flight step); frontend edits are safe. Check progress through the API (`GET /api/decisions/<id>`) or
    the log, not the browser page.
16. **Tests that touch processes or ports** must use the fixtures (`root` / `ws` / `manager` in test_workspace,
    autouse `process_manager` in conftest) and must not assume a fixed free port: leftover previews may hold 4100+.
17. **UI changes: look before you ask the user.** Render the page yourself with headless Chrome (screenshot or
    `--dump-dom`, section 16) and read the screenshot; walk every pause for free with `scripts/fake_api.py`. M10's
    screenshots caught 3 visual bugs before the user saw them. The user's browser check is still the final word.
18. **The user tests live and sends screenshots (often with no text): read every pixel.** In M10 each screenshot
    held a finding (a hedging Ask answer, a plan that silently dropped the request and would rebuild everything, a
    brief contradicting the built app, a misrouted correction, a wrong "you said" flag). Loop: say what you see →
    find the mechanism in the code (not a guess) → ask only if the fix is a product decision (AskUserQuestion with a
    recommended option) → fix + regression test + handoff entry → tell the user exactly what to do next in their open
    session (which text to type, what to check before approving).
19. **Anything that changes a BUILT app must respect what exists:** the brief is edited only (wording-only), every
    agent sees `<changes_built_after_approval>`, the writer keeps `<built_app>`'s stack, the planner writes an
    EXTENSION (never resets finished tasks). Before telling the user "approve", read the plan / brief yourself
    (new vs built tasks, stack kept, earlier changes kept).
20. **A broken live session can be repaired from its checkpoint history** instead of starting over (section 16,
    "rolled back"); say so to the user, keep the history, and only do it when the next node is a pause (no LLM call).
21. **Never write into the user's own folders** (e.g. their Download target): verify read-only (shasum, ls). Generated
    code runs only through the sandbox (`workspace.sandbox.run`), also for your own checks.
22. **Answer cost / behaviour questions from data**, not memory: costs from `GET /usage` (since M11: builder AI +
    coding agent per stage, first build, each change, step; `GET /api/metrics` across sessions), behaviour from the code (e.g. one fresh Agent SDK session per task attempt; the project
    folder and a short briefing carry the context).

## 16. Gotchas met so far (read before you repeat them)

**Shell / tooling on this Mac**
- The shell is **zsh**, and `grep` is **ugrep**. Unquoted `--include=*.py` fails with "no matches found": always quote globs.
  `$PIPESTATUS` is empty in zsh (`pipestatus` lowercase), and `[ "" -eq 0 ]` is TRUE: to get a script's exit code, run it without a
  pipe (`bash script.sh >/dev/null 2>&1; echo $?`) instead of `script | tail; echo $?`.
- **Parallel tool calls share one shell cwd.** A `cd` in one call changed the cwd of calls running at the same time, and heredocs
  landed in the wrong directory ("no such file or directory"). Use **absolute paths** in every command that writes files; keep
  `cd` out of parallel calls; when several edits touch the same file, run them sequentially in one call.
- Tool output above ~30 KB is persisted to a file instead of shown; read big dumps in chunks (`head -c 27000`, `tail -c +27001`).
- Ports **8000/3000 belong to the original ai-lab servers** (cwd `/Users/dev/pro/ai-lab`); run ai-lab-2 on 8001/3001.
- The **Docker daemon is not running** (CLI only). `uv run` prints "Building ai-decision-arena" after a `pyproject.toml` change: normal.

**Tests**
- pytest collects any module-level function named `test_*`, including helpers: a lifespan helper called `test_lifespan` was collected
  as a test and errored ("fixture 'application' not found"). Name helpers without the `test_` prefix.
- `EvidenceRef.evidence_id` has **no** regex pattern; only `Evidence.evidence_id` and the plan ids do. Don't assert validation errors
  on models that have none.
- Nodes import `call_structured` **by name** (`from ai_decision_arena.llm import call_structured`), so patching `llm.call_structured`
  does nothing: patch each module (conftest `LLM_USERS`). The same applies to `run_searches` (patched in `nodes.research`) and to
  `search_one` (patched in `research.search`).
- `get_settings()` is `lru_cache`d per session mode and `config.py` loads `.env` at import with `override=False`: set test env vars
  **before** the first `ai_decision_arena` import (top of conftest). Tests must never touch the real DB (`DATABASE_URL` points at a
  dead port, `PERSIST_RESULTS=false`, `CHECK_INS_ENABLED=false`).
- The API test replaces the Postgres lifespan with `app.router.lifespan_context = <InMemorySaver lifespan>`; the background
  `GraphRunner` thread sees the monkeypatches because they are module attributes. Poll `GET` until `run_state != "running"`.

**Renames and vocabularies**
- The lane value `"research"` collided with the graph **node** named `research` (progress lines, `NODE_INFO`, status
  `researching`): never blanket-replace that word; the lane literals were replaced only as the tuple/union/regex patterns
  (`"research", "doctor", "patient"` → `"apps", "papers", "tech"`, `(research|doctor|patient)` → `(apps|papers|tech)`).
- `frontend/src/lib/pipeline.ts` **parses backend progress messages by string pattern**: `planned N searches`, `[apps] N results`,
  `unique results`, `<domain> domain: kept`, `<domain> domain:`, `decision:`. Changing a `report()` message silently breaks the
  live "now" panel; change both sides (grep `report("` in nodes and `msgs.some(` in pipeline.ts).
- `knowledge_docs.search_vector` is a Postgres **generated column** that references the `condition` column; that rename was deferred
  to M11 to avoid recreating the computed column mid-pivot. `knowledge_docs.condition` still stores the project name.
- The health demo scripts were deleted in M3. Health leftovers that remain are listed in section 2.5. Scripts that are
  rarely run can rot: compile them (`uv run python -m compileall -q scripts src migrations`) after renames.

**Edits and renames (more)**
- **BSD `sed` has no `\b`**: `sed -i '' 's/\bcare_plans\b/x/'` silently changes nothing on macOS. Use Python `re.sub(r"\bname\b", ...)` (or `[[:<:]]name[[:>:]]`) for word-boundary renames, and always re-grep afterwards.
- The shared-cwd race (above) also hits read-only commands: a `grep` with relative paths in a parallel call printed "No such file or directory". Use absolute paths in every parallel call, reads included.

**Structured output size limit (M4)**
- Strict structured output (`method="json_schema"`) compiles the schema into a grammar, and the API refuses big schemas:
  `400 invalid_request_error: The compiled grammar is too large ... Simplify your tool schemas`. It fails on BOTH models
  instantly (no tokens spent). The limit grows with the number of **object occurrences** (`$ref`s are inlined): 15 fields of
  `list[BriefItem]` compiled, 30 did not, even with the enum removed. The full `ProblemBrief` (≈ 25 nested objects) failed;
  sections 1–4 / 5–6 / 7–9 each compile. Fix used: split the output into parts (`BriefPartOne/Two/Three`), several calls.
  **Before adding a large LLM schema (planner M6!), probe it** with a tiny prompt and `max_tokens=50`: the grammar error
  comes back before any generation (`uv run python scripts/probe_schema.py ai_decision_arena.schemas:MyModel`).

**LangGraph**
- **`thread_id` is NOT in the state** (the API passes it only in the run config; `ArenaState.thread_id` is never set).
  A node that needs it (DB writes) must read `langgraph.config.get_config()["configurable"]["thread_id"]`, like
  `completion_node`'s `config` argument. M5's artifact save silently skipped because of this; the offline test passed
  because it put `thread_id` into the graph input. **Tests must start sessions exactly like the API** (no extra state).
- An interrupted node is re-run **from its first line** on resume: never put an LLM call in an `await_*` node (M5/M6/M9 pauses must
  copy the `clarification` / `await_clarification` split). Resume with `Command(resume=<reply>)`; the reply is exactly what
  `interrupt()` returns inside the node, so validate it there and re-interrupt with `error` on bad input.
- Every new node must be wrapped by `wrap_node` and wired with `connect(...)` so the `error → completion` guard applies; add it to
  `EXPECTED_NODES` in `tests/test_graph.py` and to `scripts/draw_graph.py` `PHASES` (the script refuses unknown nodes).

**LLM calls (M5, M6)**
- `max_tokens` too small shows up as `output truncated at max_tokens` → retries → fallback to Haiku (slower, worse). Size
  limits in the prompt AND in the schema field descriptions ("at most 2 sentences") keep outputs inside the budget.
- **Opus 5.5 / Sonnet 5.5: thinking cannot be disabled; Opus 5.5's default effort is `medium`.** Set effort explicitly
  (`call_structured(..., effort="high")` → `ChatAnthropic(output_config={"effort": ...})`; langchain-anthropic 1.7.6 merges
  it with the structured-output format). Never send `temperature` / `budget_tokens` / `thinking: disabled` to these models.
- Non-streaming calls are fine up to ~16k output tokens; beyond that the SDK needs streaming. Large outputs need a longer
  per-call `timeout` (planner: 600 s; the default 90 s is for normal nodes).
- Never assume a model exists: `llm.resolve_model()` checks `GET /v1/models`. In tests it is patched in the `fake_llm`
  fixture (a real network call otherwise).
- Keep LLM-facing rules in ONE place: everything every agent must know about the user goes into `prompting.user_case_block`
  (e.g. `<brief_feedback>`), not into per-node plumbing.

**Rendering markdown (M5)**
- A bold line directly after a bullet list is swallowed by the list's last item (markdown lazy continuation): always put a
  blank line before and after sub-headings. Never put markdown table rows in a bullet list. `test_bold_subheadings_are_separated_from_lists` guards the brief.

**Tests (more)**
- `finish_session(graph, config)` (conftest) only drives an already STARTED session: call `graph.invoke({question...}, config)`
  first (use `run_full` in `test_plan.py`). Forgetting it returns an empty state and the test fails in odd places.
- The fake LLM resolves a runtime schema subclass (e.g. `plan.plan_schema_for`) through its MRO to the base builder, then
  re-validates with the subclass so the extra validators still run.

**Problems met in M7–M9 and how they were solved** (format: *Symptom* → cause → **fix**; read the symptom first, it
is what you will see)

*Workspace, sandbox, processes (M7)*
- *Symptom:* a sandbox command dies with exit `-15` (SIGTERM) after ~1–1.5 s, only sometimes (2 of 4 runs), never
  when the same command runs alone. → Cause: the user's `uvicorn --reload` on 8001 restarts the API on EVERY backend
  file edit (new scripts too); the API's startup `reconcile()` treated the live command of a separate script as an
  orphan and killed it. → **Fix:** the run file `.builder/run/<pid>.json` records its OWNER process (pid + start time);
  startup cleanup only kills groups whose owner is dead. Proved by touching a backend file mid-command: the worker
  restarted (97632 → 97771) and the command ran to its own timeout. Rule: anything at API startup must only clean up
  after DEAD processes. Two intermittent failures right after editing files = suspect the reloader first
  (`lsof -nP -iTCP:8001 -sTCP:LISTEN`).
- *Symptom:* `psutil.Process(pid).environ()` returns `{}` for a child process, so an env marker (`AI_BUILDER_SESSION=...`)
  could not identify our processes. → Cause: macOS (SIP) hides other processes' environment. → **Fix:** identify a
  process by pid + `create_time()` (`sandbox.is_same_process`), never by its environment.
- *Symptom:* port tests flaky: "port not free" right after `stop()`, and a restart sometimes failed. → Cause: our own
  health-check request leaves the server's port in TCP TIME_WAIT (~30 s) and a plain `bind()` refuses it. → **Fix:**
  the free-port bind uses `SO_REUSEADDR` like real dev servers do (still fails on a LISTENING port).
- *Symptom:* the sandbox's `python3 -c "import sys; print(sys.prefix)"` printed the BUILDER's virtualenv. → Cause: under
  `uv run`, `.venv/bin` is first on PATH, so the tool symlinks pointed at the builder's interpreter. → **Fix:**
  `sandbox.host_tool_path()` removes the virtualenv from the PATH the tool links are built from (test asserts it).
- *Symptom:* `python3 -c "print(1); print(2)"` refused as "shell operators are not allowed". → Cause:
  `command_problems(shlex.join(argv))` sees the quoted `;` / `(` / `>` as shell operators. → **Fix:** argv LISTS skip the
  shell-operator check (`shell_operators=False`, there is no shell); plan command STRINGS keep it.
- *Symptom (found by reasoning, then tested):* `git status` inside a session's `app/` succeeded, i.e. it saw the
  ai-lab-2 repo around `generated_projects/`; `git add/commit` there would write into the builder's own repository.
  → **Fix:** `GIT_CEILING_DIRECTORIES=<generated_projects>` in the sandbox env; test + verify_m7 assert exit 128
  "not a git repository".
- *Symptom:* `timeout 600 uv run ...` → exit 127 "command not found: timeout". → Cause: macOS has no GNU `timeout`.
  → **Fix:** rely on the tool call's own timeout, or `run_in_background` for long runs.

*Coding agent (M8)*
- *Symptom:* not knowing the Claude Agent SDK's options; the claude-api skill says it does not cover the SDK. →
  **Fix:** read the installed source (`backend/.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py`,
  `ClaudeAgentOptions` docstrings, `HookMatcher`, `ResultMessage`, `create_sdk_mcp_server` / `tool` in `__init__.py`),
  then prove each requirement with a small real spike (`scripts/spike_agent_sdk.py`, 13 s, $0.02) before building.
- *Symptom (found in the SDK docstring):* `ClaudeAgentOptions.env` is "merged over the parent process's environment".
  → Cause: the CLI subprocess inherits the builder's env (`DATABASE_URL`, Tavily / LangSmith keys); its built-in Bash
  would run generated-project commands next to those secrets. → **Fix:** never offer the built-in Bash
  (`tools=[Read, Write, Edit, Glob, Grep]`); commands go through our in-process MCP tool `run_command` →
  `sandbox.run` (env built from nothing); the secret names are also set to "" in the CLI env.
- *Symptom:* without isolation the CLI would load the user's `~/.claude` (settings, CLAUDE.md, memory); the init
  message still listed the CLI's bundled skills. → **Fix:** `setting_sources=[]`, `CLAUDE_CONFIG_DIR=.builder/claude-config`,
  `skills=[]`; auth with `ANTHROPIC_API_KEY` from `.env` (init shows `apiKeySource: ANTHROPIC_API_KEY`).
- *Symptom:* the path hook would deny every file call. → Cause: Claude Code's file tools send ABSOLUTE paths and
  `safe_path` only accepts relative ones. → **Fix:** `paths.tool_path_problem` (absolute → `is_inside` after resolving
  symlinks, relative → `safe_path`, Glob patterns may not contain `..` / start with `/` or `~`).
- *Symptom:* verify_m8 FAILED on "status completed_with_uncertainty" although both tasks passed; my first explanation
  ("the brief has open issues") was a GUESS and wrong (0 open issues). → Cause: the cached calculator state has a
  CONDITIONAL research report (M3's Judge asked for clarification); `completed_with_uncertainty` has three causes
  (conditional report, brief open issues, unfinished tasks / failed build / preview not ready). → **Fix:** the check
  reads the cause from the state and states which one applies. Rule: read the cause, never guess it.
- Tests: the conftest `FakeAgent` (in the `fake_llm` fixture) writes the files a task lists; `skip` / `fail_once` /
  `writes` steer failures and fixes. The fake plan's verify commands are `ls <files>` so they run for real without npm.

*Build check, preview, change requests (M9)*
- *Symptom:* after the user's 2nd screenshot the admin page still said "Waiting for your plan review" 3 minutes after
  `api_flow.py --auto` had approved the plan (the API said `running · implementing`). → Cause: `useDecision` polled
  only while `run_state == "running"`; once it saw "paused" it never asked again, so a pause answered elsewhere
  (script, another tab) left the page stale forever. → **Fix:** poll every 5 s while paused / interrupted, stop only
  when finished. Rule: check live state through the API (`curl localhost:8001/api/decisions/<id>`), not the page.
- *Symptom:* a crashed test dev server was reported "ready", and a stopped preview still answered HTTP — only while the
  E2E calculator was still running on 4100. → Cause: on macOS a `SO_REUSEADDR` bind to 127.0.0.1:4100 SUCCEEDS while
  another process (Node) listens on the wildcard `*:4100`; the second session got 4100 and its health check was
  answered by the OTHER session's app (in production: one session's preview showing another session's app). → **Fix:**
  `port_is_free` first CONNECTS to 127.0.0.1 / ::1 (anything accepting = taken), and `ready` additionally requires
  `processes.listens_on(pid, port)` (psutil: our started process tree holds the LISTEN socket). Regression test
  `test_a_foreign_wildcard_listener_is_never_mistaken_for_our_preview`.
- *Symptom:* `test_idle_stopper` saw state "failed" instead of "stopped". → Cause: a race: `stop()` kills the server,
  then saves "stopped"; a concurrent `status()` (the test loop, or any `GET /preview`) saw a dead process on a "ready"
  record and saved "failed" over it. → **Fix:** `ProcessManager` uses an RLock and `status()` checks + fails under it.
- *Symptom:* my new regression test failed: `listens_on(os.getpid(), port)` was True for the "foreign" server. → Cause:
  the foreign server was started by the pytest process, so it is a CHILD of it and `listens_on` (correctly) includes
  children. → **Fix:** compare against the preview's own pid, not the test process. Rule: when a new test fails, check
  the test's assumption before changing the code.
- *Symptom:* after wiring the new pause, 8 existing tests failed ("Left contains one more item: 'await_change_request'",
  `PendingPause` literal error, "too many values to unpack"). → Cause: sessions no longer END after the plan approval;
  they pause at `await_change_request`, the API's `PauseType` did not know `change_request`, and a failed task now
  triggers fix tasks F1/F2. → **Fix:** `finish_session` replies `finish`; `to_preview` helper in `test_delivery.py`;
  `PauseType` + `ChangeRequestResume`; tests updated to the new flow (expected changes, not regressions).
- *Tip:* adding a member to a TypeScript discriminated union (`PauseType`) makes `tsc` list every place that must
  handle it (`DecisionView`, `pipeline.ts` pause map): add the type first, then fix what tsc reports.
- Pipeline tests start REAL dev servers (fake plan dev = `python3 -m http.server {port}`); the autouse
  `process_manager` fixture gives each test its own in-memory registry and stops its servers afterwards. Leftover
  previews (idle stop = 30 min) from E2E runs hold ports while tests run: never assume a specific free port.
- A dev command needs the port: real plans put `$PORT` inside the package.json script (the shell expands it); a plain
  command can use `{port}` (replaced by Python). `npx serve -l tcp://...:$PORT` as a plan command does NOT work
  (no shell, `$PORT` stays literal).
- To steer the fake planner in one test: `fake_llm.overrides[S.ImplementationPlan] = builder` (e.g. a broken dev
  command); `fake_llm.kwargs[i]["user"]` holds each call's prompt (used to prove a replan request reached the planner).

*Builder UI (M10)*
- *Symptom:* the headless screenshot at `--window-size=420,...` looked cut off on the right. → Cause: headless Chrome on
  macOS keeps a ~500 px minimum layout width. → **Fix:** check phone layouts at 600 px (still below `md` = 768 px).
- *Symptom:* the Plan tab looked faded in one screenshot. → Cause: `animate-fade-up` (0.35 s) was mid-way when the
  virtual time budget ended (the plan was fetched late). → **Fix:** none needed; a longer `--virtual-time-budget`
  (15000) showed it fully. Rule: re-shoot before "fixing" what may be screenshot timing.
- *Symptom:* the resize drag stopped as soon as the pointer crossed into the preview; after a fix, double-click reset
  stopped working. → Cause: an iframe swallows pointer events; and a full-page drag cover shown on pointerdown caught
  the second click of the double-click. → **Fix:** `setPointerCapture` on the handle (events keep coming over the
  iframe) + the cover only after a 3 px move. Found by `check_resize.mjs`: real mouse events over the Chrome DevTools
  protocol (Node 22's built-in WebSocket, no Puppeteer needed) — use that pattern whenever a UI check needs clicks or
  drags.
- The native folder picker (`showDirectoryPicker`) cannot be automated. `check_download.mjs` replaces it with
  `navigator.storage.getDirectory()` (the Origin Private File System has the same FileSystemDirectoryHandle API),
  clicks the real button and lists what was written; downloads are caught with `Browser.setDownloadBehavior` on the
  BROWSER target (`/json/version` WebSocket), not the page.
- Headless Chrome is the agent's eyes: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new
  --disable-gpu --hide-scrollbars --window-size=1440,900 --virtual-time-budget=9000 --screenshot=/tmp/x.png <url>`
  (then Read the PNG), or `--dump-dom` for the HTML after the client fetched its data (verify_m10 asserts on it). It
  cannot click: drive the pauses through the API (curl / httpx `POST /resume`) and re-render.
- `git rm` STAGES the deletion. The user commits, so keep the index untouched: delete with `rm`, or `git reset -q`
  afterwards (done in M10).
- `next build` next to the user's `next dev` is safe in Next 16: dev writes to `.next/dev`, the build to `.next`. A
  second `next dev` on another port is NOT (same `.next/dev`): use `next build && next start -p 3002`. A build bakes
  `NEXT_PUBLIC_API_URL` in: rebuild against 8001 after a fake-API build (verify_m10 does).
- *Symptom:* my own check of the generated percent feature returned "Invalid expression" for every input although
  its tests passed. → Cause: I called `calculate("430-20%")`; the engine takes TOKENS (`calculate(tokenize(text))`).
  → **Fix:** read how the project's own tests call the code before calling it yourself; a failing independent check
  is first a question about the check.
- *Symptom:* a "new plan" for a running app listed T1–T12 again and would have rebuilt everything. → Cause: the
  planner only knew the brief and the previous plan, and `tasks_from_plan` reset every task to pending. → **Fix:**
  extension mode (decisions). Rule: anything that re-plans a built app must see what exists (tasks, later changes,
  files) and must not reset finished work.
- A checkpointed session can be rolled back without losing history: pick the checkpoint from
  `graph.get_state_history(config)`, `update_state(that_config, {}, as_node=<the node before the wanted step>)`, then
  `invoke(None, thread_config)` (only safe when the next node has no LLM call, e.g. an `await_*` pause).
- Order of conversation items: review / change `at` has second resolution, chat messages microseconds: two items in
  the same second can swap (only a script is that fast). Sorting is by `Date.parse`, stable.
- The chat's "answered" state (a reply sent, poll not caught up) is time-based: `sentAt` vs the last status poll
  (`useDecision().lastUpdate`). A pause key does not work: a finished project has none, and two finishes would look
  the same.

*Live findings from the user's browser tests (M10), symptom → cause → fix*
- *Symptom:* Ask, asked to add a feature to a FINISHED project, said "if Change mode is closed, you may need to reopen
  it" — a button that did not exist. → Cause: Finish ended the graph for good. → **Fix:** Reopen (decisions) + Ask's
  prompt says a change sent in "Request some change in app" reopens the project. Rule: the assistant's prompt must
  describe the UI as it is; when you add or rename a mode, update `chat.SYSTEM_PROMPT` too.
- *Symptom:* "Plan a bigger change: make it scientific" → plan v2 without the feature, same 12 tasks from T1. →
  Cause: the planner must follow the approved brief (scientific was out of scope), and replanning reset every task. →
  **Fix:** brief first + plan extension (decisions, section 2.1).
- *Symptom:* the updated brief listed the already built percent key and theme as "out of scope / later". → Cause:
  the writer never saw the C-task changes. → **Fix:** `prompting.built_changes_block` in every agent's `<user_input>`.
  First fix gave it only to the writer, so the VALIDATOR then flagged the percent rule's "you said" label as
  unsupported → moved to the shared block (rule: anything every agent needs goes into `user_case_block`).
- *Symptom:* a one-line correction to the brief took ~4 min and the new brief swapped Big.js for Decimal.js. → Cause:
  target "auto" → the FeedbackRouting LLM chose `proposal`, which re-ran proposer / critic / judge / checker and a
  fresh brief. → **Fix:** once built, the review is wording-only (auto → wording without the LLM call) and the writer
  gets `<built_app>`.
- *Symptom:* an API test asserting the LAST review turn was "brief approve" failed once. → Cause: review `at` has
  1-second resolution and the offline flow is faster than that, so a plan approval and a brief approval tied. →
  **Fix:** count, don't order, in fast tests.
- *Symptom:* `verify_m10` failed "message box in Ask mode" after the renames. → Cause: the check assumed a finished
  session; the reference session was paused at the change pause (default mode = change). → **Fix:** checks read the
  session's state first. Rule: live verify scripts must not assume the state of a session the user keeps using.

*M11 (cost)*
- langchain-anthropic's `usage_metadata.input_tokens` already INCLUDES cache reads and writes (its
  `_create_usage_metadata` adds them), the raw API's `input_tokens` does NOT. Mixing them up bills cached tokens
  twice; `pricing.tokens_from_langchain` / `tokens_from_anthropic` are the only two converters.
- A ContextVar set inside a StreamingResponse generator does not survive to the generator's next step (Starlette runs
  each `next()` in the threadpool with a fresh copy of the context). Anything per-request a stream needs travels in an
  object (Ask: `ToolContext.meter`). Graph nodes are fine: a node runs in one call and its worker threads copy the context.
- At the change pause `workflow_status` is `previewing` (the last working status), not `awaiting_changes`; the pause is
  `pending.type == "change_request"`. Check the pause, not the status, in tests.

**Working with the user / this environment**
- The user watches the admin page while things run and sends screenshots: they found bugs lint + tsc could not
  (M5: 5 bugs; M9: stale page while a script resumed, wrong task count, finished session hiding the app). Ask for a
  browser check after every UI change and say exactly what to look at.
- The user's dev servers run with `--reload` from their own terminal; output of those processes is not visible to
  the agent. Use the API (`curl localhost:8001/...`) and `lsof` to see their state.
- The claude-api skill describes the Messages API defaults (it says to use Opus everywhere): this project's model
  choices are decided (planner Opus 5.5, everything else Sonnet 5.5, fallback Haiku 5.5, all in config.py). Do not
  change models because a reference says so; it also does not cover the Claude Agent SDK (read its installed source).

**Spec**
- Until 2026-10-24 the product spec existed only in the chat that produced this plan; a new session could not see sections
  4.1–4.10 or the nine validation checks. It is now saved verbatim in `docs/app-builder-spec.md` and quoted in the milestone
  blocks. Keep it that way: anything the user specifies in chat that a future agent needs goes into the spec file (verbatim,
  dated) or into this handoff (decisions), never only into the conversation.

**Live verify observations (quality, not failures)**
- Calculator idea, M2: the papers domain is thin (3 records) and the extractor labelled two Wikipedia pages as
  `research_paper` / `technical_docs`. Revisit source-type guidance with eval cases in M11.
- Calculator idea, M3: the Judge ended with `request_clarification` (not `proceed`) because the proposals contradicted the
  "simple calculator" assumption. That is the intended behaviour: in the graph it goes back to clarification with the two
  contradiction questions. `verify_m3.py` still runs the checker and the report afterwards to exercise them.
- Calculator idea, M4 (reviewer's medium points, left as open issues): the writer labelled the *assumed* scope ("basic
  arithmetic, browser, no accounts" from the verify script's assumptions) as `user_provided`; it repeats settled points
  as open questions (it is told to cover every `unresolved_questions` item, and the cached state still carries the
  Judge's unanswered contradictions); every success criterion has `target = null` (correct per spec without a baseline,
  but the reviewer wants pass/fail definitions: acceptance criteria cover that). `verified` stays when ANY cited source
  is verified, even if another cited one is only partial. Candidates for M11 eval cases, not hard rules.
- Calculator idea, M5 E2E: the writer still produces more items than fit, so the fitted main part is ~900 words but the
  appendix reaches ~1,000 words (now grouped per section and readable). If users find it heavy: lower the schema list
  ranges or drop overflow beyond the second cap level instead of moving it (an M11 eval decision).
- Clarification sometimes packs "budget, launch date, or existing assets" into one question; the "one question per item" rule
  is in the prompt, a stricter check (count of "or" clauses) would be an M11 eval, not a hard filter.

## ▶ Next step
**M11 part 1 (cost + usage) is built and verified** (`verify_m11.py` PASS, 244 pytest + eslint + tsc + `next build`).
The user commits it, e.g. `M11.1: cost and usage tracking` (`handoff.md` also still carries the uncommitted M10 handoff
update). After "pushed", continue M11 in this order (section 8, M11 block):
1. **Part 2 — `tool_calls` log**: the agent's PreToolUse decisions (tool, target, denied + reason) and every sandbox
   command (argv, exit code, refused, timed out, duration) into a `tool_calls` table (they are in
   `.builder/logs/*.log` / `commands.jsonl` today, not queryable); `/api/metrics` adds tool failure / refusal counters.
2. **Part 3 — prompt registry + evals**: `prompts/` (VERSION, owner, changelog), versions recorded per session, eval
   cases from M10's live findings (section 16) + `run_evals.py` (fake offline, `--live` real, cost printed from the
   meter); prompt caching for stable system prompts (Ask measured at ~$0.05 per reply).
3. **Part 4 — builder knowledge + skills + cleanup** (section 2.5 / 2.6 leftovers, idle trigger, quick profile removal).
4. A brand-new idea end to end in the builder UI (~$2–3, ask first). It is now fully metered: report the real
   per-stage cost from `GET /usage` and replace the guesses in section 11.
