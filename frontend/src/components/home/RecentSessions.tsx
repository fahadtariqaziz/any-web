"use client";

// Recent sessions from the backend (decision_sessions table), newest first. A session is reachable by its
// URL even if this list cannot be loaded, so a failure here is shown softly.

import { Clock, History } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useSessions } from "@/hooks/useLive";
import { WORKFLOW_STATUS_LABEL, relativeTime, workflowStatusTone } from "@/lib/format";

export function RecentSessions() {
  const { data, error, loading } = useSessions();
  const sessions = data?.sessions ?? [];

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <History className="size-4 text-slate-400" aria-hidden />
        <h2 className="text-lg font-semibold tracking-tight text-slate-900">Recent sessions</h2>
      </div>
      {loading && !data && (
        <ul className="space-y-2" aria-busy>
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-16 animate-pulse rounded-xl border border-slate-200 bg-white" />
          ))}
        </ul>
      )}
      {error && (
        <p className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
          The session list is unavailable right now ({error.message}). Sessions still open from their links.
        </p>
      )}
      {data && sessions.length === 0 && (
        <EmptyState icon={<Clock className="size-6" aria-hidden />} title="No sessions yet">
          Your sessions will appear here once you start one.
        </EmptyState>
      )}
      {sessions.length > 0 && (
        <ul className="space-y-2">
          {sessions.slice(0, 8).map((s) => (
            <li key={s.thread_id}>
              <Link
                href={`/decisions/${s.thread_id}`}
                className="block rounded-xl border border-slate-200 bg-white p-4 transition hover:border-brand hover:shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="min-w-0 truncate text-sm font-medium text-slate-900">
                    {s.condition_name ?? s.question}
                    {s.mode === "quick" && (
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 align-middle text-[10px] font-medium uppercase tracking-wide text-slate-500">
                        chat
                      </span>
                    )}
                  </p>
                  <Badge tone={workflowStatusTone(s.status)} size="xs">
                    {WORKFLOW_STATUS_LABEL[s.status] ?? s.status}
                  </Badge>
                </div>
                <p className="mt-1 truncate text-xs text-slate-500">“{s.question}”</p>
                <p className="mt-1 text-xs text-slate-400">
                  {relativeTime(s.created_at)}
                  {s.red_flag_count > 0 && <span className="ml-2 text-red-600">• {s.red_flag_count} warning sign(s)</span>}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
