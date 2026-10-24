"use client";

// Every kept source, per perspective, with its excerpt, the claims it supports and its verification status.
// Filters are local; the list itself comes from GET /evidence.

import { ExternalLink, Quote, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { Tabs } from "@/components/ui/Tabs";
import type { ApiError } from "@/lib/api/client";
import type { Evidence, EvidenceResponse, Perspective, VerificationStatus } from "@/lib/api/types";
import { PERSPECTIVES, PERSPECTIVE_META, SOURCE_TYPE_LABEL, STRENGTH_LABEL, VERIFICATION_META, formatDateTime, hostname } from "@/lib/format";

type LaneFilter = "all" | Perspective;
type StatusFilter = "all" | VerificationStatus;

export function EvidencePanel({ data, loading, error }: { data: EvidenceResponse | null; loading: boolean; error: ApiError | null }) {
  const [lane, setLane] = useState<LaneFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");

  const items = useMemo(() => data?.evidence ?? [], [data]);
  const byLane = useMemo(() => Object.fromEntries(PERSPECTIVES.map((p) => [p, items.filter((e) => e.perspective === p).length])), [items]);

  const filtered = items.filter((e) => {
    if (lane !== "all" && e.perspective !== lane) return false;
    if (status !== "all" && e.verification_status !== status) return false;
    if (query) {
      const q = query.toLowerCase();
      return [e.source_title, e.relevant_excerpt, ...e.claims_supported, e.source_url].some((t) => t.toLowerCase().includes(q));
    }
    return true;
  });

  if (!data && loading) {
    return (
      <p className="flex items-center gap-2 py-6 text-sm text-slate-500">
        <Spinner className="size-4 text-brand" /> Loading evidence…
      </p>
    );
  }
  if (error && !data) return <p className="py-6 text-sm text-red-700">Could not load the evidence: {error.message}</p>;
  if (items.length === 0) {
    return (
      <EmptyState icon={<Search className="size-6" aria-hidden />} title="No evidence yet">
        Sources appear here as soon as the research agent has read the search results. Each one is kept with a short excerpt and a
        reason, or rejected with a reason.
      </EmptyState>
    );
  }

  const statusCounts = data?.verification_counts ?? {};

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs<LaneFilter>
          items={[{ key: "all", label: "All lanes", count: items.length }, ...PERSPECTIVES.map((p) => ({ key: p, label: PERSPECTIVE_META[p].short, count: byLane[p] }))]}
          value={lane}
          onChange={setLane}
          size="sm"
        />
        <label className="relative ml-auto">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search titles, excerpts, claims"
            className="w-64 rounded-lg border border-slate-300 py-1.5 pl-8 pr-3 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
          />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-slate-500">Verification:</span>
        <FilterChip active={status === "all"} onClick={() => setStatus("all")}>all</FilterChip>
        {(Object.keys(VERIFICATION_META) as VerificationStatus[])
          .filter((k) => statusCounts[k])
          .map((k) => (
            <FilterChip key={k} active={status === k} onClick={() => setStatus(status === k ? "all" : k)}>
              {VERIFICATION_META[k].label} · {statusCounts[k]}
            </FilterChip>
          ))}
      </div>

      <p className="text-xs text-slate-500">
        {filtered.length} of {items.length} sources
      </p>
      <ul className="space-y-3">
        {filtered.map((e) => (
          <EvidenceItem key={e.evidence_id} e={e} />
        ))}
      </ul>
    </div>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-0.5 ${active ? "border-brand bg-brand-faint text-brand-strong" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"}`}
    >
      {children}
    </button>
  );
}

function EvidenceItem({ e }: { e: Evidence }) {
  const meta = PERSPECTIVE_META[e.perspective];
  const verification = VERIFICATION_META[e.verification_status];
  return (
    <li className={`rounded-xl border bg-white p-4 ${meta.border}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <Badge tone="slate" size="xs" className="font-mono">{e.evidence_id}</Badge>
            <span className={`inline-flex items-center gap-1 font-medium ${meta.text}`}>
              <span className={`size-1.5 rounded-full ${meta.dot}`} />
              {meta.short}
            </span>
            <span className="text-slate-400">·</span>
            <span className="text-slate-600">{SOURCE_TYPE_LABEL[e.source_type] ?? e.source_type}</span>
            <span className="text-slate-400">·</span>
            <span className="text-slate-600">{STRENGTH_LABEL[e.evidence_strength] ?? e.evidence_strength}</span>
          </div>
          <a href={e.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 text-sm font-semibold text-slate-900 hover:text-brand">
            <span className="min-w-0">{e.source_title}</span>
            <ExternalLink className="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden />
          </a>
          <p className="text-xs text-slate-500">
            {hostname(e.source_url)}
            {e.published_at && <> · published {formatDateTime(e.published_at)}</>}
            {" · relevance "}
            {Math.round(e.relevance_score * 100)}%
          </p>
        </div>
        <Badge tone={verification.tone} size="sm">{verification.label}</Badge>
      </div>
      <blockquote className={`mt-3 flex gap-2 rounded-lg px-3 py-2 text-sm text-slate-800 ${meta.bg}`}>
        <Quote className="mt-0.5 size-4 shrink-0 text-slate-400" aria-hidden />
        <span>
          {e.relevant_excerpt}
          {!e.is_direct_quote && <span className="ml-1 text-xs text-slate-500">(paraphrased)</span>}
        </span>
      </blockquote>
      <div className="mt-3 grid gap-3 text-xs sm:grid-cols-2">
        {e.claims_supported.length > 0 && (
          <div>
            <p className="font-semibold text-slate-500">Supports</p>
            <ul className="list-disc pl-4 text-slate-700">
              {e.claims_supported.map((c) => <li key={c}>{c}</li>)}
            </ul>
          </div>
        )}
        {e.limitations.length > 0 && (
          <div>
            <p className="font-semibold text-slate-500">Limitations</p>
            <ul className="list-disc pl-4 text-slate-700">
              {e.limitations.map((c) => <li key={c}>{c}</li>)}
            </ul>
          </div>
        )}
        {e.patient_context && (
          <div className="sm:col-span-2">
            <p className="font-semibold text-slate-500">Patient context</p>
            <p className="text-slate-700">
              {e.patient_context.experience_described}
              <span className="ml-1 text-slate-500">({e.patient_context.is_recurring ? "reported by several people" : "one person's report"})</span>
            </p>
          </div>
        )}
        {e.reliability_notes && (
          <p className="text-slate-500 sm:col-span-2">
            <span className="font-semibold">Reliability:</span> {e.reliability_notes}
          </p>
        )}
      </div>
    </li>
  );
}
