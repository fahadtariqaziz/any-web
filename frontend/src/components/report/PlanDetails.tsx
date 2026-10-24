// Everything about one care plan: the plan itself, the Judge's scores, the Critic's points and the
// verified claims. Shared by human review, the debate view and the final report.

import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { Callout } from "@/components/ui/Callout";
import { Markdown } from "@/components/ui/Markdown";
import { ScoreBars } from "@/components/report/ScoreBars";
import type { CarePlan, ClaimVerification, Criticism, PlanScore, VerificationStatus } from "@/lib/api/types";
import { CONFIDENCE_TONE, LEVEL_TONE, PERSPECTIVE_META, VERIFICATION_META, titleCase } from "@/lib/format";

export function PlanDetails({
  plan,
  score,
  criticism,
  claims = [],
  keyEvidence = [],
}: {
  plan: CarePlan;
  score?: PlanScore | null;
  criticism?: Criticism | null;
  claims?: ClaimVerification[];
  keyEvidence?: { evidence_id: string; title: string; url: string; verification_status: VerificationStatus }[];
}) {
  const meta = PERSPECTIVE_META[plan.perspective];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className={`text-xs font-semibold ${meta.text}`}>{meta.label} · round {plan.round}</p>
          <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={LEVEL_TONE[plan.difficulty]} size="xs">{plan.difficulty} effort</Badge>
          <Badge tone="slate" size="xs" className="font-mono">{plan.plan_id}</Badge>
        </div>
      </div>

      <Markdown>{plan.summary}</Markdown>

      <div className="grid gap-5 md:grid-cols-2">
        <Section title="Daily routine"><BulletList items={plan.daily_routine} emptyText="Not covered by the evidence." /></Section>
        <Section title="Diet"><BulletList items={plan.diet} emptyText="Not covered by the evidence." /></Section>
        <Section title="Medications & treatments (as reported in the sources)">
          <BulletList items={plan.medications_treatments} emptyText="Not covered by the evidence." />
        </Section>
        <Section title="Expected timeline"><Markdown compact>{plan.expected_timeline}</Markdown></Section>
        <Section title="Prevalence & outlook"><Markdown compact>{plan.prevalence_and_outlook}</Markdown></Section>
        <Section title="Benefits"><BulletList items={plan.benefits} emptyText="None listed." /></Section>
        <Section title="Drawbacks & risks"><BulletList items={plan.drawbacks_risks} emptyText="None listed." /></Section>
        <Section title="Assumptions about you"><BulletList items={plan.assumptions} emptyText="None stated." /></Section>
      </div>

      {plan.safety_notes && (
        <Callout tone="warning" title="Safety notes">
          <Markdown compact>{plan.safety_notes}</Markdown>
        </Callout>
      )}

      <div className="grid gap-5 md:grid-cols-2">
        <Section title="Supporting evidence">
          {keyEvidence.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {keyEvidence.map((e) => (
                <li key={e.evidence_id} className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="slate" size="xs" className="font-mono">{e.evidence_id}</Badge>
                  <a href={e.url} target="_blank" rel="noreferrer noopener" className="min-w-0 truncate text-brand hover:underline">
                    {e.title}
                  </a>
                  <Badge tone={VERIFICATION_META[e.verification_status].tone} size="xs">{VERIFICATION_META[e.verification_status].label}</Badge>
                </li>
              ))}
            </ul>
          ) : plan.supporting_evidence_ids.length > 0 ? (
            <ul className="flex flex-wrap gap-1">
              {plan.supporting_evidence_ids.map((id) => (
                <li key={id}><Badge tone="slate" size="xs" className="font-mono">{id}</Badge></li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No evidence cited.</p>
          )}
        </Section>
        <Section title="Evidence gaps the plan relies on">
          <BulletList items={plan.evidence_gaps} emptyText="None stated." />
        </Section>
      </div>

      {score && (
        <Section title="Judge's scoring">
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm">
                <span className="text-2xl font-semibold tabular-nums text-slate-900">{score.weighted_total?.toFixed(2) ?? "–"}</span>
                <span className="text-slate-400"> / 10 weighted</span>
                <Badge tone={CONFIDENCE_TONE[score.confidence]} size="xs" className="ml-2">{score.confidence} confidence</Badge>
              </p>
              <p className="text-sm text-slate-600">{score.confidence_reason}</p>
              <ScoreBars score={score} />
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-xs font-semibold text-slate-500">Key benefits</p>
                <BulletList items={score.key_benefits} emptyText="None." />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-500">Key drawbacks</p>
                <BulletList items={score.key_drawbacks} emptyText="None." />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-500">Remaining risks</p>
                <BulletList items={score.remaining_risks} emptyText="None." />
              </div>
            </div>
          </div>
        </Section>
      )}

      {criticism && (
        <Section title={`Critic's review (${criticism.points.length} point${criticism.points.length === 1 ? "" : "s"})`}>
          <Markdown compact className="text-slate-700">{criticism.overall_assessment}</Markdown>
          {criticism.points.length > 0 && (
            <ul className="mt-2 space-y-2">
              {criticism.points.map((p, i) => (
                <li key={i} className="rounded-lg border border-slate-200 p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={LEVEL_TONE[p.severity]} size="xs">{p.severity}</Badge>
                    <Badge tone="slate" size="xs">{titleCase(p.category)}</Badge>
                    <Badge tone={p.is_verified_problem ? "orange" : "neutral"} size="xs">{p.is_verified_problem ? "demonstrated problem" : "possible risk"}</Badge>
                    <span className="text-xs text-slate-400">{p.basis === "evidence" ? "from evidence" : "clinical reasoning"}</span>
                  </div>
                  <p className="mt-1.5 text-slate-800">{p.issue}</p>
                  {p.suggested_improvement && <p className="mt-1 text-xs text-slate-600">Suggested fix: {p.suggested_improvement}</p>}
                  {p.evidence_ids.length > 0 && <p className="mt-1 font-mono text-[11px] text-slate-400">{p.evidence_ids.join(", ")}</p>}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {claims.length > 0 && (
        <Section title={`Claims checked at source (${claims.length})`}>
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {claims.map((c, i) => (
              <li key={i} className="space-y-1 px-3 py-2 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="text-slate-800">{c.claim}</p>
                  <div className="flex shrink-0 gap-1">
                    {c.is_material && <Badge tone="violet" size="xs">material</Badge>}
                    {c.is_anecdotal && <Badge tone="amber" size="xs">anecdotal</Badge>}
                    <Badge tone={VERIFICATION_META[c.status].tone} size="xs">{VERIFICATION_META[c.status].label}</Badge>
                  </div>
                </div>
                <p className="text-xs text-slate-600">{c.notes}</p>
                {c.evidence_ids.length > 0 && <p className="font-mono text-[11px] text-slate-400">{c.evidence_ids.join(", ")}</p>}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h4>
      {children}
    </section>
  );
}
