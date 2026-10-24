"use client";

// Every progress line the backend emitted, grouped by agent, with durations. Sticks to the newest line
// unless the user scrolled up to read something.

import { CheckCircle2, CircleAlert, PauseCircle, Radio } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Spinner } from "@/components/ui/Spinner";
import type { ProgressLine, RunState } from "@/lib/api/types";
import { formatDuration, formatTime, secondsSince } from "@/lib/format";
import { nodeLabel } from "@/lib/pipeline";

interface Group {
  node: string;
  lines: ProgressLine[];
  finished: boolean;
}

function groupLines(lines: ProgressLine[]): Group[] {
  const groups: Group[] = [];
  for (const line of lines) {
    const last = groups[groups.length - 1];
    if (last && last.node === line.node && !last.finished) {
      last.lines.push(line);
    } else {
      groups.push({ node: line.node, lines: [line], finished: false });
    }
    if (line.message.startsWith("✔")) groups[groups.length - 1].finished = true;
  }
  return groups;
}

export function ActivityFeed({
  lines,
  runState,
  now,
  className = "",
}: {
  lines: ProgressLine[];
  runState: RunState;
  now: number;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [stick, setStick] = useState(true);
  const groups = groupLines(lines);

  useEffect(() => {
    if (stick && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines.length, stick]);

  function onScroll() {
    const el = box.current;
    if (!el) return;
    setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
  }

  return (
    <section className={`flex min-h-0 flex-col rounded-xl border border-slate-200 bg-white shadow-sm ${className}`} aria-label="Agent activity">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Radio className={`size-4 ${runState === "running" ? "text-brand" : "text-slate-400"}`} aria-hidden />
          Agent activity
        </h2>
        <span className="text-xs text-slate-500">{lines.length ? `${lines.length} events` : runState === "running" ? "connecting…" : "no live log"}</span>
      </div>
      <div ref={box} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto px-3 py-2" style={{ maxHeight: "60vh" }}>
        {lines.length === 0 ? (
          <p className="px-1 py-4 text-sm text-slate-500">
            {runState === "running" ? (
              <span className="inline-flex items-center gap-2">
                <Spinner className="size-4 text-brand" /> Waiting for the first message from the agents…
              </span>
            ) : (
              "No live log for this run on this server. The log lives in the backend's memory and disappears when it restarts; the results shown on this page are complete."
            )}
          </p>
        ) : (
          <ol className="space-y-2">
            {groups.map((g, gi) => {
              const isLast = gi === groups.length - 1;
              const active = isLast && runState === "running" && !g.finished && g.node !== "graph";
              const first = g.lines[0].at;
              const last = g.lines[g.lines.length - 1].at;
              const seconds = active ? secondsSince(first, now) : (new Date(last).getTime() - new Date(first).getTime()) / 1000;
              return (
                <li key={`${g.node}-${gi}`} className={`rounded-lg border px-3 py-2 ${active ? "border-teal-200 bg-brand-faint/60" : "border-slate-100 bg-slate-50/60"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-800">
                      <GroupIcon group={g} active={active} />
                      {g.node === "graph" ? "System" : nodeLabel(g.node)}
                    </p>
                    {g.node !== "graph" && (g.lines.length > 1 || active) && (
                      <span className="font-mono text-[11px] tabular-nums text-slate-500">{formatDuration(seconds)}</span>
                    )}
                  </div>
                  <ol className="mt-1 space-y-0.5">
                    {g.lines.map((line, i) => {
                      const done = line.message.startsWith("✔");
                      return (
                        <li key={i} className="flex gap-2 font-mono text-[11px] leading-snug">
                          <span className="shrink-0 tabular-nums text-slate-400">{formatTime(line.at)}</span>
                          <span className={done ? "text-emerald-700" : "text-slate-700"}>{line.message}</span>
                        </li>
                      );
                    })}
                  </ol>
                </li>
              );
            })}
          </ol>
        )}
      </div>
      {!stick && lines.length > 0 && (
        <button
          type="button"
          onClick={() => {
            setStick(true);
            if (box.current) box.current.scrollTop = box.current.scrollHeight;
          }}
          className="border-t border-slate-100 px-4 py-2 text-left text-xs font-medium text-brand hover:bg-slate-50"
        >
          Jump to the latest ↓
        </button>
      )}
    </section>
  );
}

function GroupIcon({ group, active }: { group: Group; active: boolean }) {
  if (active) return <Spinner className="size-3.5 text-brand" />;
  if (group.node === "graph") {
    const crashed = group.lines.some((l) => l.message.includes("crashed"));
    return crashed ? <CircleAlert className="size-3.5 text-red-500" aria-hidden /> : <PauseCircle className="size-3.5 text-amber-500" aria-hidden />;
  }
  if (group.lines.some((l) => l.message.startsWith("failed"))) return <CircleAlert className="size-3.5 text-red-500" aria-hidden />;
  return <CheckCircle2 className="size-3.5 text-emerald-500" aria-hidden />;
}
