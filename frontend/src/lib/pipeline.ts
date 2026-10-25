// The pipeline as the USER sees it: 9 stages built from the graph's 18 nodes, plus what each node is
// doing in plain words and how long it usually takes (timings observed in the handoff's test runs).
// Everything here is derived from DecisionStatus; nothing is guessed when the backend knows better.

import type { DecisionStatus, Domain, ProgressLine } from "@/lib/api/types";

export type StageId = "intake" | "clarify" | "research" | "debate" | "verify" | "report" | "brief" | "plan" | "build";

export interface Stage {
  id: StageId;
  label: string;
  blurb: string; // one line under the label in the stepper
}

export const STAGES: Stage[] = [
  { id: "intake", label: "Intake", blurb: "Understanding your idea" },
  { id: "clarify", label: "Questions", blurb: "A few questions for you" },
  { id: "research", label: "Research", blurb: "Three domains of evidence" },
  { id: "debate", label: "Debate", blurb: "Propose, critique, judge" },
  { id: "verify", label: "Verification", blurb: "Winner's claims checked at source" },
  { id: "report", label: "Report", blurb: "Winner, alternatives, open questions" },
  { id: "brief", label: "Brief", blurb: "Problem statement and solution, validated" },
  { id: "plan", label: "Plan", blurb: "Implementation plan for your approval" },
  { id: "build", label: "Build", blurb: "Coding agent, task by task, checked by tests" },
];

export interface NodeInfo {
  label: string; // short agent name
  headline: string; // big sentence in the "now" panel
  doing: string; // what the agent is doing, in plain words
  expectedSeconds: number; // 0 = waits for the user
  stage: StageId;
  waitsForUser?: boolean;
}

export const NODE_INFO: Record<string, NodeInfo> = {
  intake: {
    label: "Intake",
    headline: "Understanding your idea",
    doing: "Reading what you wrote and extracting the facts you stated: the idea, who it is for, the requested features, constraints, and any risky aspects.",
    expectedSeconds: 6,
    stage: "intake",
  },
  clarification: {
    label: "Clarification",
    headline: "Working out what to ask you",
    doing: "Deciding which questions would change the research or the solution, and merging the answers you gave into the project facts.",
    expectedSeconds: 9,
    stage: "clarify",
  },
  await_clarification: {
    label: "Your answers",
    headline: "Recording your answers",
    doing: "Handing your answers to the clarification agent.",
    expectedSeconds: 2,
    stage: "clarify",
    waitsForUser: true,
  },
  research: {
    label: "Research",
    headline: "Researching your idea in three domains",
    doing: "Planning web searches for three domains (existing apps and user feedback, research papers, technical feasibility), running them in parallel, then reading every result and keeping only short, sourced evidence records.",
    expectedSeconds: 55,
    stage: "research",
  },
  proposer: {
    label: "Proposer",
    headline: "Designing solution proposals",
    doing: "Designing two or three meaningfully different solutions from all the evidence: the problem addressed, first-version features, user journey, architecture, technologies, and how each beats the existing alternatives.",
    expectedSeconds: 40,
    stage: "debate",
  },
  critic: {
    label: "Critic",
    headline: "Challenging every proposal",
    doing: "Each proposal is checked against all the evidence and your requirements: unsupported claims, ignored constraints, copies of existing apps, feasibility, security and scope.",
    expectedSeconds: 35,
    stage: "debate",
  },
  judge: {
    label: "Judge",
    headline: "Scoring proposals and picking the strongest",
    doing: "Scoring every proposal on the rubric (requirements alignment 30%, problem relevance 20%, evidence quality 20%, feasibility 20%, completeness 10%) and choosing the winner. It may send the agents back for more research or ask you a question.",
    expectedSeconds: 30,
    stage: "debate",
  },
  evidence_checker: {
    label: "Evidence check",
    headline: "Verifying the winner's claims against their sources",
    doing: "Re-reading the sources the winning proposal cites and marking each claim as verified, partially supported, unsupported or contradicted. Material gaps can trigger one focused research pass.",
    expectedSeconds: 25,
    stage: "verify",
  },
  final_report: {
    label: "Report writer",
    headline: "Writing the summary",
    doing: "Assembling the winning proposal, the alternatives, the scores and the verified evidence, then writing the overview, why this solution, the uncertainties and the next steps.",
    expectedSeconds: 15,
    stage: "report",
  },
  brief_writer: {
    label: "Brief writer",
    headline: "Writing the problem statement and solution brief",
    doing: "Writing a one-page brief from your requirements and the research: the problem, the evidence, the proposed solution, requirements, architecture, scope, success criteria and risks. Every statement says whether it is verified, research-backed, from you, a recommendation or an assumption; the references are added from the cited evidence.",
    expectedSeconds: 60,
    stage: "brief",
  },
  brief_validator: {
    label: "Brief validator",
    headline: "Checking the brief before you see it",
    doing: "Checking that every cited source exists, numbers have a basis, every section is filled and the brief fits about one page, then reviewing it on nine criteria (clear problem, no copy of existing apps, supported recommendations, feasibility, MVP scope, measurable success, disclosed risks, sourced claims, readability). It may ask the writer to revise or ask you a question.",
    expectedSeconds: 20,
    stage: "brief",
  },
  await_brief_review: {
    label: "Your review",
    headline: "Waiting for your review of the brief",
    doing: "The validated brief is shown to you. Approve it, or say what to change: a misunderstood requirement goes back to the questions, missing facts to research, a different solution to the proposer, wording to the writer. Nothing is planned or built before you approve.",
    expectedSeconds: 0,
    stage: "brief",
    waitsForUser: true,
  },
  brief_review_router: {
    label: "Review router",
    headline: "Applying your review",
    doing: "Recording your approval, or deciding which step must handle your change request.",
    expectedSeconds: 3,
    stage: "brief",
  },
  planner: {
    label: "Planner",
    headline: "Writing the implementation plan",
    doing: "A larger model (Claude Opus) turns the approved brief into a step-by-step plan for the coding agent: technology, project structure, architecture, phases and small tasks, each with the files it touches, how it is checked and the commands that prove it works. Every MVP feature of the brief must be covered by a task.",
    expectedSeconds: 180,
    stage: "plan",
  },
  await_plan_review: {
    label: "Your plan review",
    headline: "Waiting for your review of the plan",
    doing: "Approve the plan to continue, or say what to change. Nothing is built before you approve.",
    expectedSeconds: 0,
    stage: "plan",
    waitsForUser: true,
  },
  plan_review_router: {
    label: "Plan review",
    headline: "Applying your plan review",
    doing: "Recording your approval, or sending your change request back to the planner.",
    expectedSeconds: 3,
    stage: "plan",
  },
  implementer: {
    label: "Coding agent",
    headline: "Building your app, one task at a time",
    doing: "A coding agent (Claude Sonnet) implements the next task of the approved plan inside this session's own project folder. Then the builder itself runs the task's test commands: a task counts as done only when they pass. A failing task is retried once with the error output.",
    expectedSeconds: 180,
    stage: "build",
  },
  completion: {
    label: "Saving",
    headline: "Saving your session",
    doing: "Storing the session, the evidence and the report in the database.",
    expectedSeconds: 2,
    stage: "build",
  },
};

const STAGE_INDEX: Record<StageId, number> = Object.fromEntries(STAGES.map((s, i) => [s.id, i])) as Record<StageId, number>;

const NODE_LABEL_FALLBACK = (node: string) => node.replace(/_/g, " ");

export function nodeLabel(node: string): string {
  return NODE_INFO[node]?.label ?? NODE_LABEL_FALLBACK(node);
}

/** Which user-facing stage a node belongs to. Unknown nodes (e.g. "graph") map to null. */
export function nodeStage(node: string | null | undefined): StageId | null {
  if (!node) return null;
  return NODE_INFO[node]?.stage ?? null;
}

// --- what is happening right now --------------------------------------------------------------

export interface Activity {
  activeNode: string | null; // node in progress (running), waiting (paused) or next (interrupted)
  activeStage: StageId | null;
  stageStartedAt: string | null; // ISO time of the first progress line of the active node, if any
  lastLine: ProgressLine | null;
  finishedCount: number; // "✔ finished" lines: changes exactly when a node finishes
}

/** The last progress line that is not a system ("graph") line. */
function lastNodeLine(lines: ProgressLine[]): ProgressLine | null {
  for (let i = lines.length - 1; i >= 0; i--) if (lines[i].node !== "graph") return lines[i];
  return null;
}

export function deriveActivity(status: DecisionStatus): Activity {
  const lines = status.progress;
  const lastLine = lines.length ? lines[lines.length - 1] : null;
  const finishedCount = lines.filter((l) => l.message.startsWith("✔")).length;

  let activeNode: string | null = null;
  if (status.run_state === "running") {
    // The checkpoint says which node LangGraph is executing; before the first checkpoint it is intake.
    activeNode = status.next_nodes[0] ?? lastNodeLine(lines)?.node ?? "intake";
  } else if (status.run_state === "paused") {
    const pauseNode = { clarification: "await_clarification", brief_review: "await_brief_review", plan_review: "await_plan_review" };
    activeNode = status.next_nodes[0] ?? (status.pending ? pauseNode[status.pending.type] : "await_clarification");
  } else if (status.run_state === "interrupted") {
    activeNode = status.next_nodes[0] ?? null;
  } else {
    activeNode = status.current_node;
  }

  // Lines of the active node at the END of the log (its current run, not an earlier pass).
  let stageStartedAt: string | null = null;
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i];
    if (line.node === activeNode && !line.message.startsWith("✔")) stageStartedAt = line.at;
    else if (line.node !== "graph") break;
  }

  return { activeNode, activeStage: nodeStage(activeNode), stageStartedAt, lastLine, finishedCount };
}

// --- stepper states ---------------------------------------------------------------------------

export type StageState = "done" | "current" | "upcoming" | "skipped" | "failed";

export function stageStates(status: DecisionStatus, activity: Activity): Record<StageId, StageState> {
  const result = {} as Record<StageId, StageState>;
  const finished = status.run_state === "finished";
  const ws = status.workflow_status;

  if (finished && (ws === "completed" || ws === "completed_with_uncertainty")) {
    for (const s of STAGES) result[s.id] = "done";
    return result;
  }
  const current = activity.activeStage ?? (finished ? "build" : "intake");
  const currentIndex = STAGE_INDEX[current];
  for (const s of STAGES) {
    const i = STAGE_INDEX[s.id];
    result[s.id] = i < currentIndex ? "done" : i === currentIndex ? (finished && ws === "failed" ? "failed" : "current") : "upcoming";
  }
  return result;
}

// --- sub-steps inside a node, parsed from its progress lines ------------------------------------
// The messages are written by the backend nodes (progress.report); the patterns below mirror them.

export type LaneState = "waiting" | "working" | "done";

export interface SubProgress {
  summary: string | null; // e.g. "6 of 9 searches done"
  lanes: Record<Domain, LaneState> | null;
  fraction: number | null; // 0..1 when the node reports countable sub-steps
}

const DOMAINS: Domain[] = ["apps", "papers", "tech"];

function activeLines(lines: ProgressLine[], node: string | null): ProgressLine[] {
  const out: ProgressLine[] = [];
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i];
    if (line.node === node && !line.message.startsWith("✔")) out.unshift(line);
    else if (line.node !== "graph") break;
  }
  return out;
}

export function subProgress(lines: ProgressLine[], node: string | null): SubProgress {
  const mine = activeLines(lines, node);
  const none: SubProgress = { summary: null, lanes: null, fraction: null };
  if (!node || mine.length === 0) return none;
  const msgs = mine.map((l) => l.message);

  if (node === "research") {
    const planned = msgs.map((m) => /planned (\d+) searches/.exec(m)).find(Boolean);
    const total = planned ? Number(planned[1]) : null;
    const searchesDone = msgs.filter((m) => /^\[(apps|papers|tech)\] (\d+ results|search failed)/.test(m)).length;
    const extracting = msgs.some((m) => /unique results/.test(m));
    const lanes = Object.fromEntries(DOMAINS.map((p) => [p, "waiting"])) as Record<Domain, LaneState>;
    if (extracting) {
      for (const p of DOMAINS) lanes[p] = msgs.some((m) => m.startsWith(`${p} domain: kept`)) ? "done" : "working";
      const done = DOMAINS.filter((p) => lanes[p] === "done").length;
      return { summary: `Reading results: ${done} of 3 domains extracted`, lanes, fraction: 0.6 + (done / 3) * 0.4 };
    }
    if (total) {
      for (const p of DOMAINS) lanes[p] = msgs.some((m) => m.startsWith(`[${p}]`)) ? "working" : "waiting";
      return { summary: `Searching: ${Math.min(searchesDone, total)} of ${total} searches done`, lanes, fraction: 0.1 + Math.min(searchesDone / total, 1) * 0.5 };
    }
    return { summary: "Planning the searches", lanes: null, fraction: 0.05 };
  }

  if (["proposer", "critic", "judge", "evidence_checker"].includes(node)) {
    if (msgs.some((m) => m.startsWith("decision:"))) return { summary: "Decision made", lanes: null, fraction: 1 };
    const proposalLines = msgs.filter((m) => /^proposal_[a-c]:/.test(m)).length;
    if (proposalLines > 0) return { summary: `${proposalLines} proposal${proposalLines === 1 ? "" : "s"} done`, lanes: null, fraction: Math.min(proposalLines / 3, 0.9) };
    const designing = msgs.find((m) => /^\d+ proposal/.test(m));
    if (designing) return { summary: designing, lanes: null, fraction: 1 };
    return none;
  }

  return none;
}
