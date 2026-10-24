"use client";

// Proposals, critiques and scores as they appear: every proposal with the Judge's score, the winner highlighted,
// the Critic's points and the Evidence Checker's results. Visible while running too.

import { Gavel, Scale, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ProposalDetails } from "@/components/debate/ProposalDetails";
import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Markdown } from "@/components/ui/Markdown";
import type { LiveSnapshot } from "@/lib/api/types";
import { CONFIDENCE_TONE, DOMAINS, DOMAIN_META, LEVEL_TONE, titleCase, type Tone } from "@/lib/format";

const DECISION_LABEL: Record<string, { label: string; tone: Tone }> = {
  proceed: { label: "Proceed to verification", tone: "emerald" },
  request_more_research: { label: "More research requested", tone: "violet" },
  request_clarification: { label: "Questions for you", tone: "amber" },
  insufficient_evidence: { label: "Continuing with uncertainty", tone: "amber" },
};

const DOMAIN_STATUS: Record<string, { label: string; tone: Tone }> = {
  sufficient: { label: "sufficient", tone: "emerald" },
  insufficient: { label: "insufficient", tone: "amber" },
  no_evidence: { label: "no evidence", tone: "slate" },
};

const PROPOSER_STATUS: Record<string, { label: string; tone: Tone }> = {
  ok: { label: "proposals built", tone: "emerald" },
  thin: { label: "evidence thin", tone: "amber" },
  declined: { label: "nothing to propose", tone: "slate" },
  no_evidence: { label: "no evidence", tone: "slate" },
};

export function DebateView({ live }: { live: LiveSnapshot }) {
  const [open, setOpen] = useState<string | null>(null);
  const { debate, verification, research } = live;
  const winner = debate.verdict?.winning_proposal_id ?? null;

  if (debate.proposals.length === 0) {
    return (
      <EmptyState icon={<Scale className="size-6" aria-hidden />} title="No proposals yet">
        Solution proposals appear here as soon as the Proposer finishes. Then the Critic&apos;s points and the Judge&apos;s scores are added as each agent completes.
        {debate.proposer_notes && <p className="mt-2 text-xs text-slate-500">{debate.proposer_notes}</p>}
      </EmptyState>
    );
  }

  return (
    <div className="space-y-5">
      {research.domain_summaries && Object.keys(research.domain_summaries).length > 0 && (
        <Card>
          <CardHeader eyebrow="Research" title={`What each domain found (${research.passes} pass${research.passes === 1 ? "" : "es"})`} />
          <CardBody className="grid gap-4 md:grid-cols-3">
            {DOMAINS.map((d) => (
              <div key={d} className={`rounded-lg border p-3 ${DOMAIN_META[d].border}`}>
                <p className={`mb-1 text-xs font-semibold ${DOMAIN_META[d].text}`}>
                  {DOMAIN_META[d].short} · {research.evidence_by_domain[d] ?? 0} sources
                </p>
                <Markdown compact className="text-slate-700">{research.domain_summaries[d] ?? "Nothing yet."}</Markdown>
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
                {DOMAINS.map((d) => {
                  const s = debate.verdict!.domain_status[d];
                  const m = s ? DOMAIN_STATUS[s] : null;
                  return m ? <Badge key={d} tone={m.tone} size="xs">{DOMAIN_META[d].short}: {m.label}</Badge> : null;
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
            {debate.verdict.material_contradictions.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-amber-700">Material contradictions</p>
                <BulletList items={debate.verdict.material_contradictions} />
              </div>
            )}
            {debate.verdict.clarification_questions.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500">Questions for you</p>
                <BulletList items={debate.verdict.clarification_questions} />
              </div>
            )}
          </CardBody>
        </Card>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-sm font-semibold text-slate-800">
            {debate.proposals.length} proposal{debate.proposals.length === 1 ? "" : "s"} · round {debate.round}
          </p>
          {PROPOSER_STATUS[debate.proposer_status] && (
            <Badge tone={PROPOSER_STATUS[debate.proposer_status].tone} size="xs">{PROPOSER_STATUS[debate.proposer_status].label}</Badge>
          )}
        </div>
        {debate.proposer_notes && <p className="text-xs text-slate-600">{debate.proposer_notes}</p>}
        <div className="grid gap-4 lg:grid-cols-3">
          {debate.proposals.map((proposal) => {
            const id = proposal.proposal_id;
            const score = debate.scores.find((s) => s.proposal_id === id) ?? null;
            const crit = debate.criticisms.find((c) => c.proposal_id === id) ?? null;
            const isWinner = winner === id;
            const isOpen = open === id;
            return (
              <article key={id} className={`rounded-xl border bg-white p-4 ${isWinner ? "border-brand ring-2 ring-brand/20 lg:col-span-3" : "border-slate-200"} ${isOpen && !isWinner ? "lg:col-span-3" : ""}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {isWinner && <Badge tone="brand" size="xs">Winner</Badge>}
                      <Badge tone="slate" size="xs" className="font-mono">{id}</Badge>
                      <span className="text-[11px] text-slate-400">round {proposal.round}</span>
                    </div>
                    <h3 className="mt-1 text-sm font-semibold leading-snug text-slate-900">{proposal.name}</h3>
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
                  <Badge tone={LEVEL_TONE[proposal.difficulty]} size="xs">{proposal.difficulty} effort</Badge>
                  {score && <Badge tone={CONFIDENCE_TONE[score.confidence]} size="xs">{score.confidence} confidence</Badge>}
                  {crit ? (
                    <Badge tone={crit.points.length === 0 ? "emerald" : "amber"} size="xs">{crit.points.length} critic point{crit.points.length === 1 ? "" : "s"}</Badge>
                  ) : (
                    <Badge tone="slate" size="xs">not critiqued yet</Badge>
                  )}
                </div>
                <Markdown compact className="mt-2 text-slate-700">{proposal.summary}</Markdown>
                <button type="button" onClick={() => setOpen(isOpen ? null : id)} aria-expanded={isOpen} className="mt-2 text-xs font-medium text-brand hover:underline">
                  {isOpen ? "Hide details" : "Full proposal, scores and critique"}
                </button>
                {isOpen && (
                  <div className="mt-3 border-t border-slate-100 pt-3">
                    <ProposalDetails proposal={proposal} score={score} criticism={crit} claims={verification.results.filter((r) => r.proposal_id === id)} />
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </section>

      {verification.verdict && (
        <Card>
          <CardHeader
            eyebrow="Evidence checker"
            title={
              <span className="flex items-center gap-2">
                <ShieldCheck className="size-4 text-slate-500" aria-hidden />
                {verification.verdict.claims_checked} claims checked · {verification.verdict.decision === "proceed" ? "proceeding to the summary" : titleCase(verification.verdict.decision)}
              </span>
            }
          />
          <CardBody className="space-y-2">
            <p className="text-sm text-slate-700">{verification.verdict.reason}</p>
            {verification.verdict.summary && <p className="text-sm text-slate-600">{verification.verdict.summary}</p>}
            {verification.verdict.material_gaps.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-amber-700">Material gaps</p>
                <BulletList items={verification.verdict.material_gaps} />
              </div>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
