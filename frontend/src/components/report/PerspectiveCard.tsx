"use client";

// One domain's winning plan at a glance: score, confidence, verification counts, top objections.
// Used in the final report.

import { ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Markdown } from "@/components/ui/Markdown";
import type { Level, Domain, VerificationStatus } from "@/lib/api/types";
import { CONFIDENCE_TONE, LEVEL_TONE, DOMAIN_META, VERIFICATION_META, titleCase } from "@/lib/format";

const VERIFICATION_ORDER: VerificationStatus[] = ["verified", "partially_supported", "unsupported", "contradicted", "unavailable", "irrelevant", "pending"];

export function VerificationChips({ counts, size = "xs" }: { counts: Record<string, number>; size?: "xs" | "sm" }) {
  const entries = VERIFICATION_ORDER.filter((k) => counts[k]).map((k) => [k, counts[k]] as const);
  if (entries.length === 0) return <span className="text-xs text-slate-400">No claims checked</span>;
  return (
    <ul className="flex flex-wrap gap-1" aria-label="Claim verification">
      {entries.map(([k, n]) => (
        <li key={k}>
          <Badge tone={VERIFICATION_META[k].tone} size={size}>
            {n} {VERIFICATION_META[k].label.toLowerCase()}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

/** Objections arrive as "[medium/missing_consideration] text" (older reports: "[medium] text"). */
function parseObjection(text: string): { severity: Level | null; category: string | null; text: string } {
  const m = /^\[(low|medium|high)(?:\/([a-z_]+))?\]\s*/.exec(text);
  if (!m) return { severity: null, category: null, text };
  return { severity: m[1] as Level, category: m[2] ?? null, text: text.slice(m[0].length) };
}

function asLevel(v: string | null | undefined): Level | null {
  return v === "low" || v === "medium" || v === "high" ? v : null;
}

export function PerspectiveCard({
  domain,
  planId,
  name,
  summary,
  weightedTotal,
  confidence,
  difficulty,
  verificationCounts,
  objections,
  unavailableReason,
  expanded,
  onToggle,
}: {
  domain: Domain;
  planId: string | null;
  name: string | null;
  summary: string | null;
  weightedTotal: number | null;
  confidence: string | null;
  difficulty: string | null;
  verificationCounts: Record<string, number>;
  objections: string[];
  unavailableReason: string | null;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const meta = DOMAIN_META[domain];
  const conf = asLevel(confidence);
  const diff = asLevel(difficulty);
  return (
    <article className={`flex flex-col rounded-xl border bg-white ${meta.border}`}>
      <div className={`flex items-center justify-between gap-2 rounded-t-xl border-b px-4 py-2.5 ${meta.bg} ${meta.border}`}>
        <p className={`flex items-center gap-2 text-sm font-semibold ${meta.text}`}>
          <span className={`size-2 rounded-full ${meta.dot}`} />
          {meta.label}
        </p>
      </div>
      <div className="flex flex-1 flex-col gap-3 px-4 py-4">
        <p className="text-xs text-slate-500">{meta.description}</p>
        {planId && name ? (
          <>
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-base font-semibold leading-snug text-slate-900">{name}</h3>
              {weightedTotal != null && (
                <p className="shrink-0 text-right">
                  <span className="text-2xl font-semibold tabular-nums text-slate-900">{weightedTotal.toFixed(1)}</span>
                  <span className="text-xs text-slate-400"> / 10</span>
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {conf && <Badge tone={CONFIDENCE_TONE[conf]} size="xs">{conf} confidence</Badge>}
              {diff && <Badge tone={LEVEL_TONE[diff]} size="xs">{diff} effort</Badge>}
              <Badge tone="slate" size="xs" className="font-mono">
                {planId}
              </Badge>
            </div>
            {summary && <Markdown compact className="text-slate-700">{summary}</Markdown>}
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Claims verified at source</p>
              <VerificationChips counts={verificationCounts} />
            </div>
            {objections.length > 0 && (
              <div className="space-y-1">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Critic&apos;s top objections</p>
                <ul className="space-y-1.5 text-xs text-slate-700">
                  {objections.map((o) => {
                    const { severity, category, text } = parseObjection(o);
                    return (
                      <li key={o} className="space-y-0.5">
                        {(severity || category) && (
                          <span className="flex flex-wrap gap-1">
                            {severity && <Badge tone={LEVEL_TONE[severity]} size="xs">{severity}</Badge>}
                            {category && <Badge tone="slate" size="xs">{titleCase(category)}</Badge>}
                          </span>
                        )}
                        <span className="block">{text}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </>
        ) : (
          <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            <p className="font-medium text-slate-800">No plan from this domain</p>
            <p>{unavailableReason ?? "The evidence did not support a defensible plan."}</p>
          </div>
        )}
        {onToggle && (
          <button type="button" onClick={onToggle} aria-expanded={expanded} className="mt-auto inline-flex items-center gap-1 self-start text-xs font-medium text-brand hover:underline">
            <ChevronDown className={`size-3.5 transition ${expanded ? "rotate-180" : ""}`} aria-hidden />
            {expanded ? "Hide the full plan" : "Show the full plan, scores and critique"}
          </button>
        )}
      </div>
    </article>
  );
}
