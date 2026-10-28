// The builder chat keeps the agents' details out of the conversation: while they work, it shows one short label
// ("Researching…") and the newest progress line. This maps the graph node that is running to that label; the
// full detail is in the right pane's Activity tab.

import type { DecisionStatus } from "@/lib/api/types";

export function stageLabel(status: DecisionStatus | null): string {
  if (!status) return "Getting to know your idea";
  // While running, next_nodes[0] is the node in progress; current_node is the last one that finished.
  const node = status.next_nodes[0] ?? status.current_node ?? "";
  switch (node) {
    case "intake":
      return "Getting to know your idea";
    case "clarification":
    case "await_clarification":
      return status.counters.clarification_rounds > 0 ? "Understanding your answers" : "Getting to know your idea";
    case "research":
      return "Researching";
    case "proposer":
    case "critic":
      return "Designing solutions";
    case "judge":
      return "Judging the solutions";
    case "final_report":
      return "Writing the summary";
    case "brief_writer":
    case "brief_validator":
      return "Writing your brief";
    case "await_brief_review":
    case "brief_review_router":
      return "Reading your review";
    case "planner":
    case "await_plan_review":
    case "plan_review_router":
      return "Planning the build";
    case "implementer":
      return "Building your app";
    case "build_check":
      return "Checking the build";
    case "preview":
      return "Starting your app";
    case "await_change_request":
    case "change_request_router":
      return "Reading your request";
    case "completion":
      return "Wrapping up";
    default:
      return "Thinking";
  }
}

/** The newest progress line that says something (not the "✔ finished" / graph bookkeeping lines). */
export function latestDetail(status: DecisionStatus | null): string | null {
  const lines = status?.progress ?? [];
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i];
    if (line.node !== "graph" && !line.message.startsWith("✔")) return line.message;
  }
  return null;
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
