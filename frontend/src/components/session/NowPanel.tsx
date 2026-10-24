"use client";

// "What is happening right now": the one card a user watches while the agents work. It always shows
// something that moves (elapsed timer, progress bar, latest message) so there is never a frozen screen
// between two polls.

import { Clock } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import type { DecisionStatus, Perspective } from "@/lib/api/types";
import { PERSPECTIVES, PERSPECTIVE_META, formatDuration, secondsSince } from "@/lib/format";
import { type Activity, NODE_INFO, STAGES, type LaneState, subProgress } from "@/lib/pipeline";

export function NowPanel({
  status,
  activity,
  now,
  fallbackStart,
  resuming,
}: {
  status: DecisionStatus;
  activity: Activity;
  now: number;
  fallbackStart: number | null;
  resuming: boolean;
}) {
  const node = resuming ? null : activity.activeNode;
  const info = node ? NODE_INFO[node] : null;
  const stageIndex = STAGES.findIndex((s) => s.id === activity.activeStage);

  const startedIso = activity.stageStartedAt;
  const elapsed = startedIso ? secondsSince(startedIso, now) : fallbackStart ? (now - fallbackStart) / 1000 : 0;
  const expected = info?.expectedSeconds ?? 0;
  const sub = subProgress(status.progress, node);
  const fraction = sub.fraction ?? (expected ? Math.min(elapsed / expected, 0.95) : 0.1);
  const slow = expected > 0 && elapsed > expected * 1.6;

  const headline = resuming ? "Sending your reply to the agents" : info?.headline ?? "Starting the agents";
  const doing = resuming
    ? "Your reply is being saved to the session. The next agent starts in a moment."
    : info?.doing ?? "Connecting to the session and starting the first agent.";

  return (
    <Card className="overflow-hidden border-teal-200">
      <div className="h-1 w-full bg-teal-100">
        <div className="shimmer-bar h-full w-full" />
      </div>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <Badge tone="brand" dot pulse>
              Live
            </Badge>
            {stageIndex >= 0 && (
              <span>
                Stage {stageIndex + 1} of {STAGES.length} · {STAGES[stageIndex].label}
              </span>
            )}
            {status.counters.debate_round > 1 && activity.activeStage === "debate" && <Badge tone="violet" size="xs">Debate round {status.counters.debate_round}</Badge>}
            {node === "research" && status.counters.research_passes >= 2 && (
              <Badge tone="violet" size="xs">Follow-up research pass {status.counters.research_passes}</Badge>
            )}
          </div>
          <div className="flex items-center gap-1.5 font-mono text-sm tabular-nums text-slate-700">
            <Clock className="size-4 text-slate-400" aria-hidden />
            <span>{formatDuration(elapsed)}</span>
            {expected > 0 && <span className="text-xs text-slate-400">/ usually ~{formatDuration(expected)}</span>}
          </div>
        </div>

        <div className="space-y-1.5">
          <h2 className="text-xl font-semibold tracking-tight text-slate-900">{headline}</h2>
          <p className="text-sm leading-relaxed text-slate-600">{doing}</p>
        </div>

        {(sub.summary || sub.lanes) && (
          <div className="flex flex-wrap items-center gap-2">
            {sub.summary && <span className="text-sm font-medium text-slate-800">{sub.summary}</span>}
            {sub.lanes && (
              <ul className="flex flex-wrap gap-1.5" aria-label="Lanes">
                {PERSPECTIVES.map((p) => (
                  <LaneChip key={p} perspective={p} state={sub.lanes![p]} />
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="space-y-1.5">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fraction * 100)}>
            <div className="h-full rounded-full bg-brand transition-[width] duration-700 ease-out" style={{ width: `${Math.max(4, fraction * 100)}%` }} />
          </div>
          {slow && (
            <p className="text-xs text-amber-700">
              Taking longer than usual. Large results or a slow model reply can do that; failed calls are retried automatically.
            </p>
          )}
        </div>

        <p className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700" aria-live="polite">
          <span className="shrink-0 text-slate-400">latest</span>
          <span className="min-w-0 break-words">
            {activity.lastLine ? `${activity.lastLine.node}: ${activity.lastLine.message}` : "waiting for the first message from the agents…"}
          </span>
        </p>
      </CardBody>
    </Card>
  );
}

function LaneChip({ perspective, state }: { perspective: Perspective; state: LaneState }) {
  const meta = PERSPECTIVE_META[perspective];
  const style =
    state === "done" ? `${meta.bg} ${meta.text} ${meta.border}` : state === "working" ? "border-slate-300 bg-white text-slate-700" : "border-slate-200 bg-slate-50 text-slate-400";
  return (
    <li className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${style}`}>
      <span className={`size-1.5 rounded-full ${state === "waiting" ? "bg-slate-300" : meta.dot} ${state === "working" ? "animate-pulse" : ""}`} />
      {meta.short}
      <span className="text-[10px] font-normal opacity-80">{state === "done" ? "done" : state === "working" ? "working" : "queued"}</span>
    </li>
  );
}
