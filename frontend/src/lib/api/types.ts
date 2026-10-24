// TypeScript mirror of the backend's API models (backend/src/ai_decision_arena/api/schemas.py
// and the parts of schemas.py they include). Written by hand: if a backend model changes, change it here too.

// --- session status (GET /api/decisions/{thread_id}) ---------------------------------------------

/** What the HTTP layer knows about a session (not the graph's own status). */
export type RunState = "running" | "paused" | "interrupted" | "finished";

export type PauseType = "clarification";

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

/** `type` tells which payload it is (TypeScript narrows on it: if (p.type === "clarification") ...). */
export type PendingPause = { type: "clarification"; payload: ClarificationPayload };

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
  care_plans: number;
  claims_checked: number;
}

export interface DecisionStatus {
  thread_id: string;
  run_state: RunState;
  workflow_status: string | null; // intake, researching, debating, completed, ...
  question: string | null;
  condition_name: string | null;
  red_flags: string[];
  pending: PendingPause | null;
  progress: ProgressLine[]; // lost when the server restarts
  error: ErrorInfo | null;
  has_report: boolean;
  current_node: string | null; // last node that finished
  next_nodes: string[]; // while running, [0] is the node in progress
  started_at: string | null;
  active_seconds: number;
  counters: Counters;
}

// --- live snapshot (GET /live): everything produced so far -----------------------------------

export interface CaseView {
  condition_name: string | null;
  condition_category: string | null;
  case_summary: string | null;
  user_context: string;
  health_profile: Record<string, string>;
  symptoms: Record<string, string>;
  constraints: Record<string, string>;
  missing_information: string[];
  assumptions: string[];
  clarification_answers: Record<string, string>;
  red_flags: string[];
  withdrawn_red_flags: { flag: string; reason: string }[];
}

export interface ResearchView {
  passes: number;
  queries: string[];
  evidence_by_perspective: Record<string, number>;
  evidence_gaps: string[];
  conflicting_claims: { topic: string; evidence_ids: string[]; description: string }[];
  rejected_count: number;
  perspective_summaries: Record<string, string>;
  research_focus: string[];
}

export type Level = "low" | "medium" | "high";

export interface CriticismPoint {
  category: string;
  issue: string;
  severity: Level;
  basis: "evidence" | "clinical_reasoning";
  is_verified_problem: boolean;
  evidence_ids: string[];
  suggested_improvement: string;
}

export interface Criticism {
  plan_id: string;
  points: CriticismPoint[];
  overall_assessment: string;
}

export interface Verdict {
  decision: "proceed" | "request_more_research" | "request_clarification" | "insufficient_evidence";
  reason: string;
  winning_plan_ids: Record<string, string>;
  perspective_status: Record<string, string>; // sufficient | insufficient | no_plans | declined
  required_evidence: string[];
  clarification_questions: string[];
}

export interface DebateView {
  round: number;
  care_plans: CarePlan[];
  criticisms: Criticism[];
  scores: PlanScore[];
  verdict: Verdict | null;
  lane_status: Record<string, string>;
  proposer_notes: Record<string, string>;
}

export interface ClaimVerification {
  claim: string;
  plan_id: string | null;
  perspective: string;
  evidence_ids: string[];
  status: VerificationStatus;
  notes: string;
  is_anecdotal: boolean;
  is_material: boolean;
}

export interface CheckerVerdict {
  decision: string;
  reason: string;
  gaps_by_lane: Record<string, string[]>;
  summaries: Record<string, string>;
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

/** "full" = admin view (every pause), "quick" = patient chat (fast, no pauses after the questions). */
export type SessionMode = "full" | "quick";

export interface SessionSummary {
  thread_id: string;
  question: string;
  mode: SessionMode;
  condition_name: string | null;
  status: string;
  red_flag_count: number;
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
  | { type: "continue" };

// --- evidence (GET /evidence) --------------------------------------------------------------------

export type Perspective = "research" | "doctor" | "patient";

export type VerificationStatus =
  | "pending"
  | "verified"
  | "partially_supported"
  | "unsupported"
  | "contradicted"
  | "irrelevant"
  | "unavailable";

export interface Evidence {
  evidence_id: string;
  perspective: Perspective;
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
  patient_context: { is_recurring: boolean; experience_described: string } | null;
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

// --- final report (GET /report) ------------------------------------------------------------------

export interface CarePlan {
  plan_id: string;
  perspective: Perspective;
  round: number;
  name: string;
  summary: string;
  daily_routine: string[];
  diet: string[];
  medications_treatments: string[];
  expected_timeline: string;
  prevalence_and_outlook: string;
  benefits: string[];
  drawbacks_risks: string[];
  assumptions: string[];
  difficulty: Level;
  safety_notes: string;
  supporting_evidence_ids: string[];
  evidence_gaps: string[];
}

export interface PlanScore {
  plan_id: string;
  criterion_scores: { criterion: string; score: number; explanation: string }[];
  weighted_total: number | null;
  key_benefits: string[];
  key_drawbacks: string[];
  confidence: Level;
  confidence_reason: string;
  supporting_evidence_ids: string[];
  remaining_risks: string[];
}

export interface PerspectiveResult {
  perspective: Perspective;
  plan: CarePlan | null;
  score: PlanScore | null;
  key_evidence: { evidence_id: string; title: string; url: string; verification_status: VerificationStatus }[];
  critic_key_objections: string[];
  verification_counts: Record<string, number>;
  verification_notes: string[];
  unavailable_reason: string;
}

export interface FinalReport {
  generated_at: string;
  original_question: string;
  condition_name: string;
  confirmed_profile: Record<string, string>;
  symptoms: Record<string, string>;
  constraints: Record<string, string>;
  clarifications: Record<string, string>;
  assumptions: string[];
  research_methodology: string;
  overview: string;
  perspectives: PerspectiveResult[];
  where_perspectives_agree: string[];
  where_perspectives_differ: string[];
  is_conditional: boolean;
  uncertainties: string[];
  unsupported_claims: string[];
  unresolved_questions: string[];
  next_steps: string[];
  red_flags: string[];
  withdrawn_red_flags: string[];
  disclaimer: string;
}

export interface ReportResponse {
  thread_id: string;
  workflow_status: string;
  report: FinalReport;
}

// --- patient chat (backend api/chat.py) ------------------------------------------------------------

/** The short message that ends onboarding (backend schemas.OnboardingSummary). */
export interface OnboardingSummary {
  opening: string;
  doctors_say: string;
  patients_say: string;
  research_says: string;
  invitation: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

/** GET /api/chats/{thread_id}: the onboarding so far and the chat messages after it. */
export interface ChatTranscript {
  thread_id: string;
  mode: SessionMode;
  question: string | null;
  condition_name: string | null;
  clarifications: { question: string; answer: string }[]; // answered onboarding questions, in order
  onboarding_summary: OnboardingSummary | null;
  ready: boolean; // the report exists: the patient can chat
  messages: ChatMessage[];
}
