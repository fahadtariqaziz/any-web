# Pivot (2026-10-20): from technical decisions to health conditions

`docs/requirements.md` is the ORIGINAL brief (technical decision support). On 2026-10-20 the product
purpose changed. The architecture (11 nodes, LangGraph, Claude-only, Tavily, LangSmith, Postgres,
FastAPI, Next.js) and the engineering rules in `requirements.md` §5–§7, §13 still apply. This file
records what changed and how the old concepts map to the new ones.

## New purpose
A user describes a health condition ("I have diabetes"). The system clarifies their situation, researches
how the condition is managed from **three perspectives**, debates and scores candidate care plans per
perspective, verifies the evidence, lets the user review, and writes a report with **one best plan per
perspective**:

1. **Research perspective** – papers, studies, systematic reviews.
2. **Doctor perspective** – clinical guidelines, hospital and medical-reference sites.
3. **Patient perspective** – real-world experiences from Reddit, patient forums, reviews.

Every perspective answers the same questions: daily routine, diet, medications/treatments, how long until
progress is typically seen, and whether the condition is common or rare (plus outlook).

The system gives **health information to discuss with a clinician**. It never diagnoses, never prescribes,
never invents doses, never advises stopping medication, and flags red-flag symptoms.

## Concept mapping
| Old (technical) | New (health) |
|---|---|
| technical problem / `is_technical_problem` | health concern / `is_health_concern` |
| `problem_domain` (databases, devops…) | `condition_category` (metabolic_endocrine, cardiovascular…) + `condition_name` |
| `problem_summary` | `case_summary` |
| `requirements` | `health_profile` (age, diagnosis, medications, goals) + `symptoms` |
| `constraints` (budget, cloud) | `constraints` (allergies, dietary restrictions, budget, preferences) |
| candidate options (PostgreSQL vs MongoDB) | the three perspectives (research / doctor / patient) |
| `SearchPurpose` (docs, pricing, benchmarks…) | `ResearchTopic` (overview_prevalence, routine_lifestyle, diet, medications_treatment, progress_timeline, risks_warning_signs) |
| `SourceType` (official docs, github…) | `SourceType` (research_paper, clinical_guideline, medical_reference, patient_community, health_article) |
| `CommunityContext` | `PatientContext` |
| — | `evidence_strength` (meta-analysis → anecdotal) |
| `Proposal` (2–3 solutions total) | `CarePlan` (2–3 plans **per perspective**, ids `research_a`, `doctor_b`, …) |
| one winner `winning_solution_id` | one winner per perspective `winning_plan_ids` |
| rubric: requirements_fit, technical_feasibility, reliability_and_risks, cost_efficiency, evidence_quality | rubric: fit_to_user 0.30, safety 0.25, evidence_quality 0.20, practicality 0.15, completeness 0.10 |
| `select_solution` / `modify_requirements` | `select_plan` / `modify_profile` |

## Node behaviour after the pivot
- **Intake**: extracts condition name/category, profile, symptoms, constraints, missing info, red flags.
- **Clarification**: first round asks 5–6 questions (type & confirmation, duration, symptoms & timing,
  treatments, other conditions/allergies/pregnancy, routine/diet/goals). Later rounds only if something
  material changed, or when the Judge sends its own questions.
- **Red flags** (no pause since 2026-10-24): intake and clarification record emergency signs; they are shown
  in the UI and the report and switch the Proposer / Judge to emergency-first plans with no loops.
- **Research**: one planner call → 3 queries per lane (9 total) → Tavily in parallel with lane-specific
  domain steering (research/doctor: prefer medical domains; patient: restrict to forum domains, advanced
  depth) → one extractor call per lane in parallel → evidence tagged with `perspective`.
- **Proposer**: 3 parallel calls, each sees only its lane's evidence → 2–3 `CarePlan`s per lane.
- **Critic**: 3 parallel calls, each sees its lane's plans but ALL evidence (cross-perspective challenge).
- **Judge**: 3 parallel calls score plans 0–10 per criterion; Python computes weighted totals, picks the
  top plan per lane, and decides routing (proceed / more research / clarification / insufficient) within
  the loop limits.
- **Evidence Checker**: one call per winning plan; every factual claim gets a verification status; material
  gaps trigger one focused research pass when loops are allowed, otherwise they are listed as unresolved.
- **No human review pause** (removed 2026-10-24): after the evidence check the report is written directly; it
  always shows the best plan of all three perspectives.
- **Final Report**: one best plan per perspective with scores, cited evidence and verification status, where the
  perspectives agree and differ, unsupported claims, unresolved questions, next steps, disclaimer.
- **Completion / failures** (since 2026-10-24): final status + metrics. Each LLM call retries, then tries a
  fallback model; if that fails too, the node's error is recorded and the run ends as `failed`, showing the API error.

## Package name
The Python package is still `ai_decision_arena` and the LangSmith project is still `ai-decision-arena`
to avoid churn (imports, traces, uv project). The product name in prompts is "Health Decision Arena".
Renaming the package later is a mechanical change (directory move + import rewrite).
