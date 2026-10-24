// The pipeline as the USER sees it: 7 stages built from the graph's 13 nodes, plus what each node is
// doing in plain words and how long it usually takes (timings observed in the handoff's test runs).
// Everything here is derived from DecisionStatus; nothing is guessed when the backend knows better.

import type { DecisionStatus, Perspective, ProgressLine } from "@/lib/api/types";

export type StageId = "intake" | "clarify" | "research" | "debate" | "verify" | "report";

export interface Stage {
  id: StageId;
  label: string;
  blurb: string; // one line under the label in the stepper
}

export const STAGES: Stage[] = [
  { id: "intake", label: "Intake", blurb: "Understanding your message" },
  { id: "clarify", label: "Questions", blurb: "A few questions for you" },
  { id: "research", label: "Research", blurb: "Three lanes of evidence" },
  { id: "debate", label: "Debate", blurb: "Propose, critique, judge" },
  { id: "verify", label: "Verification", blurb: "Claims checked at source" },
  { id: "report", label: "Report", blurb: "One plan per perspective" },
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
    headline: "Understanding your message",
    doing: "Reading what you wrote and extracting the facts you stated: the condition, symptoms, current treatments, constraints, and any emergency warning signs.",
    expectedSeconds: 6,
    stage: "intake",
  },
  clarification: {
    label: "Clarification",
    headline: "Working out what to ask you",
    doing: "Deciding which questions would change the research for your situation, and merging the answers you gave into your profile.",
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
    headline: "Researching your condition from three perspectives",
    doing: "Planning three web searches per lane (research papers, clinical guidance, patient communities), running them in parallel, then reading every result and keeping only short, sourced evidence records.",
    expectedSeconds: 55,
    stage: "research",
  },
  proposer: {
    label: "Proposer",
    headline: "Drafting care plans",
    doing: "Each lane builds two or three care plans from its own evidence only, so the three perspectives stay distinct. Every plan covers routine, diet, treatments as reported, timeline and outlook.",
    expectedSeconds: 22,
    stage: "debate",
  },
  critic: {
    label: "Critic",
    headline: "Challenging every plan",
    doing: "Each plan is checked against all the evidence from the three lanes: missing considerations, safety issues, weak or outdated sources, and poor fit to your situation.",
    expectedSeconds: 45,
    stage: "debate",
  },
  judge: {
    label: "Judge",
    headline: "Scoring plans and picking winners",
    doing: "Scoring every plan on the rubric (fit to you 30%, safety 25%, evidence quality 20%, practicality 15%, completeness 10%) and choosing one winner per lane. It may send the agents back for more research or ask you a question.",
    expectedSeconds: 16,
    stage: "debate",
  },
  evidence_checker: {
    label: "Evidence check",
    headline: "Verifying claims against their sources",
    doing: "Re-reading the sources the three winning plans cite and marking each claim as verified, partially supported, unsupported or contradicted. Material gaps can trigger one focused research pass.",
    expectedSeconds: 25,
    stage: "verify",
  },
  final_report: {
    label: "Report writer",
    headline: "Writing your report",
    doing: "Assembling the three winning plans with their scores and evidence, then writing the overview, where the perspectives agree and differ, the uncertainties and the next steps.",
    expectedSeconds: 12,
    stage: "report",
  },
  completion: {
    label: "Saving",
    headline: "Saving your session",
    doing: "Storing the session, the evidence and the report in the database.",
    expectedSeconds: 2,
    stage: "report",
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
    activeNode = "await_clarification";
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
  const current = activity.activeStage ?? (finished ? "report" : "intake");
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
  lanes: Record<Perspective, LaneState> | null;
  fraction: number | null; // 0..1 when the node reports countable sub-steps
}

const PERSPECTIVES: Perspective[] = ["research", "doctor", "patient"];

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
    const searchesDone = msgs.filter((m) => /^\[(research|doctor|patient)\] (\d+ results|search failed)/.test(m)).length;
    const extracting = msgs.some((m) => /unique results/.test(m));
    const lanes = Object.fromEntries(PERSPECTIVES.map((p) => [p, "waiting"])) as Record<Perspective, LaneState>;
    if (extracting) {
      for (const p of PERSPECTIVES) lanes[p] = msgs.some((m) => m.startsWith(`${p} lane: kept`)) ? "done" : "working";
      const done = PERSPECTIVES.filter((p) => lanes[p] === "done").length;
      return { summary: `Reading results: ${done} of 3 lanes extracted`, lanes, fraction: 0.6 + (done / 3) * 0.4 };
    }
    if (total) {
      for (const p of PERSPECTIVES) lanes[p] = msgs.some((m) => m.startsWith(`[${p}]`)) ? "working" : "waiting";
      return { summary: `Searching: ${Math.min(searchesDone, total)} of ${total} searches done`, lanes, fraction: 0.1 + Math.min(searchesDone / total, 1) * 0.5 };
    }
    return { summary: "Planning the searches", lanes: null, fraction: 0.05 };
  }

  if (["proposer", "critic", "judge", "evidence_checker"].includes(node)) {
    const lanes = Object.fromEntries(PERSPECTIVES.map((p) => [p, "working"])) as Record<Perspective, LaneState>;
    for (const p of PERSPECTIVES) if (msgs.some((m) => m.startsWith(`${p} lane:`))) lanes[p] = "done";
    const done = PERSPECTIVES.filter((p) => lanes[p] === "done").length;
    const decided = msgs.some((m) => m.startsWith("decision:"));
    if (decided) return { summary: "Decision made", lanes, fraction: 1 };
    return { summary: `${done} of 3 lanes finished`, lanes, fraction: done / 3 };
  }

  return none;
}
