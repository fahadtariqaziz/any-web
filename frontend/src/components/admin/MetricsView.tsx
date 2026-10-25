"use client";

// Observability across projects (M11, GET /api/metrics): what the builder's own model calls cost, per node and per
// day, which models ran, how often nodes failed, and the outcome of every kind of tool call (agent tool decisions,
// sandbox commands, Ask tools, research searches). Tables only: exact numbers matter more than shapes here.

import { useState } from "react";

import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { useFetch } from "@/hooks/useFetch";
import { getMetrics } from "@/lib/api/client";
import type { UsageTotals } from "@/lib/api/types";

const DAYS = [1, 7, 30];
const usd = (v: number) => (v > 0 && v < 0.01 ? "<$0.01" : `$${v.toFixed(2)}`);
const int = (v: number) => v.toLocaleString();

function Table({
  head,
  rows,
}: {
  head: string[];
  rows: (string | number)[][];
}) {
  if (!rows.length)
    return (
      <p className="text-sm text-slate-500">Nothing recorded in this period.</p>
    );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            {head.map((h, i) => (
              <th
                key={h}
                className={`py-2 pr-4 font-semibold ${i ? "text-right" : ""}`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={String(r[0])}>
              {r.map((c, i) => (
                <td
                  key={i}
                  className={`py-1.5 pr-4 tabular-nums ${i ? "text-right text-slate-700" : "text-slate-900"}`}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function usageRow(label: string, u: UsageTotals): (string | number)[] {
  return [
    label,
    int(u.runs),
    int(u.calls),
    int(u.failed_calls),
    int(u.node_failures),
    int(u.input_tokens + u.cache_read_tokens + u.cache_write_tokens),
    int(u.output_tokens),
    usd(u.cost_usd),
  ];
}

const USAGE_HEAD = [
  "",
  "Runs",
  "Calls",
  "Bad answers",
  "Failures",
  "Input tokens",
  "Output tokens",
  "Cost",
];

export function MetricsView() {
  const [days, setDays] = useState(7);
  const { data, error, loading } = useFetch(
    () => getMetrics(days),
    String(days),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Metrics
          </h1>
          <p className="text-sm text-slate-600">
            The builder&apos;s own model calls (measured per node run and per
            Ask reply), coding-agent spend of finished projects, and every tool
            call&apos;s outcome.
          </p>
        </div>
        <div role="group" aria-label="Period" className="flex gap-1">
          {DAYS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              aria-pressed={days === d}
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium ${days === d ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}
            >
              {d === 1 ? "24 h" : `${d} days`}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <Callout tone="danger" title="Could not load the metrics">
          <p>{error.message}</p>
        </Callout>
      )}
      {loading && !data && <p className="text-sm text-slate-500">Loading…</p>}

      {data && (
        <>
          <Card>
            <CardHeader
              title="Totals"
              description={`Since ${new Date(data.since).toLocaleString()}`}
            />
            <CardBody>
              <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
                {[
                  ["Builder AI cost", usd(data.total.cost_usd)],
                  [
                    "Coding agent (finished projects)",
                    data.agent.sessions
                      ? `${usd(data.agent.cost_usd ?? 0)} across ${data.agent.sessions} project${data.agent.sessions === 1 ? "" : "s"}`
                      : "—",
                  ],
                  ["Projects with model calls", int(data.total.sessions)],
                  ["Model calls", int(data.total.calls)],
                  [
                    "Answers that failed validation",
                    int(data.total.failed_calls),
                  ],
                  ["Node failures", int(data.total.node_failures)],
                ].map(([k, v]) => (
                  <div
                    key={k}
                    className="flex justify-between gap-3 border-b border-slate-100 py-1"
                  >
                    <dt className="text-slate-600">{k}</dt>
                    <dd className="font-medium tabular-nums text-slate-900">
                      {v}
                    </dd>
                  </div>
                ))}
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="By node"
              description="Which agent spends what (Ask = the project assistant's replies)."
            />
            <CardBody>
              <Table
                head={USAGE_HEAD}
                rows={data.by_node.map((n) => usageRow(n.node, n))}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Tools"
              description="Agent tool decisions, sandbox commands, Ask tools and research searches. Refused = denied by the path guard or the command policy."
            />
            <CardBody>
              <Table
                head={[
                  "Source · tool",
                  "Calls",
                  "Failed",
                  "Refused",
                  "Timed out",
                  "Avg seconds",
                ]}
                rows={data.tools.map((t) => [
                  `${t.source} · ${t.tool}`,
                  int(t.calls),
                  int(t.failed),
                  int(t.refused),
                  int(t.timed_out),
                  t.avg_seconds.toFixed(2),
                ])}
              />
            </CardBody>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="By day" />
              <CardBody>
                <Table
                  head={["Day", "Calls", "Failures", "Cost"]}
                  rows={data.by_day.map((d) => [
                    d.day,
                    int(d.calls),
                    int(d.node_failures),
                    usd(d.cost_usd),
                  ])}
                />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Models" />
              <CardBody>
                <Table
                  head={["Model", "Calls"]}
                  rows={Object.entries(data.calls_by_model).map(([m, n]) => [
                    m,
                    int(n),
                  ])}
                />
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
