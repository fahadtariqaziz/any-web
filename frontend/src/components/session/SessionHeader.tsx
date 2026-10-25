"use client";

import { Check, Copy, Hammer } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import type { DecisionStatus } from "@/lib/api/types";
import { RUN_STATE_META, WORKFLOW_STATUS_LABEL, formatDuration, relativeTime, workflowStatusTone } from "@/lib/format";

export function SessionHeader({ status, now }: { status: DecisionStatus; now: number }) {
  const [copied, setCopied] = useState(false);
  const run = RUN_STATE_META[status.run_state];
  const title = status.project_name ?? status.question ?? "New session";
  const c = status.counters;

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard not available: nothing to do */
    }
  }

  return (
    <header className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="font-mono">Session {status.thread_id.slice(0, 8)}</span>
        <button type="button" onClick={copyLink} className="no-print inline-flex items-center gap-1 rounded px-1 hover:text-slate-800">
          {copied ? <Check className="size-3.5 text-emerald-600" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
          {copied ? "Link copied" : "Copy link"}
        </button>
        {status.started_at && <span>• started {relativeTime(status.started_at, now)}</span>}
        <Link href={`/c/${status.thread_id}`} className="no-print inline-flex items-center gap-1 rounded px-1 font-medium text-brand hover:underline">
          <Hammer className="size-3.5" aria-hidden />
          Open in the builder
        </Link>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            <span className="capitalize">{title}</span>
          </h1>
          {status.question && status.project_name && <p className="text-sm text-slate-600">“{status.question}”</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={run.tone} dot pulse={status.run_state === "running"} size="md">
            {run.label}
          </Badge>
          {status.workflow_status && status.run_state !== "running" && (
            <Badge tone={workflowStatusTone(status.workflow_status)} size="md">
              {WORKFLOW_STATUS_LABEL[status.workflow_status] ?? status.workflow_status}
            </Badge>
          )}
        </div>
      </div>
      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
        <Stat label="Active time" value={formatDuration(status.active_seconds)} />
        <Stat label="Sources kept" value={c.evidence} />
        <Stat label="Proposals" value={c.proposals} />
        <Stat label="Claims checked" value={c.claims_checked} />
        {c.debate_round > 0 && <Stat label="Debate round" value={c.debate_round} />}
        {c.research_passes > 1 && <Stat label="Research passes" value={c.research_passes} />}
      </dl>
    </header>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline gap-1">
      <dt>{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  );
}
