"use client";

// The three winning plans side by side, one row per topic (routine, diet, medications...). On large
// screens it is a real grid so rows line up; on small screens one domain is shown at a time.

import { useState } from "react";

import { BulletList } from "@/components/ui/BulletList";
import { Markdown } from "@/components/ui/Markdown";
import { Tabs } from "@/components/ui/Tabs";
import type { CarePlan, Domain, DomainResult } from "@/lib/api/types";
import { DOMAIN_META } from "@/lib/format";

interface Row {
  label: string;
  render: (plan: CarePlan) => React.ReactNode;
}

const ROWS: Row[] = [
  { label: "Daily routine", render: (p) => <BulletList items={p.daily_routine} emptyText="Not covered." /> },
  { label: "Diet", render: (p) => <BulletList items={p.diet} emptyText="Not covered." /> },
  { label: "Medications & treatments", render: (p) => <BulletList items={p.medications_treatments} emptyText="Not covered." /> },
  { label: "Expected timeline", render: (p) => <Markdown compact>{p.expected_timeline}</Markdown> },
  { label: "Prevalence & outlook", render: (p) => <Markdown compact>{p.prevalence_and_outlook}</Markdown> },
  { label: "Benefits", render: (p) => <BulletList items={p.benefits} emptyText="None listed." /> },
  { label: "Drawbacks & risks", render: (p) => <BulletList items={p.drawbacks_risks} emptyText="None listed." /> },
  { label: "Safety notes", render: (p) => <Markdown compact>{p.safety_notes}</Markdown> },
];

export function ComparisonGrid({ domains }: { domains: DomainResult[] }) {
  const [selected, setSelected] = useState<Domain>(domains[0]?.domain ?? "research");
  const visible = domains.find((p) => p.domain === selected) ?? domains[0];

  return (
    <div>
      {/* Small screens: one domain at a time */}
      <div className="space-y-4 lg:hidden">
        <Tabs
          items={domains.map((p) => ({ key: p.domain, label: DOMAIN_META[p.domain].short }))}
          value={selected}
          onChange={setSelected}
        />
        {visible && (
          <div className="space-y-4">
            {ROWS.map((row) => (
              <div key={row.label} className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{row.label}</p>
                {visible.plan ? row.render(visible.plan) : <p className="text-sm text-slate-500">No plan from this domain.</p>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Large screens: aligned grid */}
      <div className="hidden lg:grid lg:grid-cols-[160px_repeat(3,minmax(0,1fr))] lg:gap-x-4">
        <div />
        {domains.map((p) => {
          const meta = DOMAIN_META[p.domain];
          return (
            <div key={p.domain} className={`rounded-t-lg border-b-2 px-3 py-2 ${meta.bg} ${meta.border}`}>
              <p className={`text-sm font-semibold ${meta.text}`}>{meta.short}</p>
              <p className="truncate text-xs text-slate-600">{p.plan?.name ?? "No plan"}</p>
            </div>
          );
        })}
        {ROWS.map((row) => (
          <div key={row.label} className="contents">
            <div className="border-b border-slate-100 py-3 pr-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{row.label}</div>
            {domains.map((p) => (
              <div key={p.domain} className="border-b border-slate-100 px-3 py-3 text-sm">
                {p.plan ? row.render(p.plan) : <span className="text-slate-400">—</span>}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
