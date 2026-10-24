"use client";

// The final report: red flags first, overview, the three winning plans side by side, where the
// domains agree and differ, uncertainties, next steps, your information, methodology, disclaimer.

import { FileText, Printer } from "lucide-react";
import { useState } from "react";

import { ComparisonGrid } from "@/components/report/ComparisonGrid";
import { PerspectiveCard } from "@/components/report/PerspectiveCard";
import { PlanDetails } from "@/components/report/PlanDetails";
import { RedFlagBanner } from "@/components/session/RedFlagBanner";
import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { KeyValueList } from "@/components/ui/KeyValueList";
import { Markdown } from "@/components/ui/Markdown";
import type { FinalReport, LiveSnapshot } from "@/lib/api/types";
import { WORKFLOW_STATUS_LABEL, formatDateTime, titleCase, workflowStatusTone } from "@/lib/format";

export function ReportView({ report, workflowStatus, live }: { report: FinalReport; workflowStatus: string; live: LiveSnapshot | null }) {
  const [openPlan, setOpenPlan] = useState<string | null>(null);
  const withdrawn = report.withdrawn_risk_flags.map((text) => {
    const m = /^(.*?)\s*\((.*)\)$/.exec(text);
    return m ? { flag: m[1], reason: m[2] } : { flag: text, reason: "" };
  });
  const clarifications = Object.entries(report.clarifications);

  return (
    <div className="animate-fade-up space-y-6">
      <Card>
        <CardHeader
          eyebrow="Final report"
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
          <RedFlagBanner flags={report.risk_flags} withdrawn={withdrawn} />
          {report.is_conditional && (
            <Callout tone="warning" title="Read this report as conditional">
              <p>
                Some guidance depends on unconfirmed assumptions or on claims that could not be verified at their source. The
                uncertainties and unresolved questions are listed below; bring them to your doctor.
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
        <h2 className="text-lg font-semibold tracking-tight text-slate-900">The best plan from each domain</h2>
        <div className="grid gap-4 lg:grid-cols-3">
          {report.domains.map((p) => (
            <PerspectiveCard
              key={p.domain}
              domain={p.domain}
              planId={p.plan?.plan_id ?? null}
              name={p.plan?.name ?? null}
              summary={p.plan?.summary ?? null}
              weightedTotal={p.score?.weighted_total ?? null}
              confidence={p.score?.confidence ?? null}
              difficulty={p.plan?.difficulty ?? null}
              verificationCounts={p.verification_counts}
              objections={p.critic_key_objections}
              unavailableReason={p.unavailable_reason || null}
              expanded={openPlan === p.plan?.plan_id}
              onToggle={p.plan ? () => setOpenPlan(openPlan === p.plan!.plan_id ? null : p.plan!.plan_id) : undefined}
            />
          ))}
        </div>
        {openPlan && (
          <Card>
            <CardBody>
              {(() => {
                const result = report.domains.find((p) => p.plan?.plan_id === openPlan);
                if (!result?.plan) return null;
                return (
                  <PlanDetails
                    plan={result.plan}
                    score={result.score}
                    criticism={live?.debate.criticisms.find((c) => c.plan_id === openPlan) ?? null}
                    claims={live?.verification.results.filter((r) => r.plan_id === openPlan) ?? []}
                    keyEvidence={result.key_evidence}
                  />
                );
              })()}
            </CardBody>
          </Card>
        )}
      </section>

      <Card>
        <CardHeader eyebrow="Side by side" title="Compare the three plans" description="Routine, diet, treatments as reported, timeline and outlook, from each domain's own evidence." />
        <CardBody>
          <ComparisonGrid domains={report.domains} />
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader eyebrow="Consensus" title="Where the domains agree" />
          <CardBody><BulletList items={report.where_perspectives_agree} emptyText="No shared points were identified." /></CardBody>
        </Card>
        <Card>
          <CardHeader eyebrow="Disagreement" title="Where they differ" />
          <CardBody><BulletList items={report.where_perspectives_differ} emptyText="No differences were identified." /></CardBody>
        </Card>
      </div>

      <Card className="border-brand/40">
        <CardHeader eyebrow="Bring to your doctor" title="Next steps" description="Questions to ask and things to monitor. Nothing here is a prescription." />
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

      {report.domains.some((p) => p.verification_notes.length > 0) && (
        <Card>
          <CardHeader eyebrow="Evidence checker" title="Verification notes" />
          <CardBody className="grid gap-4 md:grid-cols-3">
            {report.domains.map((p) => (
              <div key={p.domain} className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{titleCase(p.domain)}</p>
                <BulletList items={p.verification_notes} emptyText="No notes." />
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader eyebrow="Based on" title="Your information" description="The facts the plans were built on. Correct anything wrong in a new session." />
        <CardBody className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Confirmed profile</h3>
            <KeyValueList items={report.confirmed_profile} />
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
        <CardHeader eyebrow="Methodology" title="How this report was made" />
        <CardBody className="space-y-3 text-sm text-slate-700">
          <Markdown compact>{report.research_methodology}</Markdown>
          <p className="rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-600">{report.disclaimer}</p>
        </CardBody>
      </Card>
    </div>
  );
}
