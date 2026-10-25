"use client";

// Where the project is, in seven words: Idea · Research · Solution · Brief · Plan · Build · Preview. Grouped from
// the pipeline's ten stages (lib/pipeline.ts), derived from the status like the admin stepper.

import { Check } from "lucide-react";

import type { DecisionStatus } from "@/lib/api/types";
import { deriveActivity, type StageId, type StageState, stageStates } from "@/lib/pipeline";

const GROUPS: { label: string; stages: StageId[] }[] = [
  { label: "Idea", stages: ["intake", "clarify"] },
  { label: "Research", stages: ["research"] },
  { label: "Solution", stages: ["debate", "verify", "report"] },
  { label: "Brief", stages: ["brief"] },
  { label: "Plan", stages: ["plan"] },
  { label: "Build", stages: ["build"] },
  { label: "Preview", stages: ["preview"] },
];

function groupState(states: StageState[]): StageState {
  if (states.includes("failed")) return "failed";
  if (states.includes("current")) return "current";
  if (states.every((s) => s === "done" || s === "skipped")) return "done";
  return "upcoming";
}

export function StageChips({ status }: { status: DecisionStatus }) {
  const states = stageStates(status, deriveActivity(status));
  const waiting = status.run_state === "paused";
  return (
    <ol className="flex items-center gap-0.5 overflow-x-auto" aria-label="Progress">
      {GROUPS.map((g) => {
        const state = groupState(g.stages.map((s) => states[s]));
        const style =
          state === "done"
            ? "bg-emerald-50 text-emerald-700"
            : state === "current"
              ? waiting
                ? "bg-amber-100 text-amber-800 ring-1 ring-amber-300"
                : "bg-brand-soft text-brand-strong ring-1 ring-teal-300"
              : state === "failed"
                ? "bg-red-50 text-red-700"
                : "bg-slate-100 text-slate-400";
        return (
          <li key={g.label} aria-current={state === "current" ? "step" : undefined} className={`inline-flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-medium ${style}`}>
            {state === "done" && <Check className="size-2.5" aria-hidden />}
            {g.label}
          </li>
        );
      })}
    </ol>
  );
}
