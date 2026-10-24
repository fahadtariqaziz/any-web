"use client";

// "✻ Researching… (12s)": the only sign of the agents' work the patient sees. The star cycles through
// a few glyphs so it feels alive; the label comes from lib/chatStages.ts.

import { useEffect, useState } from "react";

const FRAMES = ["·", "✢", "✳", "✶", "✻", "✽", "✻", "✶", "✳", "✢"];
const FRAME_MS = 140;

export function WorkingChip({ label, seconds }: { label: string; seconds?: number | null }) {
  // A counter from 0 (not the clock): the server render and the first browser render must match.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), FRAME_MS);
    return () => clearInterval(id);
  }, []);
  const frame = FRAMES[tick % FRAMES.length];
  return (
    <div className="flex items-center gap-2 py-1 text-[15px] text-[#e0876a]" role="status" aria-live="polite">
      <span className="inline-block w-4 text-center font-mono" aria-hidden>
        {frame}
      </span>
      <span className="font-medium">{label}…</span>
      {seconds != null && <span className="text-neutral-500">({seconds}s)</span>}
    </div>
  );
}
