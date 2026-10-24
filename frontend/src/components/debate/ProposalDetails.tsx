"use client";

// Everything about one proposal: the design, the Judge's scores, the Critic's points, the verified claims.
// Shared by the live debate view and the report.

import { ScoreBars } from "@/components/report/ScoreBars";
import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { KeyValueList } from "@/components/ui/KeyValueList";
import type { ClaimVerification, Criticism, EvidenceRef, ProposalScore, SolutionProposal } from "@/lib/api/types";
import { LEVEL_TONE, VERIFICATION_META, titleCase } from "@/lib/format";

export function ProposalDetails({
  proposal,
  score,
  criticism,
  claims,
  keyEvidence = [],
}: {
  proposal: SolutionProposal;
  score: ProposalScore | null;
  criticism: Criticism | null;
  claims: ClaimVerification[];
  keyEvidence?: EvidenceRef[];
}) {
  const arch = proposal.architecture;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="space-y-4">
        <Section title="Problem addressed">
          <p className="text-sm text-slate-700">{proposal.problem_addressed}</p>
        </Section>
        <Section title="Target users">
          <p className="text-sm text-slate-700">{proposal.target_users}</p>
        </Section>
        <Section title="Core features (first version)">
          <BulletList items={proposal.core_features} />
        </Section>
        <Section title="Later">
          <BulletList items={proposal.future_features} emptyText="Nothing deferred." />
        </Section>
        <Section title="User journey">
          <BulletList items={proposal.user_journey} numbered />
        </Section>
        <Section title="Architecture">
          <KeyValueList
            items={{
              frontend: arch.frontend,
              backend: arch.backend,
              database: arch.database,
              "external services": arch.external_services.join(", ") || "none",
              "AI components": arch.ai_components,
            }}
          />
        </Section>
        <Section title="Technologies">
          <BulletList items={proposal.technologies} />
        </Section>
        <Section title="Why it beats the alternatives">
          <p className="text-sm text-slate-700">{proposal.how_it_beats_alternatives}</p>
        </Section>
      </div>

      <div className="space-y-4">
        {score && (
          <Section title="Judge's scores">
            <ScoreBars score={score} />
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <div>
                <p className="text-xs font-semibold text-emerald-700">Key benefits</p>
                <BulletList items={score.key_benefits} />
              </div>
              <div>
                <p className="text-xs font-semibold text-amber-700">Key drawbacks</p>
                <BulletList items={score.key_drawbacks} />
              </div>
            </div>
            <p className="mt-2 text-xs text-slate-600">
              Confidence <strong>{score.confidence}</strong>: {score.confidence_reason}
            </p>
            {score.remaining_risks.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-semibold text-slate-500">Remaining risks</p>
                <BulletList items={score.remaining_risks} />
              </div>
            )}
          </Section>
        )}
        <Section title="Benefits">
          <BulletList items={proposal.benefits} />
        </Section>
        <Section title="Drawbacks and risks">
          <BulletList items={proposal.drawbacks_risks} />
        </Section>
        <Section title="Feasibility">
          <p className="text-sm text-slate-700">{proposal.feasibility_notes}</p>
        </Section>
        <Section title="Security and privacy">
          <p className="text-sm text-slate-700">{proposal.security_privacy_notes}</p>
        </Section>
        <Section title="Assumptions">
          <BulletList items={proposal.assumptions} emptyText="None stated." />
        </Section>
        <Section title="Evidence gaps">
          <BulletList items={proposal.evidence_gaps} emptyText="None stated." />
        </Section>
        {criticism && (
          <Section title={`Critic: ${criticism.points.length} point${criticism.points.length === 1 ? "" : "s"}`}>
            <p className="text-sm text-slate-700">{criticism.overall_assessment}</p>
            <ul className="mt-2 space-y-2">
              {criticism.points.map((pt, i) => (
                <li key={i} className="rounded-lg border border-slate-200 p-2 text-sm">
                  <div className="mb-1 flex flex-wrap gap-1">
                    <Badge tone={LEVEL_TONE[pt.severity]} size="xs">{pt.severity}</Badge>
                    <Badge tone="slate" size="xs">{titleCase(pt.category)}</Badge>
                    <Badge tone={pt.is_verified_problem ? "red" : "amber"} size="xs">{pt.is_verified_problem ? "verified problem" : "possible risk"}</Badge>
                    <Badge tone="slate" size="xs">{pt.basis === "evidence" ? pt.evidence_ids.join(", ") : "engineering judgement"}</Badge>
                  </div>
                  <p className="text-slate-800">{pt.issue}</p>
                  {pt.suggested_improvement && <p className="mt-1 text-xs text-slate-600">Fix: {pt.suggested_improvement}</p>}
                </li>
              ))}
            </ul>
          </Section>
        )}
        {claims.length > 0 && (
          <Section title="Claims checked at the source">
            <ul className="space-y-1.5">
              {claims.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <Badge tone={VERIFICATION_META[c.status].tone} size="xs">{VERIFICATION_META[c.status].label}</Badge>
                  <span className="text-slate-700">
                    {c.claim}
                    {c.is_material && <span className="ml-1 text-xs text-slate-400">(material)</span>}
                  </span>
                </li>
              ))}
            </ul>
          </Section>
        )}
        {keyEvidence.length > 0 && (
          <Section title="Key evidence">
            <ul className="space-y-1 text-sm">
              {keyEvidence.map((e) => (
                <li key={e.evidence_id} className="flex items-start gap-2">
                  <Badge tone={VERIFICATION_META[e.verification_status].tone} size="xs">{VERIFICATION_META[e.verification_status].label}</Badge>
                  <a href={e.url} target="_blank" rel="noreferrer" className="text-brand hover:underline">{e.title}</a>
                </li>
              ))}
            </ul>
          </Section>
        )}
        <p className="text-xs text-slate-500">Cites {proposal.supporting_evidence_ids.join(", ") || "no evidence"}.</p>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h4>
      {children}
    </div>
  );
}
