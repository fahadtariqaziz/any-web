// The patient chat hides the agents' details: while they work, it only shows one short label, like
// "Researching…". This maps the graph node that is running to that label.

import type { DecisionStatus } from "@/lib/api/types";

export function stageLabel(status: DecisionStatus | null): string {
  if (!status) return "Getting to know you";
  // While running, next_nodes[0] is the node in progress; current_node is the last one that finished.
  const node = status.next_nodes[0] ?? status.current_node ?? "";
  switch (node) {
    case "intake":
      return "Getting to know you";
    case "clarification":
      return status.counters.clarification_rounds > 0 ? "Understanding your answers" : "Getting to know you";
    case "research":
      return "Researching";
    case "proposer":
    case "critic":
      return "Planning";
    case "judge":
    case "evidence_checker":
      return "Judging";
    case "final_report":
    case "completion":
      return "Writing your summary";
    default:
      return "Thinking";
  }
}

/** Seconds since the current run segment started: after the last pause, else the first progress line. */
export function runSeconds(status: DecisionStatus | null, now: number): number | null {
  const lines = status?.progress ?? [];
  if (lines.length === 0) return null; // the server restarted: progress lines are in memory only
  let start = lines[0].at;
  lines.forEach((line, i) => {
    if (line.message.startsWith("paused:") && lines[i + 1]) start = lines[i + 1].at;
  });
  return Math.max(0, Math.round((now - Date.parse(start)) / 1000));
}
