"use client";

// The implementation plan once the session moved past the plan review (read-only; the review is PlanReviewPanel).
// Collapsed by default: the plan is long, and the brief above it is what most readers check first.

import { ChevronDown, ListChecks } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Markdown } from "@/components/ui/Markdown";
import type { PlanResponse } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

export function PlanView({ data }: { data: PlanResponse }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="animate-fade-up">
      <CardHeader
        eyebrow="Implementation plan"
        title={
          <span className="flex items-center gap-2">
            <ListChecks className="size-5 text-brand" aria-hidden />
            {data.plan.phases.length} phases · {data.plan.tasks.length} tasks
            {data.tasks.length > data.plan.tasks.length && (
              <span className="text-sm font-normal text-slate-500">
                · +{data.tasks.length - data.plan.tasks.length} added later (build fixes, change requests)
              </span>
            )}
          </span>
        }
        description={`Plan version ${data.revision + 1} · written by ${data.model}`}
        aside={
          data.approved_at ? (
            <Badge tone="emerald" size="md">
              Approved {formatDateTime(data.approved_at)}
            </Badge>
          ) : (
            <Badge tone="amber" size="md">
              Not approved
            </Badge>
          )
        }
      />
      <CardBody className="space-y-3">
        <p className="text-sm text-slate-700">{data.plan.summary}</p>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="no-print inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline"
        >
          <ChevronDown className={`size-4 transition ${open ? "rotate-180" : ""}`} aria-hidden /> {open ? "Hide" : "Show"} the full plan
        </button>
        {open && <Markdown>{data.markdown}</Markdown>}
      </CardBody>
    </Card>
  );
}
