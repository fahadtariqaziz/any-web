# ai-lab-2 — Handoff: AI App Builder (Lovable-style)

> **Read this first in every new session.** It is the always-current record: where the project stands, how it is built,
> the plan we follow, and what is next. **Update it after every major change** (structure, decisions, progress, next step).
>
> **New agent / new session?** Read section 0 (status), the current milestone in section 8, then **section 15 (how to work
> here) and section 16 (gotchas)** before touching code. They record how the previous sessions worked and what bit them.
> The **original product specification is saved verbatim in `docs/app-builder-spec.md`**; milestones cite it as "spec §4.3".
>
> **Working rule (agreed 2026-10-24):** one milestone at a time. For each: build → run its verify script → if it passes,
> the user commits and pushes (Claude never commits) → next milestone. Ask the user when a decision is theirs.

---

## 0. Status at a glance

| | |
|---|---|
| **Spec** | `docs/app-builder-spec.md` — the user's original brief, verbatim (clarification §1, research §2, proposals §3, brief §4.1–4.10, validation §5, review §6, planning §7, implementation §8, preview + isolation §9, platform §10.1–10.11, constraints §12, outcome §13). The milestone blocks below quote the parts each one needs. |
| **Concept (decided 2026-10-24)** | An AI application builder like Lovable: the user describes an app or website; the system clarifies, researches, proposes, critiques, judges, writes a validated problem statement + solution brief, gets approval, plans (Opus 5.5), implements (Sonnet 5.5) in an isolated session folder, and shows a live preview beside the chat. |
| **Where we are** | **M6 done** (2026-10-25): after the brief approval, `planner` (Opus 5.5, effort high, model checked against `GET /v1/models`) writes an `ImplementationPlan` checked in Python (ids, dependency order, relative files, allowlisted commands, every approved MVP feature covered); `await_plan_review` → `plan_review_router` (approve with hash + artifact, or changes ≤ 3). **M5:** the validated brief pauses for the user's review (`await_brief_review` → `brief_review_router`; approve with hash guard + `project_artifacts`, or change requests routed to wording / requirements / research / proposal, always revalidated). **M4:** after the report, `brief_writer` (3 structured calls → `ProblemBrief`, Python references + label fixes + markdown) and `brief_validator` (6 deterministic checks + 1 LLM review on the 9 spec criteria; Python verdict approve / revise ≤ 2 / clarify). `GET /brief`, admin `BriefView`. M3: proposer → critic → judge → checker → report. |
| **Next milestone** | **M7 — session workspace, sandbox, processes** (section 8). |
| **Models (verified 2026-10-24 via `client.models.list()`)** | `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` are all available to the key in `backend/.env`. Configured default: `ANTHROPIC_MODEL=claude-sonnet-5-5`. |
| **Environment (verified 2026-10-24)** | uv 0.12.21 · Python 3.13.12 · Node 22.22 · npm 10.9 · Postgres 16.15 running, DB `ai_decision_arena_2` at Alembic head · Claude Code CLI 2.1.310 installed · Docker CLI 29.4 present but **daemon not running** · ports **8000/3000 are taken by the original ai-lab servers** → run ai-lab-2 on **8001/3001** (section 11). |
| **Tests** | `backend/tests/` (156 pytest tests, no network / no DB: fake LLM + fake search, see `tests/conftest.py`). Run `bash backend/scripts/verify_m0.sh` (pytest + eslint + tsc). No frontend unit tests yet. |

---

## 1. Target product in one paragraph

User prompt → **clarification** (2–3 rounds, pauses for answers) → **research** in 3 domains (existing apps & user feedback ·
papers & technical literature · feasibility & implementations) → **proposer** (4–5 solution proposals) → **critic** → **judge**
(scores, picks the strongest, may loop to research / clarification) → **evidence checker** → **brief writer** (one-page problem
statement + solution brief with labelled claims and real references) → **brief validator** (deterministic + LLM checks) →
**user review** (approve or request changes; changes route back to the right node) → **planner** (Opus 5.5, Claude-Code-style
implementation plan) → **user approval** → **implementer** (Sonnet 5.5 coding agent, one task per step, verified by real
commands) → **build check** → **preview** (dev server per session, health-checked) → **change requests** from the chat →
done. Every generated project lives in `generated_projects/<session_id>/`, isolated from the builder and from other sessions.

---

## 2. Current architecture (started as a copy of the ai-lab health app; 2.1 and 2.3 are kept current)

### 2.1 Graph today (`backend/src/ai_decision_arena/graph.py`, 16 nodes + completion)
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
await_plan_review → plan_review_router ──(approved, brief + plan hashes)──► completion → END   (M8: implementer)
                                       └──(changes, ≤ max_plan_revisions)──► planner
                                         ├──(wording)──► brief_writer      ├──(requirements)──► clarification
                                         ├──(research)─► research          └──(proposal)──────► proposer
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
├── docs/                           # requirements.md (original brief), pivot-medical.md, agent-anatomy.md — history
├── backend/
│   ├── .env (not in git; template .env.example), pyproject.toml, uv.lock, alembic.ini, Dockerfile
│   ├── migrations/versions/        # Alembic migrations (8 so far; head e3f4a5b6c7d8 = project_artifacts)
│   ├── knowledge/*.md              # curated knowledge docs (health; to be replaced)
│   ├── skills/*/SKILL.md           # chat skills (health; to be replaced)
│   ├── scripts/                    # run_graph, run_intake, run_research, api_flow (HTTP end to end), check_env, draw_graph,
│   │                               #   probe_schema (grammar limit), load_knowledge, print_helpers, verify_m0.sh, verify_m1..m6.py
│   ├── tests/                      # pytest: conftest (fake LLM + fake search), graph, limits, sources, schemas,
│   │                               #   nodes, full pipeline on InMemorySaver, API with TestClient
│   └── src/ai_decision_arena/      # package name kept (rename = churn, no value now)
│       ├── graph.py, state.py, schemas.py (~1200 lines), config.py, limits.py, prompting.py, llm.py, progress.py
│       ├── brief.py (brief references / labels / rendering / deterministic checks), plan.py (plan checks / rendering / hashes)
│       ├── nodes/  intake, clarification, research, proposer, critic, judge, evidence_checker, final_report (+ completion),
│       │           brief_writer, brief_validator, brief_review (await + router), planner (+ await + router), node_wrapper
│       ├── research/  planner (queries), search (Tavily), extractor (snippets → Evidence), sources (domains, url utils)
│       ├── chat.py, tools.py, researcher.py, skills.py, knowledge.py, memory.py, triggers.py, checkpointing.py
│       ├── db/  engine, models (7 tables), repository
│       └── api/  main (decisions endpoints), runner (background threads), chat, memories, triggers, schemas, errors
└── frontend/src/
    ├── app/(chat)/   `/` and `/c/[threadId]`  — ChatGPT-style chat (ChatShell, ChatView, Composer, Messages…)
    ├── app/(admin)/  `/admin`, `/decisions/[threadId]` — full pipeline view (stepper, clarification form, debate, evidence, report)
    ├── hooks/  useDecision (poll 2 s), useLive, useFetch, useStartChat…
    └── lib/  api/client.ts, api/types.ts (hand-written mirror of API models), pipeline.ts, chatStages.ts, format.ts
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

### 2.5 Health-specific parts (to replace)
Prompts of every node and of `research/planner.py`, `research/extractor.py`, `chat.py`, `researcher.py`; `SAFETY_RULES`; vocabularies in
`schemas.py` (`Perspective`, `SourceType`, `EvidenceStrength`, `ConditionCategory`, `ResearchTopic`, `CarePlan`, `FinalReport`,
`OnboardingSummary`…); domain lists in `research/sources.py`; rubric in `config.py`; red-flag / emergency logic; `knowledge/*.md`;
`skills/*`; DB columns `condition_name`, `condition_category`, `red_flags`, `patient_id`, table `patient_memories`; all UI wording,
`PERSPECTIVE_META`, `NODE_INFO`, report components.

### 2.6 Gaps for the new product
No file/command tools or sandbox for generated code · only one pause type · no approval checkpoints · no planner /
implementer / preview nodes · no prompt registry or versions · no per-node token/cost accounting · no per-session workspace.

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
                              │               ├──(replan)──► planner
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
| `change_request` | `preview`, `build_results`, task summary | `{action: change \| replan \| finish, request}` | change → `implementer` (new task); replan → `planner`; finish → `completion` |

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
| **10.11 Evaluation / observability / cost** | LangSmith traces, metrics at completion, progress lines | `token_usage` per node from `usage_metadata` + price table → USD; session budget stops new loops; `/metrics` endpoint; eval runner + E2E regression script; failure counters (M11) |

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

### M7 — Workspace, sandbox, processes
- `workspace/paths.py`, `sandbox.py`, `processes.py`, `project_runtimes` table, `generated_projects/` in `.gitignore`, orphan cleanup at startup.
- **Verify:** pytest (traversal, symlink escape, env scrub, timeout kill, output cap, allowlist) + `scripts/verify_m7.py`: creates a workspace, runs `npm init -y`, starts a tiny static server, health-checks, stops.
- **Commit:** `M7: session workspace and sandbox`

### M8 — Implementer (coding agent, one task per step)
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

### M9 — Build check, preview, change requests, completion
Spec §9 (preview + isolation): run the generated app in an isolated environment; show it in a preview panel; refresh it when
changes are applied; show useful build / runtime errors when it fails to start. Each session has a unique id and its own
`generated_projects/<session>/` folder with source, configuration, dependencies and artifacts; generated code never modifies the
builder; sessions cannot touch each other's files or runtime; conversation, approved brief, plan and execution state stay
associated with the session; sessions can be resumed; file access, terminal commands, package installation and execution are
restricted to the session's environment; resource usage and processes are managed so one project cannot disrupt another.
- `build_check` (install/test/build from `plan.commands`), `preview` (processes.py), `await_change_request`, routing, `GET /api/decisions/{id}/preview` (+ `restart`, `stop`), `GET /implementation` (tasks + log tail), completion persists brief/plan/runtime, `types.ts`.
- **Verify:** pytest (routes, fix-round cap, preview ready only after health check) + `scripts/verify_m9.py`: full pipeline `--auto` on a tiny idea; `curl` of the preview URL returns HTTP 200.
- **Commit:** `M9: build check, preview and change requests`

### M10 — Lovable UI
Spec §9 (interface): left = the conversation (initial prompt, clarification answers, document review, plan approval, change
requests), context and progress preserved through the session; right = the live preview of the running app.
- `/` and `/c/[id]`: left = chat (prompt → questions → stage chips → brief card with Approve / Request changes + target → plan card → task progress → change composer), right = `PreviewPane` (iframe, state chip, errors, refresh/restart). `/admin` keeps the detailed view with new stages. Remove health wording, update `pipeline.ts`, `chatStages.ts`, `format.ts`, layout metadata.
- **Verify:** `npm run lint`, `tsc --noEmit`, `next build`; manual checklist in the progress log (new idea → answer → approve brief → approve plan → preview visible → one change request applied).
- **Commit:** `M10: Lovable UI with live preview`

### M11 — Platform hardening (prompts, evals, cost, knowledge, memory, triggers, skills)
Spec §10.1–10.11 (platform-level requirements; section 7 of this file maps each one to what exists and what to add). They apply to
the builder itself, **not** to every generated app: a generated project gets only the AI infrastructure its approved requirements need.
- `prompts/` registry + versions in state/DB; `backend/evals/` cases + `scripts/run_evals.py`; `token_usage`/USD per node + session budget + `/metrics`; `tool_calls` log; curated builder knowledge docs + builder skills (replace health ones); `user_memories`; idle-preview trigger (replaces check-ins); `chat.py` re-pointed as "ask about this project" (optional).
- **Verify:** pytest + `scripts/run_evals.py` (fake-LLM cases offline; real cases behind `--live`).
- **Commit:** `M11: platform hardening`

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
| Platform (M11) | prompt registry, cost math, eval runner | eval cases pass |

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
Database: local Postgres `ai_decision_arena_2` (`backend/.env`). Tables: `decision_sessions`, `evidence_records`, `decision_reports`,
`user_feedback`, `chat_messages`, `user_memories`, `knowledge_docs` (its `condition` column is renamed in M11), LangGraph `checkpoint*`.
Planned tables: `project_artifacts`, `project_runtimes`, `tool_calls`.

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
- 2026-10-25 (M6): `call_structured(model=, effort=, timeout=)`; with `model` set, the fallback chain is [that model, the session's default model]. `effort` goes to `ChatAnthropic(output_config={"effort": ...})`; langchain-anthropic 1.7.6 merges it with the structured-output `format` (checked in its source). Planner settings: `planner_model=claude-opus-5-5`, `planner_effort=high` (Opus 5.5 defaults to medium and cannot disable thinking), `planner_max_tokens=16000` (non-streaming is fine up to ~16k), `planner_timeout_seconds=600`. `llm.resolve_model()` reads `GET /v1/models` once per process: listed → used; not listed → `anthropic_model` with a progress line; list unreadable → kept unchecked (the call's own fallback chain covers it). The API logs the planner / implementer availability at startup (`check_models`). The plan schema fits the strict-output grammar in ONE call (probed). Plan checks live in the schema validators so `call_structured` sends the exact problem back: unique `T<n>` ids, `depends_on` only on EARLIER tasks (order = topological order, so no cycle is possible), known phases, ≥ 1 acceptance criterion and verify command per task, relative file paths, every command passes `schemas.command_problems` (argv only, no shell operators, executable allowlist = the M7 sandbox's, no push/publish, no absolute or `..` paths, no `rm -rf .`). MVP coverage is enforced by `plan.plan_schema_for(mvp_features)`, a runtime subclass named `ImplementationPlan` (the fake LLM handles subclasses via the MRO). Guards: the planner raises unless `brief_is_approved`; `route_after_plan_review` requires `plan_is_approved` (plan hash AND brief hash), the M8 implementer route must use it. Plan review: approve / request_changes (feedback required); after `max_plan_revisions=3` rewrites only approval is accepted (node re-asks, API 422). Approved plans go to `project_artifacts` (kind `plan`). `implementation_tasks` = `{id, title, phase, depends_on, status: pending, attempts: 0, result: null}`. No server-side refusal `fallbacks` parameter (the claude-api reference recommends it for Opus 5.5): our client-side fallback to the default model covers refusals as structured-output failures; revisit when moving off langchain.
- 2026-10-25 (M5): the review pause is split like clarification: `await_brief_review` (interrupt only, validates the reply, re-asks with `error`) + `brief_review_router` (Python; ONE small `FeedbackRouting` LLM call only for `target="auto"`). Routes: wording → `brief_writer` (edits the reviewed draft: `revision_mode` = "user", detected from `current_node == "brief_review_router"`), requirements → `clarification` (+ `research_focus` with the correction), research → `research` (`research_focus` = the feedback), proposal → `proposer`. The user's change requests reach EVERY agent as `<brief_feedback>` inside `<user_input>` (`prompting.user_case_block`, rule in `BUILDER_RULES`): no per-node plumbing. User-driven loops do not consume `research_retry_count`; they are bounded by `max_review_rounds=6`, after which only wording (auto → wording without an LLM call) or approval is accepted (node re-asks; API 422). Approval stores `brief_approved_at` + `brief_approved_hash` (sha256 of the markdown); `route_after_brief_review` only proceeds when `brief_is_approved(state)` (hash matches the current markdown), otherwise back to the pause. The approved version goes to the new `project_artifacts` table (version per thread+kind, unique content hash, failure to save = progress line only, the checkpoint stays the truth); `GET /artifacts`. The brief's draft number now only grows within a session. Quick-mode chat has no review UI yet: it links to the session page (M10 builds the real one).
- 2026-10-25 (M4): the brief writer makes **three** strict structured calls (sections 1–4, then 5–6 and 7–9 in parallel with sections 1–4 as context): the whole brief schema exceeds the API's grammar limit. Python owns: references (from cited ids only), the `verified` label (needs a checker-verified source, else downgraded to `research_backed`), `required_by_user` technology (only with label `user_provided`), the one-page budget (900 words over sections 1–9, labels/citations/URLs not counted): the renderer moves list items beyond per-list caps to the appendix and, while the page is over budget, shrinks the caps level by level (`CAP_LEVELS` 1.0/0.75/0.5/0; floors keep the MVP, scope, user journey, 3 functional requirements, 2 success criteria and 2 risks in the main part); only a brief too long at the smallest caps fails `det_word_budget`. Reason: in the first live run the LLM needed two full rewrites (1561 → 1080 → 1012 words) for length alone. M5 E2E still needed two (1021 → 940 → 861): the writer now aims at 80% of the budget with ≤ ~20-word items, and `det_word_budget` passes up to budget × 1.10 (`WORD_BUDGET_TOLERANCE`, "approximately one page"). Validator: deterministic checks first; if one fails and a revision is left, revise **without** the LLM call; revise also on any high-severity LLM criterion; clarify only when the reviewer says the brief cannot go forward without the user AND `loops_allowed` permits (bumps `research_retry_count`, resets `brief_revision_count`); otherwise approve, listing remaining medium/high failures as open issues (appendix C + `unresolved_questions`, status `completed_with_uncertainty`). Approve currently routes to `completion` (M5 inserts `await_brief_review`). `GET /brief` returns only a draft whose validation verdict is approve and whose `brief_generated_at` matches the brief (no unvalidated draft is ever shown). The brief lives in the checkpoint only; `project_artifacts` (DB) comes with M5.
- 2026-10-24 (M2): the word is **domain** everywhere (code, state, API, DB columns, UI), keys `apps / papers / tech`. Tavily steering is "prefer" for all three (never exclusive); the apps domain searches with `advanced` depth. `SearchQuery` validates that a topic belongs to its domain; each domain's key topic (`user_complaints`, `established_approaches`, `feasibility_and_risks`) is always searched on the first pass (`planner.ensure_key_topics`). Patient-story top-up removed.

## 13. Open questions (for the user; none blocks M7; question 1 must be answered before M8 starts)
1. **Coding agent (M8):** OK to spike the Claude Agent SDK first (uses the installed Claude Code CLI, Sonnet 5.5, our hooks) with the own-tool-loop as fallback?
2. **Preview runtime:** start the Docker daemon for v2 later, or stay on host subprocesses for now? (v1 works without Docker.)
3. **Chat after preview:** keep the tool-using chat (`chat.py`) as "ask about this project", or retire it?
4. **Quick mode / patient chat UI:** retire the "quick" profile entirely in M10?
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

## 15. How to work on this repo (the loop every milestone follows)

1. **Start:** read section 0, the milestone block in section 8 (it quotes the spec parts it needs; the full text is
   `docs/app-builder-spec.md`), and section 3 (what maps to what). Check `git status` is clean
   (the user commits after each milestone; if it is not clean, ask before continuing).
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
12. **Ask the user** only for decisions that are theirs (section 13); otherwise choose, state the assumption in the handoff, continue.

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
- Health demo data remains in `backend/scripts/demo_data.py` / `schemas_demo.py` until M3; `RedFlagBanner` naming and the chat UI
  wording until M10. Compile them (`uv run python -m compileall -q scripts src migrations`) rather than run them.

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
**User commits M6** as `M6: Opus planner and plan review`. Then **M7** (section 6 + section 8): `workspace/paths.py`
(`safe_path`, traversal + symlink escape tests), `workspace/sandbox.py` (`run(session_dir, argv, timeout, env)`: cwd
`app/`, scrubbed env, the SAME allowlist as `schemas.command_problems` — reuse it, don't duplicate —, output cap,
process group, kill on timeout), `workspace/processes.py` (port from `preview_port_range`, `PORT` injected, health
check, stop, restart, idle cleanup) + `project_runtimes` table (Alembic), `generated_projects/` in `.gitignore`, orphan
cleanup at startup; `scripts/verify_m7.py`: create a workspace, `npm init -y`, start a tiny static server, health-check,
stop. No LLM calls in M7.
