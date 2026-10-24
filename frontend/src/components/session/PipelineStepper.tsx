"use client";

// The 8-stage pipeline with the current stage highlighted. The user always knows where the agents are,
// even when the live log is empty (e.g. after a backend restart), because the states come from the checkpoint.

import { Check, Minus, X } from "lucide-react";

import type { Counters } from "@/lib/api/types";
import { STAGES, type StageId, type StageState, nodeLabel } from "@/lib/pipeline";

function detail(stage: StageId, state: StageState, activeNode: string | null, c: Counters): string {
  if (state === "current" && activeNode) return nodeLabel(activeNode);
  switch (stage) {
    case "clarify":
      return c.clarification_rounds ? `${c.clarification_rounds} round${c.clarification_rounds > 1 ? "s" : ""}` : "";
    case "research":
      return c.evidence ? `${c.evidence} sources${c.research_passes > 1 ? ` · ${c.research_passes} passes` : ""}` : "";
    case "debate":
      return c.proposals ? `${c.proposals} proposals${c.debate_round > 1 ? ` · round ${c.debate_round}` : ""}` : "";
    case "verify":
      return c.claims_checked ? `${c.claims_checked} claims` : "";
    default:
      return "";
  }
}

const RING: Record<StageState, string> = {
  done: "border-emerald-200 bg-emerald-50/60",
  current: "border-brand bg-brand-faint shadow-sm ring-2 ring-brand/20",
  upcoming: "border-slate-200 bg-white",
  skipped: "border-slate-200 bg-slate-50 opacity-70",
  failed: "border-red-300 bg-red-50",
};

export function PipelineStepper({
  states,
  activeNode,
  counters,
  running,
}: {
  states: Record<StageId, StageState>;
  activeNode: string | null;
  counters: Counters;
  running: boolean;
}) {
  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8" aria-label="Pipeline">
      {STAGES.map((stage, i) => {
        const state = states[stage.id];
        const sub = detail(stage.id, state, activeNode, counters);
        return (
          <li
            key={stage.id}
            aria-current={state === "current" ? "step" : undefined}
            className={`flex items-start gap-2.5 rounded-xl border px-3 py-2.5 transition ${RING[state]}`}
          >
            <StepIcon state={state} index={i + 1} running={running} />
            <div className="min-w-0">
              <p className={`truncate text-sm font-semibold ${state === "upcoming" || state === "skipped" ? "text-slate-500" : "text-slate-900"}`}>
                {stage.label}
              </p>
              <p className="truncate text-xs text-slate-500">{sub || stage.blurb}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StepIcon({ state, index, running }: { state: StageState; index: number; running: boolean }) {
  const base = "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold";
  switch (state) {
    case "done":
      return (
        <span className={`${base} bg-emerald-500 text-white`}>
          <Check className="size-3.5" aria-hidden />
        </span>
      );
    case "current":
      return (
        <span className={`${base} bg-brand text-white ${running ? "animate-pulse-ring" : ""}`}>{index}</span>
      );
    case "failed":
      return (
        <span className={`${base} bg-red-500 text-white`}>
          <X className="size-3.5" aria-hidden />
        </span>
      );
    case "skipped":
      return (
        <span className={`${base} bg-slate-200 text-slate-500`}>
          <Minus className="size-3.5" aria-hidden />
        </span>
      );
    default:
      return <span className={`${base} border border-slate-300 bg-white text-slate-500`}>{index}</span>;
  }
}
