"use client";

// "✻ Researching… (12s)": the short sign of the agents' work in the chat. The star cycles through a few glyphs
// so it feels alive; the label comes from lib/chatStages.ts. The details are in the right pane's Activity tab.

import { useEffect, useState } from "react";

const FRAMES = ["·", "✢", "✳", "✶", "✻", "✽", "✻", "✶", "✳", "✢"];
const FRAME_MS = 140;

export function WorkingChip({ label, seconds, detail }: { label: string; seconds?: number | null; detail?: string | null }) {
  // A counter from 0 (not the clock): the server render and the first browser render must match.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), FRAME_MS);
    return () => clearInterval(id);
  }, []);
  const frame = FRAMES[tick % FRAMES.length];
  return (
    <div className="py-1" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-[15px] text-orange-600">
        <span className="inline-block w-4 text-center font-mono" aria-hidden>
          {frame}
        </span>
        <span className="font-medium">{label}…</span>
        {seconds != null && <span className="text-slate-400">({seconds}s)</span>}
      </div>
      {detail && <p className="mt-0.5 truncate pl-6 text-xs text-slate-500">{detail}</p>}
    </div>
  );
}
