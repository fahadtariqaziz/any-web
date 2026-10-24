import { Badge } from "@/components/ui/Badge";
import { BulletList } from "@/components/ui/BulletList";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { KeyValueList } from "@/components/ui/KeyValueList";
import type { CaseView } from "@/lib/api/types";
import { titleCase } from "@/lib/format";

/** What the agents understood about the user: the facts every later step is based on. */
export function CaseCard({ view }: { view: CaseView }) {
  const answers = Object.entries(view.clarification_answers);
  return (
    <Card>
      <CardHeader
        eyebrow="Your profile as the agents understand it"
        title={<span className="capitalize">{view.condition_name ?? "Not yet known"}</span>}
        description={view.case_summary ?? "The intake agent fills this in from your message."}
        aside={view.condition_category && <Badge tone="slate">{titleCase(view.condition_category)}</Badge>}
      />
      <CardBody className="grid gap-6 md:grid-cols-2">
        <Section title="Health profile">
          <KeyValueList items={view.health_profile} emptyText="No facts recorded yet." />
        </Section>
        <Section title="Symptoms">
          <KeyValueList items={view.symptoms} emptyText="No symptoms recorded." />
        </Section>
        <Section title="Constraints & preferences">
          <KeyValueList items={view.constraints} emptyText="No constraints recorded." />
        </Section>
        <Section title="Assumptions the agents made">
          <BulletList items={view.assumptions} emptyText="None recorded." />
        </Section>
        {view.missing_information.length > 0 && (
          <Section title="Information still missing">
            <BulletList items={view.missing_information} />
          </Section>
        )}
        {view.user_context && (
          <Section title="Context you added">
            <p className="whitespace-pre-wrap text-sm text-slate-800">{view.user_context}</p>
          </Section>
        )}
        {answers.length > 0 && (
          <Section title="Your answers" className="md:col-span-2">
            <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {answers.map(([q, a]) => (
                <div key={q} className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-2 sm:gap-4">
                  <dt className="text-slate-600">{q}</dt>
                  <dd className={`font-medium ${a === "(skipped by user)" ? "text-slate-400" : "text-slate-900"}`}>{a}</dd>
                </div>
              ))}
            </dl>
          </Section>
        )}
      </CardBody>
    </Card>
  );
}

function Section({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`}>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h3>
      {children}
    </div>
  );
}
