"use client";

import { useState } from "react";

import type { PlanScore } from "@/lib/api/types";
import { RUBRIC } from "@/lib/format";

/** The Judge's five criterion scores as bars, with the weight of each and the explanation on demand. */
export function ScoreBars({ score, compact = false }: { score: PlanScore; compact?: boolean }) {
  const [showWhy, setShowWhy] = useState(false);
  const byKey = Object.fromEntries(score.criterion_scores.map((c) => [c.criterion, c]));
  return (
    <div className="space-y-2">
      <ul className="space-y-1.5">
        {RUBRIC.map((r) => {
          const c = byKey[r.key];
          const value = c?.score ?? 0;
          return (
            <li key={r.key} className="space-y-0.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-600">
                  {r.label} <span className="text-slate-400">· {Math.round(r.weight * 100)}%</span>
                </span>
                <span className="font-mono tabular-nums text-slate-800">{value.toFixed(1)}</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-brand" style={{ width: `${(value / 10) * 100}%` }} />
              </div>
              {showWhy && c && <p className="text-xs leading-relaxed text-slate-600">{c.explanation}</p>}
            </li>
          );
        })}
      </ul>
      {!compact && (
        <button type="button" onClick={() => setShowWhy((v) => !v)} className="text-xs font-medium text-brand hover:underline">
          {showWhy ? "Hide the Judge's reasoning" : "Why these scores?"}
        </button>
      )}
    </div>
  );
}
