// TypeScript mirror of the backend's API models (backend/src/ai_decision_arena/api/schemas.py
// and the parts of schemas.py they include). Written by hand: if a backend model changes, change it here too.

// --- session status (GET /api/decisions/{thread_id}) ---------------------------------------------

/** What the HTTP layer knows about a session (not the graph's own status). */
export type RunState = "running" | "paused" | "interrupted" | "finished";

export type PauseType = "clarification" | "brief_review" | "plan_review" | "change_request";

export interface ProgressLine {
  at: string; // ISO time
  node: string;
  message: string;
}

/** Exactly what the graph's interrupt() sent. `error` is set when the previous reply was refused. */
export interface ClarificationPayload {
  type: "clarification";
  questions: string[];
  round: number;
  error?: string;
}

export type ReviewTarget = "auto" | "requirements" | "research" | "proposal" | "wording";

/** The validated brief, waiting for the user's approval or change request (spec §6). */
export interface BriefReviewPayload {
  type: "brief_review";
  brief_markdown: string;
  brief: ProblemBrief;
  validation_summary: {
    checks_passed: number;
    checks_total: number;
    open_issues: string[];
    word_count: number;
    word_budget: number;
  };
  unresolved_questions: string[];
  round: number; // 1 + change requests so far
  max_rounds: number;
  wording_only: boolean; // only wording changes (or approval) are accepted
  wording_only_reason?: "built" | "rounds" | null; // the app is already built, or max_rounds was reached
  error?: string;
}

/** The implementation plan, waiting for the user's approval or change request (spec §7). */
export interface PlanReviewPayload {
  type: "plan_review";
  plan_markdown: string;
  plan: ImplementationPlan;
  round: number; // plan version
  max_revisions: number;
  changes_allowed: boolean; // false once max_revisions rewrites were made: approve only
  model: string; // model that wrote the plan
  task_count: number;
  new_task_count?: number; // tasks still to build; less than task_count when the app is already built (plan extension)
  error?: string;
}

/** The live preview of the session's dev server (GET /preview; also inside the change_request pause). */
export interface PreviewInfo {
  state: "starting" | "ready" | "failed" | "stopped";
  url: string | null; // set only when ready (after a successful HTTP health check)
  port: number | null;
  command: string;
  last_error: string | null; // exit code / timeout + the server's last output
  log_tail?: string;
}

export interface BuildStep {
  phase: "install" | "test" | "build";
  command: string;
  ok: boolean;
  exit_code: number | null;
  summary: string; // e.g. "exit 0 in 1.2s", "timed out after 120s"
  output: string;
  skipped_tests?: number; // test step: skipped + todo tests the runner reported in its summary (M11)
}

/** The last build check: install → test → build in the sandbox. passed comes from exit codes only. */
export interface BuildResults {
  round: number;
  passed: boolean;
  steps: BuildStep[];
  at: string;
}

/** The app runs in the preview: ask for a change, a new plan, or finish (spec §8 / §9). */
export interface ChangeRequestPayload {
  type: "change_request";
  preview: PreviewInfo | Record<string, never>;
  build: BuildResults | Record<string, never>;
  tasks: { id: string; title: string; status: TaskStatus; attempts: number }[];
  cost_usd: number;
  round: number;
  changes_allowed: boolean; // false once max_change_requests was reached: finish only
  replan_allowed: boolean;
  error?: string;
}

/** `type` tells which payload it is (TypeScript narrows on it: if (p.type === "clarification") ...). */
export type PendingPause =
  | { type: "clarification"; payload: ClarificationPayload }
  | { type: "brief_review"; payload: BriefReviewPayload }
  | { type: "plan_review"; payload: PlanReviewPayload }
  | { type: "change_request"; payload: ChangeRequestPayload };

export interface ErrorInfo {
  code: string;
  message: string;
}

/** Small numbers shown next to the pipeline (all read from the checkpoint). */
export interface Counters {
  clarification_rounds: number;
  research_passes: number;
  debate_round: number;
  evidence: number;
  proposals: number;
  claims_checked: number;
}

export interface DecisionStatus {
  thread_id: string;
  run_state: RunState;
  workflow_status: string | null; // intake, researching, debating, completed, ...
  question: string | null;
  project_name: string | null;
  risk_flags: string[];
  pending: PendingPause | null;
  progress: ProgressLine[]; // lost when the server restarts
  error: ErrorInfo | null;
  has_report: boolean;
  has_brief: boolean; // a validated problem brief exists (GET /brief)
  has_plan: boolean; // the planner wrote a plan (GET /plan)
  has_build: boolean; // the coding agent has a project folder (GET /implementation)
  reopen_actions: ("change" | "replan")[]; // a finished, built project still accepts these as {type: "reopen"}
  current_node: string | null; // last node that finished
  next_nodes: string[]; // while running, [0] is the node in progress
  started_at: string | null;
  active_seconds: number;
  counters: Counters;
}

// --- live snapshot (GET /live): everything produced so far -----------------------------------

export interface CaseView {
  project_name: string | null;
  project_category: string | null;
  idea_summary: string | null;
  user_context: string;
  project_profile: Record<string, string>;
  requested_features: Record<string, string>;
  constraints: Record<string, string>;
  missing_information: string[];
  assumptions: string[];
  clarification_answers: Record<string, string>;
  risk_flags: string[];
  withdrawn_risk_flags: { flag: string; reason: string }[];
}

export interface ResearchView {
  passes: number;
  queries: string[];
  evidence_by_domain: Record<string, number>;
  evidence_gaps: string[];
  conflicting_claims: { topic: string; evidence_ids: string[]; description: string }[];
  rejected_count: number;
  domain_summaries: Record<string, string>;
  research_focus: string[];
}

export type Level = "low" | "medium" | "high";

export interface CriticismPoint {
  category: string;
  issue: string;
  severity: Level;
  basis: "evidence" | "engineering_judgement";
  is_verified_problem: boolean;
  evidence_ids: string[];
  suggested_improvement: string;
}

export interface Criticism {
  proposal_id: string;
  points: CriticismPoint[];
  overall_assessment: string;
}

export interface Verdict {
  decision: "proceed" | "request_more_research" | "request_clarification" | "insufficient_evidence";
  reason: string;
  winning_proposal_id: string | null;
  domain_status: Record<string, string>; // sufficient | insufficient | no_evidence
  required_evidence: string[];
  material_contradictions: string[];
  clarification_questions: string[];
}

export interface DebateView {
  round: number;
  proposals: SolutionProposal[];
  criticisms: Criticism[];
  scores: ProposalScore[];
  verdict: Verdict | null;
  proposer_status: string; // ok | thin | declined | no_evidence
  proposer_notes: string;
}

export interface ClaimVerification {
  claim: string;
  proposal_id: string | null;
  evidence_ids: string[];
  status: VerificationStatus;
  notes: string;
  is_anecdotal: boolean;
  is_material: boolean;
}

export interface CheckerVerdict {
  decision: string;
  reason: string;
  material_gaps: string[];
  summary: string;
  claims_checked: number;
}

export interface VerificationView {
  results: ClaimVerification[];
  verdict: CheckerVerdict | null;
  unresolved_questions: string[];
}

export interface LiveSnapshot {
  thread_id: string;
  run_state: RunState;
  workflow_status: string | null;
  current_node: string | null;
  case: CaseView;
  research: ResearchView;
  debate: DebateView;
  verification: VerificationView;
  metrics: Record<string, unknown> | null;
}

// --- session list (GET /api/decisions) ---------------------------------------------------------

/** "full" = every agent and loop (the builder and the admin view). "quick" = legacy fast profile, no longer started. */
export type SessionMode = "full" | "quick";

export interface SessionSummary {
  thread_id: string;
  question: string;
  mode: SessionMode;
  project_name: string | null;
  status: string;
  risk_flag_count: number;
  created_at: string;
  updated_at: string | null;
  completed_at: string | null;
}

export interface SessionList {
  sessions: SessionSummary[];
}

export interface Accepted {
  thread_id: string;
  run_state: RunState;
  message: string;
}

// --- requests ----------------------------------------------------------------------------------

export interface CreateDecisionRequest {
  question: string;
  context?: string;
  mode?: SessionMode; // default "full"
}

/** Body of POST /resume. `type` must match pending.type (or "continue" for an interrupted run). */
export type ResumeRequest =
  | { type: "clarification"; answers: Record<string, string> } // exact question text -> answer
  | { type: "brief_review"; action: "approve" | "request_changes"; feedback?: string; target?: ReviewTarget }
  | { type: "plan_review"; action: "approve" | "request_changes"; feedback?: string }
  | { type: "change_request"; action: "change" | "replan" | "finish"; request?: string }
  | { type: "reopen"; action: "change" | "replan"; request: string } // a finished project takes another change
  | { type: "continue" };

// --- evidence (GET /evidence) --------------------------------------------------------------------

export type Domain = "apps" | "papers" | "tech";

export type VerificationStatus =
  | "pending"
  | "verified"
  | "partially_supported"
  | "unsupported"
  | "contradicted"
  | "irrelevant"
  | "unavailable";

export interface FeedbackContext {
  product: string;
  feedback_type: "complaint" | "praise" | "feature_request" | "workaround" | "mixed";
  experience_described: string;
  is_recurring: boolean;
  context: string;
  relevant_to_idea: boolean;
}

export interface Evidence {
  evidence_id: string;
  domain: Domain;
  source_title: string;
  source_url: string;
  source_type: string;
  evidence_strength: string;
  published_at: string | null;
  retrieved_at: string;
  relevant_excerpt: string;
  is_direct_quote: boolean;
  claims_supported: string[];
  limitations: string[];
  feedback_context: FeedbackContext | null;
  sentiment: "positive" | "negative" | "mixed" | "neutral" | null;
  relevance_score: number;
  reliability_notes: string;
  verification_status: VerificationStatus;
}

export interface EvidenceResponse {
  thread_id: string;
  count: number;
  verification_counts: Record<string, number>;
  evidence: Evidence[];
}

// --- proposals and the report (GET /report) ------------------------------------------------------

export interface ArchitectureSketch {
  frontend: string;
  backend: string;
  database: string;
  external_services: string[];
  ai_components: string;
}

export interface SolutionProposal {
  proposal_id: string;
  round: number;
  name: string;
  summary: string;
  problem_addressed: string;
  target_users: string;
  core_features: string[];
  future_features: string[];
  user_journey: string[];
  architecture: ArchitectureSketch;
  technologies: string[];
  how_it_beats_alternatives: string;
  benefits: string[];
  drawbacks_risks: string[];
  assumptions: string[];
  difficulty: Level;
  feasibility_notes: string;
  security_privacy_notes: string;
  supporting_evidence_ids: string[];
  evidence_gaps: string[];
}

export interface ProposalScore {
  proposal_id: string;
  criterion_scores: { criterion: string; score: number; explanation: string }[];
  weighted_total: number | null;
  key_benefits: string[];
  key_drawbacks: string[];
  confidence: Level;
  confidence_reason: string;
  supporting_evidence_ids: string[];
  remaining_risks: string[];
}

export interface EvidenceRef {
  evidence_id: string;
  title: string;
  url: string;
  verification_status: VerificationStatus;
}

export interface ProposalResult {
  proposal: SolutionProposal;
  score: ProposalScore | null;
  is_winner: boolean;
  key_evidence: EvidenceRef[];
  critic_key_objections: string[];
  verification_counts: Record<string, number>;
  verification_notes: string[];
}

export interface FinalReport {
  generated_at: string;
  original_question: string;
  project_name: string;
  confirmed_profile: Record<string, string>;
  requested_features: Record<string, string>;
  constraints: Record<string, string>;
  clarifications: Record<string, string>;
  assumptions: string[];
  research_methodology: string;
  overview: string;
  winner: ProposalResult | null;
  alternatives: ProposalResult[];
  no_winner_reason: string;
  why_this_solution: string[];
  is_conditional: boolean;
  uncertainties: string[];
  unsupported_claims: string[];
  unresolved_questions: string[];
  next_steps: string[];
  risk_flags: string[];
  withdrawn_risk_flags: string[];
  disclaimer: string;
}

// --- problem statement + solution brief (GET /api/decisions/{id}/brief) ----------------------------

/** Where a statement comes from. verified = checked against its source by the Evidence Checker. */
export type ClaimLabel = "verified" | "research_backed" | "user_provided" | "recommendation" | "assumption";

export interface BriefItem {
  text: string;
  label: ClaimLabel;
  evidence_ids: string[];
}

export interface NonFunctionalRequirement extends BriefItem {
  category: string; // performance | security | privacy | reliability | accessibility | scalability | ...
}

export interface TechnologyChoice {
  name: string;
  purpose: string;
  label: ClaimLabel;
  evidence_ids: string[];
  required_by_user: boolean;
}

export interface SuccessCriterion {
  metric: string;
  target: string | null; // null = no baseline to justify a number
  basis: "user_requirement" | "evidence" | "none";
  evaluation_method: string;
  evidence_ids: string[];
}

export interface BriefRisk {
  risk: string;
  category: string;
  mitigation: string;
  evidence_ids: string[];
}

export interface BriefReference {
  number: number;
  evidence_id: string;
  title: string;
  url: string;
  domain: Domain;
  source_type: string;
  verification_status: VerificationStatus;
  cited_in: string[];
}

export interface ProblemBrief {
  project_name: string;
  revision: number;
  generated_at: string;
  project_overview: { proposed_name: string; description: string; audience: BriefItem[]; context: BriefItem };
  problem_statement: {
    statement: BriefItem;
    who_and_context: BriefItem;
    current_alternatives: BriefItem[];
    gap: BriefItem;
    consequences: BriefItem[];
    indicators: BriefItem[];
  };
  research_findings: {
    apps_and_feedback: BriefItem[];
    papers_and_literature: BriefItem[];
    feasibility_and_implementations: BriefItem[];
    limitations_and_opportunity: BriefItem[];
    evidence_gaps: string[];
  };
  proposed_solution: {
    how_it_addresses_problem: BriefItem;
    mvp_features: string[];
    future_enhancements: string[];
    user_journey: string[];
    why_this_approach: BriefItem[];
  };
  requirements: {
    functional: BriefItem[];
    non_functional: NonFunctionalRequirement[];
    integrations_and_data: string[];
    user_roles: string[];
    acceptance_criteria: string[];
  };
  architecture: {
    overview: BriefItem;
    components: { name: string; responsibility: string }[];
    data_flow: string;
    technologies: TechnologyChoice[];
    key_decisions: BriefItem[];
  };
  scope: { in_scope: string[]; out_of_scope: string[]; deliverables: string[]; dependencies: BriefItem[] };
  success_criteria: SuccessCriterion[];
  constraints_and_risks: { constraints: BriefItem[]; assumptions: string[]; unresolved_questions: string[]; risks: BriefRisk[] };
  references: BriefReference[]; // assembled by the backend from the cited evidence ids
}

export interface ValidationCheck {
  check_id: string;
  source: "deterministic" | "llm";
  passed: boolean;
  severity: Level;
  issue: string;
  fix_instruction: string;
}

export interface BriefValidation {
  verdict: "approve" | "revise" | "clarify";
  reason: string;
  revision: number;
  brief_generated_at: string | null;
  checks: ValidationCheck[];
  word_count: number;
  word_budget: number;
  clarification_questions: string[];
  open_issues: string[];
  llm_summary: string;
  validated_at: string;
}

export interface BriefResponse {
  thread_id: string;
  workflow_status: string | null;
  brief: ProblemBrief;
  markdown: string; // main part (~1 page), references, appendix
  validation: BriefValidation;
  approved_at: string | null; // set once the user approved exactly this brief
  review_round: number; // change requests so far
}

// --- implementation plan (GET /api/decisions/{id}/plan) ------------------------------------------

export interface PlanTask {
  id: string; // T1, T2, ...
  phase: string;
  title: string;
  description: string;
  depends_on: string[];
  files: string[];
  acceptance_criteria: string[];
  verify_commands: string[];
}

/** How the build check installs, tests, builds and previews the app (all checked against the sandbox policy). */
export interface PlanCommands {
  install: string[];
  test: string[];
  build: string[];
  dev: string;
}

export interface ImplementationPlan {
  summary: string;
  tech_stack: string[];
  project_structure: string[];
  dependencies: string[];
  architecture: string;
  data_model: string;
  api_endpoints: string[];
  frontend_components: string[];
  backend_services: string[];
  integrations: string[];
  ai_components: string;
  phases: { id: string; name: string; goal: string }[];
  tasks: PlanTask[];
  feature_coverage: { feature: string; task_ids: string[] }[];
  testing_strategy: string[];
  commands: PlanCommands;
  risks_and_decisions: string[];
}

/** done = the task's verify commands passed in the sandbox (never the agent's own claim). */
export type TaskStatus = "pending" | "done" | "failed" | "blocked" | "skipped";

export interface VerifyResult {
  command: string;
  ok: boolean;
  exit_code: number | null;
  summary: string;
  output: string;
}

export interface TaskResult {
  attempt: number;
  passed: boolean;
  files_changed: string[];
  verify: VerifyResult[];
  agent: { ok: boolean; error: string | null; turns: number; cost_usd: number; seconds: number; commands: number; report: string };
}

export interface ImplementationTask {
  id: string; // T1.. plan tasks, F1.. build fixes, C1.. change requests
  title: string;
  phase: string;
  depends_on: string[];
  status: TaskStatus;
  attempts: number;
  result: TaskResult | { reason: string } | null;
}

export interface ImplementationResponse {
  thread_id: string;
  workflow_status: string | null;
  workspace_dir: string | null;
  current_task_id: string | null;
  tasks: ImplementationTask[];
  log: { task_id: string; attempt: number; ok: boolean; status: TaskStatus; summary: string; cost_usd: number; at: string }[];
  cost_usd: number;
  build: BuildResults | null;
}

/** Totals of usage_events rows (one per node run with model calls / per Ask reply). */
export interface UsageTotals {
  runs: number;
  calls: number;
  failed_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number;
  seconds: number;
  node_failures: number;
}

/** GET /api/metrics?days=N (M11): the builder's own usage and tool outcomes across projects. */
export interface MetricsResponse {
  since: string;
  days: number;
  total: UsageTotals & { sessions: number };
  by_node: (UsageTotals & { node: string })[];
  by_day: (UsageTotals & { day: string })[];
  calls_by_model: Record<string, number>;
  tools: { source: "agent" | "sandbox" | "chat" | "search"; tool: string; calls: number; failed: number; refused: number; timed_out: number; avg_seconds: number }[];
  agent: { sessions?: number; cost_usd?: number };
}

/** One metered step: a graph node's model calls ("llm") or one coding-agent task attempt ("agent"). */
export interface UsageStep {
  kind: "llm" | "agent";
  node: string;
  phase: string;
  at: string;
  cost_usd: number;
  calls?: number;
  tokens?: { input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number };
  seconds?: number;
  models?: Record<string, number>;
  error?: string | null;
  task_id?: string;
  attempt?: number;
  ok?: boolean;
}

export interface CostSplit {
  llm_usd: number;
  agent_usd: number;
  total_usd: number;
}

/** GET /api/decisions/{id}/usage (M11): what the session cost, per phase, for the first build and per change. */
export interface UsageResponse {
  thread_id: string;
  total_usd: number;
  llm_usd: number; // the builder's own model calls (measured since M11)
  agent_usd: number; // the coding agent (Agent SDK cost per attempt)
  ask_usd: number | null;
  llm_budget_usd: number;
  agent_budget_usd: number;
  llm_measured_since: string | null; // null = the builder's calls were never measured (session from before M11)
  unpriced_models: string[];
  prices_as_of: string;
  phases: ({ phase: string } & CostSplit)[];
  first_build: CostSplit;
  changes: ({ round: number; action: "change" | "replan"; request: string; at: string; tasks: string[] } & CostSplit)[];
  steps: UsageStep[];
}

export interface PreviewResponse extends PreviewInfo {
  thread_id: string;
  log_tail: string;
  started_at: string | null;
  ready_at: string | null;
}

export interface PlanResponse {
  thread_id: string;
  workflow_status: string | null;
  plan: ImplementationPlan;
  markdown: string;
  revision: number;
  model: string;
  approved_at: string | null; // set once the user approved exactly this plan
  tasks: ImplementationTask[];
}

// --- code export (GET /code, /code.zip) ------------------------------------------------------------

/** The generated project's files for "Download code" (node_modules, build output, .git, .env* left out). */
export interface CodeExportResponse {
  thread_id: string;
  folder_name: string; // e.g. "simple-calculator-web-app"
  total_bytes: number;
  skipped: string[]; // what was left out, with the reason
  files: { path: string; content_b64: string }[];
}

// --- approved versions (GET /artifacts) -----------------------------------------------------------

export interface ArtifactView {
  kind: "brief" | "plan";
  version: number;
  content_hash: string;
  approved_at: string | null;
  created_at: string;
  markdown: string;
}

export interface ArtifactList {
  thread_id: string;
  artifacts: ArtifactView[];
}

export interface ReportResponse {
  thread_id: string;
  workflow_status: string;
  report: FinalReport;
}

// --- builder chat (backend api/chat.py) ----------------------------------------------------------

/** The short message that ends the research phase (built from the report, backend chat.summary_from_report). */
export interface OnboardingSummary {
  opening: string;
  details: string; // markdown
  invitation: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

/** One reply of the user to a brief or plan review. */
export interface ReviewTurn {
  kind: "brief" | "plan";
  round: number;
  action: "approve" | "request_changes";
  feedback: string;
  target: string | null; // brief only: where the change went
  at: string;
}

/** One reply at the change-request pause, with the C<n> task it created (change only). */
export interface ChangeTurn {
  round: number;
  action: "change" | "replan" | "finish";
  request: string;
  at: string;
  task_id: string | null;
  task_status: TaskStatus | null;
  cost_usd: number | null; // model calls + coding agent until the next reply at the change pause (M11)
}

/** GET /api/chats/{thread_id}: the whole conversation of a builder session (the pauses themselves come from the status). */
export interface ChatTranscript {
  thread_id: string;
  mode: SessionMode;
  question: string | null;
  project_name: string | null;
  clarifications: { question: string; answer: string }[]; // answered questions, in order
  onboarding_summary: OnboardingSummary | null;
  ready: boolean; // the report exists: Ask mode is available
  reviews: ReviewTurn[]; // brief and plan review replies, oldest first
  changes: ChangeTurn[]; // change requests, oldest first
  messages: ChatMessage[]; // Ask-mode messages, oldest first
}
