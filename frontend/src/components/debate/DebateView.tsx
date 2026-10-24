"use client";

// Plans, critiques and scores as they appear: every plan per lane with the Judge's score, the winner
// highlighted, the Critic's points and the Evidence Checker's results. Visible while running too.

import { Gavel, Scale, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { PlanDetails } from "@/components/report/PlanDetails";
import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Markdown } from "@/components/ui/Markdown";
import type { LiveSnapshot } from "@/lib/api/types";
import { CONFIDENCE_TONE, LEVEL_TONE, DOMAINS, DOMAIN_META, titleCase, type Tone } from "@/lib/format";

const DECISION_LABEL: Record<string, { label: string; tone: Tone }> = {
  proceed: { label: "Proceed to verification", tone: "emerald" },
  request_more_research: { label: "More research requested", tone: "violet" },
  request_clarification: { label: "Questions for you", tone: "amber" },
  insufficient_evidence: { label: "Continuing with uncertainty", tone: "amber" },
};

const LANE_STATUS: Record<string, { label: string; tone: Tone }> = {
  sufficient: { label: "evidence sufficient", tone: "emerald" },
  insufficient: { label: "evidence insufficient", tone: "amber" },
  no_plans: { label: "no plans", tone: "slate" },
  declined: { label: "declined (emergency first)", tone: "red" },
  ok: { label: "plans built", tone: "emerald" },
  thin: { label: "evidence thin", tone: "amber" },
  no_evidence: { label: "no evidence", tone: "slate" },
};

export function DebateView({ live }: { live: LiveSnapshot }) {
  const [open, setOpen] = useState<string | null>(null);
  const { debate, verification, research } = live;
  const winners = new Set(Object.values(debate.verdict?.winning_plan_ids ?? {}));

  if (debate.care_plans.length === 0) {
    return (
      <EmptyState icon={<Scale className="size-6" aria-hidden />} title="No plans yet">
        Care plans appear here as soon as the Proposer finishes. Then the Critic&apos;s points and the Judge&apos;s scores are added as each agent completes.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-5">
      {research.domain_summaries && Object.keys(research.domain_summaries).length > 0 && (
        <Card>
          <CardHeader eyebrow="Research" title={`What each lane found (${research.passes} pass${research.passes === 1 ? "" : "es"})`} />
          <CardBody className="grid gap-4 md:grid-cols-3">
            {DOMAINS.map((p) => (
              <div key={p} className={`rounded-lg border p-3 ${DOMAIN_META[p].border}`}>
                <p className={`mb-1 text-xs font-semibold ${DOMAIN_META[p].text}`}>
                  {DOMAIN_META[p].short} · {research.evidence_by_domain[p] ?? 0} sources
                </p>
                <Markdown compact className="text-slate-700">{research.domain_summaries[p] ?? "Nothing yet."}</Markdown>
              </div>
            ))}
            {research.evidence_gaps.length > 0 && (
              <div className="md:col-span-3">
                <p className="text-xs font-semibold text-slate-500">Evidence gaps named by the research agent</p>
                <BulletList items={research.evidence_gaps} />
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {debate.verdict && (
        <Card>
          <CardHeader
            eyebrow={`Judge · debate round ${debate.round}`}
            title={
              <span className="flex items-center gap-2">
                <Gavel className="size-4 text-slate-500" aria-hidden />
                {DECISION_LABEL[debate.verdict.decision]?.label ?? titleCase(debate.verdict.decision)}
              </span>
            }
            aside={
              <div className="flex flex-wrap gap-1.5">
                {DOMAINS.map((p) => {
                  const s = debate.verdict!.domain_status[p];
                  const m = s ? LANE_STATUS[s] : null;
                  return m ? <Badge key={p} tone={m.tone} size="xs">{DOMAIN_META[p].short}: {m.label}</Badge> : null;
                })}
              </div>
            }
          />
          <CardBody className="space-y-2">
            <Markdown compact className="text-slate-700">{debate.verdict.reason}</Markdown>
            {debate.verdict.required_evidence.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500">Asked the research agent to find</p>
                <BulletList items={debate.verdict.required_evidence} />
              </div>
            )}
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {DOMAINS.map((p) => {
          const meta = DOMAIN_META[p];
          const plans = debate.care_plans.filter((c) => c.domain === p).sort((a, b) => b.round - a.round);
          const lane = debate.lane_status[p];
          return (
            <section key={p} className="space-y-3">
              <div className={`flex items-center justify-between rounded-lg border px-3 py-2 ${meta.bg} ${meta.border}`}>
                <p className={`flex items-center gap-2 text-sm font-semibold ${meta.text}`}>
                  <span className={`size-2 rounded-full ${meta.dot}`} />
                  {meta.short} · {plans.length} plan{plans.length === 1 ? "" : "s"}
                </p>
                {lane && LANE_STATUS[lane] && <Badge tone={LANE_STATUS[lane].tone} size="xs">{LANE_STATUS[lane].label}</Badge>}
              </div>
              {debate.proposer_notes[p] && <p className="text-xs text-slate-600">{debate.proposer_notes[p]}</p>}
              {plans.map((plan) => {
                const score = debate.scores.find((s) => s.plan_id === plan.plan_id) ?? null;
                const crit = debate.criticisms.find((c) => c.plan_id === plan.plan_id) ?? null;
                const isWinner = winners.has(plan.plan_id);
                const isOpen = open === plan.plan_id;
                return (
                  <article key={plan.plan_id} className={`rounded-xl border bg-white p-4 ${isWinner ? "border-brand ring-2 ring-brand/20" : "border-slate-200"}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {isWinner && <Badge tone="brand" size="xs">Winner</Badge>}
                          <Badge tone="slate" size="xs" className="font-mono">{plan.plan_id}</Badge>
                          <span className="text-[11px] text-slate-400">round {plan.round}</span>
                        </div>
                        <h3 className="mt-1 text-sm font-semibold leading-snug text-slate-900">{plan.name}</h3>
                      </div>
                      {score?.weighted_total != null ? (
                        <p className="shrink-0 text-right">
                          <span className="text-xl font-semibold tabular-nums">{score.weighted_total.toFixed(1)}</span>
                          <span className="text-xs text-slate-400"> / 10</span>
                        </p>
                      ) : (
                        <span className="shrink-0 text-xs text-slate-400">not scored yet</span>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Badge tone={LEVEL_TONE[plan.difficulty]} size="xs">{plan.difficulty} effort</Badge>
                      {score && <Badge tone={CONFIDENCE_TONE[score.confidence]} size="xs">{score.confidence} confidence</Badge>}
                      {crit ? (
                        <Badge tone={crit.points.length === 0 ? "emerald" : "amber"} size="xs">{crit.points.length} critic point{crit.points.length === 1 ? "" : "s"}</Badge>
                      ) : (
                        <Badge tone="slate" size="xs">not critiqued yet</Badge>
                      )}
                    </div>
                    <Markdown compact className="mt-2 text-slate-700">{plan.summary}</Markdown>
                    <button type="button" onClick={() => setOpen(isOpen ? null : plan.plan_id)} aria-expanded={isOpen} className="mt-2 text-xs font-medium text-brand hover:underline">
                      {isOpen ? "Hide details" : "Full plan, scores and critique"}
                    </button>
                    {isOpen && (
                      <div className="mt-3 border-t border-slate-100 pt-3">
                        <PlanDetails plan={plan} score={score} criticism={crit} claims={verification.results.filter((r) => r.plan_id === plan.plan_id)} />
                      </div>
                    )}
                  </article>
                );
              })}
            </section>
          );
        })}
      </div>

      {verification.verdict && (
        <Card>
          <CardHeader
            eyebrow="Evidence checker"
            title={
              <span className="flex items-center gap-2">
                <ShieldCheck className="size-4 text-slate-500" aria-hidden />
                {verification.verdict.claims_checked} claims checked · {verification.verdict.decision === "proceed" ? "proceeding to the report" : titleCase(verification.verdict.decision)}
              </span>
            }
          />
          <CardBody className="space-y-3">
            <p className="text-sm text-slate-700">{verification.verdict.reason}</p>
            <div className="grid gap-3 md:grid-cols-3">
              {DOMAINS.map((p) =>
                verification.verdict!.summaries[p] ? (
                  <div key={p} className={`rounded-lg border p-3 text-sm ${DOMAIN_META[p].border}`}>
                    <p className={`mb-1 text-xs font-semibold ${DOMAIN_META[p].text}`}>{DOMAIN_META[p].short}</p>
                    <p className="text-slate-700">{verification.verdict!.summaries[p]}</p>
                    {verification.verdict!.gaps_by_lane[p]?.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs font-semibold text-amber-700">Material gaps</p>
                        <BulletList items={verification.verdict!.gaps_by_lane[p]} />
                      </div>
                    )}
                  </div>
                ) : null,
              )}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
