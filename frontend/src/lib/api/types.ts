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

/** "full" = admin view (every pause), "quick" = fast profile (fewer searches, one proposal). */
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
}

export interface ReportResponse {
  thread_id: string;
  workflow_status: string;
  report: FinalReport;
}

// --- project chat (backend api/chat.py) ----------------------------------------------------------

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

/** GET /api/chats/{thread_id}: the onboarding so far and the chat messages after it. */
export interface ChatTranscript {
  thread_id: string;
  mode: SessionMode;
  question: string | null;
  project_name: string | null;
  clarifications: { question: string; answer: string }[]; // answered questions, in order
  onboarding_summary: OnboardingSummary | null;
  ready: boolean; // the report exists: the user can chat
  messages: ChatMessage[];
}
