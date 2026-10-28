"use client";

// Where the project is, in seven words: Idea · Research · Solution · Brief · Plan · Build · Preview. Grouped from
// the pipeline's nine stages (lib/pipeline.ts), derived from the status like the admin stepper. The current chip
// glows (gradient) and pulses softly while the agents work; amber while the builder waits for the user.

import { Check } from "lucide-react";
import { motion } from "motion/react";

import type { DecisionStatus } from "@/lib/api/types";
import { deriveActivity, type StageId, type StageState, stageStates } from "@/lib/pipeline";

const GROUPS: { label: string; stages: StageId[] }[] = [
  { label: "Idea", stages: ["intake", "clarify"] },
  { label: "Research", stages: ["research"] },
  { label: "Solution", stages: ["debate", "report"] },
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
  const working = status.run_state === "running";
  return (
    <ol className="flex items-center gap-1 overflow-x-auto" aria-label="Progress">
      {GROUPS.map((g) => {
        const state = groupState(g.stages.map((s) => states[s]));
        const style =
          state === "done"
            ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/70"
            : state === "current"
              ? waiting
                ? "bg-amber-100 text-amber-800 ring-1 ring-amber-300"
                : "bg-gradient-to-r from-indigo-500 to-fuchsia-500 text-white shadow-[0_6px_14px_-6px_rgb(124_58_237_/_0.9)]"
              : state === "failed"
                ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                : "bg-slate-100 text-slate-400";
        return (
          <motion.li
            key={g.label}
            layout
            aria-current={state === "current" ? "step" : undefined}
            animate={state === "current" && working ? { scale: [1, 1.04, 1] } : { scale: 1 }}
            transition={state === "current" && working ? { duration: 1.8, repeat: Infinity, ease: "easeInOut" } : { duration: 0.2 }}
            className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${style}`}
          >
            {state === "done" && <Check className="size-2.5" aria-hidden />}
            {g.label}
          </motion.li>
        );
      })}
    </ol>
  );
}
