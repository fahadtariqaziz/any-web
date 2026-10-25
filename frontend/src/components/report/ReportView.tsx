"use client";

// The interim report: the recommended solution, why it won, the alternatives, what is uncertain, and what to
// decide before planning the build. The problem statement + solution brief (BriefView) is shown above it.

import { FileText, Printer, Trophy } from "lucide-react";
import { useState } from "react";

import { ProposalDetails } from "@/components/debate/ProposalDetails";
import { RiskFlagBanner } from "@/components/session/RiskFlagBanner";
import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { Markdown } from "@/components/ui/Markdown";
import type { FinalReport, LiveSnapshot, ProposalResult } from "@/lib/api/types";
import { CONFIDENCE_TONE, LEVEL_TONE, WORKFLOW_STATUS_LABEL, formatDateTime, workflowStatusTone } from "@/lib/format";

export function ReportView({ report, workflowStatus, live }: { report: FinalReport; workflowStatus: string; live: LiveSnapshot | null }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const withdrawn = report.withdrawn_risk_flags.map((text) => {
    const m = /^(.*?)\s*\((.*)\)$/.exec(text);
    return m ? { flag: m[1], reason: m[2] } : { flag: text, reason: "" };
  });
  const clarifications = Object.entries(report.clarifications);
  const all: ProposalResult[] = [...(report.winner ? [report.winner] : []), ...report.alternatives];
  const open = all.find((r) => r.proposal.proposal_id === openId) ?? null;

  return (
    <div className="animate-fade-up space-y-6">
      <Card>
        <CardHeader
          eyebrow="Research summary"
          title={
            <span className="flex items-center gap-2">
              <FileText className="size-5 text-brand" aria-hidden />
              <span className="capitalize">{report.project_name}</span>
            </span>
          }
          description={`Generated ${formatDateTime(report.generated_at)} for “${report.original_question}”`}
          aside={
            <>
              <Badge tone={workflowStatusTone(workflowStatus)} size="md">
                {WORKFLOW_STATUS_LABEL[workflowStatus] ?? workflowStatus}
              </Badge>
              <Button variant="secondary" size="sm" className="no-print" icon={<Printer className="size-4" aria-hidden />} onClick={() => window.print()}>
                Print / save PDF
              </Button>
            </>
          }
        />
        <CardBody className="space-y-4">
          <RiskFlagBanner flags={report.risk_flags} withdrawn={withdrawn} />
          {report.is_conditional && (
            <Callout tone="warning" title="Read this as conditional">
              <p>
                The recommendation depends on unconfirmed assumptions, thin evidence in a domain, or claims that could not be
                verified at their source. The uncertainties and unresolved questions are listed below.
              </p>
            </Callout>
          )}
          <div className="rounded-xl bg-brand-faint p-5">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand">Overview</p>
            <Markdown>{report.overview}</Markdown>
          </div>
        </CardBody>
      </Card>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight text-slate-900">Recommended solution</h2>
        {report.winner ? (
          <ProposalCard result={report.winner} open={openId === report.winner.proposal.proposal_id} onToggle={() => setOpenId(openId === report.winner!.proposal.proposal_id ? null : report.winner!.proposal.proposal_id)} why={report.why_this_solution} />
        ) : (
          <Callout tone="warning" title="No solution could be defended">
            <p>{report.no_winner_reason || "The agents could not propose a defensible solution with the evidence available."}</p>
          </Callout>
        )}
        {report.alternatives.length > 0 && (
          <>
            <h3 className="pt-2 text-sm font-semibold text-slate-700">Alternatives considered</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {report.alternatives.map((alt) => (
                <ProposalCard key={alt.proposal.proposal_id} result={alt} open={openId === alt.proposal.proposal_id} onToggle={() => setOpenId(openId === alt.proposal.proposal_id ? null : alt.proposal.proposal_id)} />
              ))}
            </div>
          </>
        )}
        {open && (
          <Card>
            <CardHeader eyebrow={open.is_winner ? "Winner" : "Alternative"} title={open.proposal.name} />
            <CardBody>
              <ProposalDetails
                proposal={open.proposal}
                score={open.score}
                criticism={live?.debate.criticisms.find((c) => c.proposal_id === open.proposal.proposal_id) ?? null}
                claims={live?.verification.results.filter((r) => r.proposal_id === open.proposal.proposal_id) ?? []}
                keyEvidence={open.key_evidence}
              />
            </CardBody>
          </Card>
        )}
      </section>

      <Card className="border-brand/40">
        <CardHeader eyebrow="Before planning the build" title="Next steps" description="What to confirm or decide before the implementation plan is written." />
        <CardBody><BulletList items={report.next_steps} numbered emptyText="None listed." /></CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader eyebrow="Honesty" title="Uncertainties" />
          <CardBody><BulletList items={report.uncertainties} emptyText="None listed." /></CardBody>
        </Card>
        <Card>
          <CardHeader eyebrow="Checked at source" title="Unsupported claims" />
          <CardBody><BulletList items={report.unsupported_claims} emptyText="Every material claim was supported by its source." /></CardBody>
        </Card>
        <Card>
          <CardHeader eyebrow="Open" title="Unresolved questions" />
          <CardBody><BulletList items={report.unresolved_questions} emptyText="None." /></CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader eyebrow="Based on" title="Your information" description="The facts the proposals were built on. Correct anything wrong in a new session." />
        <CardBody className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Project profile</h3>
            <KeyValueList items={report.confirmed_profile} emptyText="None recorded." />
          </div>
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Requested features</h3>
            <KeyValueList items={report.requested_features} emptyText="None recorded." />
          </div>
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Constraints</h3>
            <KeyValueList items={report.constraints} emptyText="None recorded." />
          </div>
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Assumptions</h3>
            <BulletList items={report.assumptions} emptyText="None." />
          </div>
          {clarifications.length > 0 && (
            <div className="space-y-2 md:col-span-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Your answers</h3>
              <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                {clarifications.map(([q, a]) => (
                  <div key={q} className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-2 sm:gap-4">
                    <dt className="text-slate-600">{q}</dt>
                    <dd className="font-medium text-slate-900">{a}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader eyebrow="Methodology" title="How this summary was made" />
        <CardBody className="space-y-3 text-sm text-slate-700">
          <Markdown compact>{report.research_methodology}</Markdown>
          <p className="rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-600">{report.disclaimer}</p>
        </CardBody>
      </Card>
    </div>
  );
}

function ProposalCard({ result, open, onToggle, why }: { result: ProposalResult; open: boolean; onToggle: () => void; why?: string[] }) {
  const p = result.proposal;
  const counts = Object.entries(result.verification_counts);
  return (
    <article className={`rounded-xl border bg-white p-4 ${result.is_winner ? "border-brand ring-2 ring-brand/20" : "border-slate-200"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            {result.is_winner && <Badge tone="brand" size="xs"><Trophy className="mr-1 inline size-3" aria-hidden />Recommended</Badge>}
            <Badge tone="slate" size="xs" className="font-mono">{p.proposal_id}</Badge>
            <Badge tone={LEVEL_TONE[p.difficulty]} size="xs">{p.difficulty} effort</Badge>
            {result.score && <Badge tone={CONFIDENCE_TONE[result.score.confidence]} size="xs">{result.score.confidence} confidence</Badge>}
          </div>
          <h3 className="mt-1 text-base font-semibold leading-snug text-slate-900">{p.name}</h3>
        </div>
        {result.score?.weighted_total != null && (
          <p className="shrink-0 text-right">
            <span className="text-2xl font-semibold tabular-nums">{result.score.weighted_total.toFixed(1)}</span>
            <span className="text-xs text-slate-400"> / 10</span>
          </p>
        )}
      </div>
      <Markdown compact className="mt-2 text-slate-700">{p.summary}</Markdown>
      {why && why.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Why this one</p>
          <BulletList items={why} />
        </div>
      )}
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">First version</p>
          <BulletList items={p.core_features.slice(0, 5)} />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Stack</p>
          <BulletList items={p.technologies.slice(0, 5)} />
        </div>
      </div>
      {(counts.length > 0 || result.critic_key_objections.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
          {counts.map(([status, n]) => (
            <Badge key={status} tone="slate" size="xs">{n} {status.replace(/_/g, " ")}</Badge>
          ))}
          {result.critic_key_objections.length > 0 && <Badge tone="amber" size="xs">{result.critic_key_objections.length} critic objection{result.critic_key_objections.length === 1 ? "" : "s"}</Badge>}
        </div>
      )}
      <button type="button" onClick={onToggle} aria-expanded={open} className="mt-3 text-xs font-medium text-brand hover:underline">
        {open ? "Hide details" : "Full proposal, scores, critique and evidence"}
      </button>
    </article>
  );
}
