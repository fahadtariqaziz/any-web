"use client";

// What a project cost (M11, GET /usage): the builder's own model calls (research, brief, plan... measured since M11)
// and the coding agent (the Agent SDK's cost per task attempt), per phase, for the first build and per change.

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import type { UsageResponse } from "@/lib/api/types";

function usd(value: number): string {
  return value > 0 && value < 0.01 ? "<$0.01" : `$${value.toFixed(2)}`;
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** Total so far: builder AI + coding agent + Ask replies. */
export function projectTotal(usage: UsageResponse): number {
  return usage.total_usd + (usage.ask_usd ?? 0);
}

function Limit({ label, used, budget, note }: { label: string; used: number | null; budget: number; note: string }) {
  const share = used === null ? 0 : Math.min(1, used / budget);
  const left = used === null ? null : Math.max(0, budget - used);
  return (
    <div className="py-1.5 text-sm">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-slate-700">
          {label} <span className="text-xs text-slate-500">{note}</span>
        </span>
        <span className="shrink-0 tabular-nums text-slate-900">
          {used === null ? (
            <span className="text-slate-500">not measured · {usd(budget)} limit</span>
          ) : (
            <>
              <span className="font-medium">{usd(left!)} left</span>
              <span className="text-slate-500"> of {usd(budget)}</span>
            </>
          )}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className={`h-full rounded-full ${share >= 0.9 ? "bg-red-500" : share >= 0.7 ? "bg-amber-500" : "bg-brand"}`} style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

function Row({ label, value, hint, strong }: { label: React.ReactNode; value: string; hint?: string; strong?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 py-1 text-sm ${strong ? "font-semibold" : ""}`}>
      <span className="min-w-0 text-slate-700">
        {label}
        {hint && <span className="ml-1.5 text-xs text-slate-500">{hint}</span>}
      </span>
      <span className="shrink-0 font-medium tabular-nums text-slate-900">{value}</span>
    </div>
  );
}

export function CostCard({ usage }: { usage: UsageResponse }) {
  const measured = usage.llm_measured_since !== null;
  return (
    <Card>
      <CardHeader
        title="Cost"
        aside={
          <Badge tone="slate" size="md">
            {usd(projectTotal(usage))} so far
          </Badge>
        }
      />
      <CardBody>
        <div className="divide-y divide-slate-100">
          <Row
            label="Builder AI"
            hint={measured ? "questions, research, proposals, brief, plan" : "not measured: this project started before cost tracking"}
            value={measured ? usd(usage.llm_usd) : "—"}
          />
          <Row label="Coding agent" hint="every task attempt" value={usd(usage.agent_usd)} />
          {usage.ask_usd !== null && usage.ask_usd > 0 && <Row label="Ask replies" value={usd(usage.ask_usd)} />}
          <Row label="Total so far" value={usd(projectTotal(usage))} strong />
        </div>

        <div className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Limits for this project</h4>
          <Limit
            label="Builder AI"
            note="then no more automatic research / clarification loops"
            used={measured ? usage.llm_usd : null}
            budget={usage.llm_budget_usd}
          />
          <Limit label="Coding agent" note="then no new task starts" used={usage.agent_usd} budget={usage.agent_budget_usd} />
        </div>

        {usage.phases.length > 0 && (
          <div className="mt-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">By stage</h4>
            <div className="mt-1 divide-y divide-slate-100">
              {usage.phases.map((p) => (
                <Row key={p.phase} label={p.phase} value={usd(p.total_usd)} />
              ))}
            </div>
          </div>
        )}

        {usage.changes.length > 0 && (
          <div className="mt-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">First build and each change</h4>
            <div className="mt-1 divide-y divide-slate-100">
              <Row label="First build" hint="everything before your first change" value={usd(usage.first_build.total_usd)} />
              {usage.changes.map((c) => (
                <Row
                  key={c.round}
                  label={
                    <span className="line-clamp-1" title={c.request}>
                      {c.action === "replan" ? "Bigger change" : "Change"}: {c.request}
                    </span>
                  }
                  hint={c.tasks.length ? c.tasks.join(", ") : undefined}
                  value={usd(c.total_usd)}
                />
              ))}
            </div>
          </div>
        )}

        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          {measured && `Builder AI measured since ${shortDate(usage.llm_measured_since!)}. `}
          Limits count the whole project, all changes included. Prices as of {usage.prices_as_of}.
          {usage.unpriced_models.length > 0 && ` No price known for ${usage.unpriced_models.join(", ")}: counted as $0.`}
        </p>
      </CardBody>
    </Card>
  );
}
