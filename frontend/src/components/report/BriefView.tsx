"use client";

// The problem statement + solution brief (M4), read-only once the session moved past the review (the review itself is
// BriefReviewPanel). The markdown is rendered by the backend (labels, reference numbers, appendix); this view adds
// what the validator found: the verdict, the checks, the open issues.

import { ClipboardCheck, FileText, Printer } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Markdown } from "@/components/ui/Markdown";
import type { BriefResponse, ValidationCheck } from "@/lib/api/types";
import { formatDateTime, LEVEL_TONE } from "@/lib/format";

const CHECK_LABEL: Record<string, string> = {
  det_known_evidence_ids: "Every cited source exists",
  det_cited_labels_have_evidence: "Research statements cite a source",
  det_targets_have_basis: "Numeric targets have a basis",
  det_sections_present: "All ten sections present",
  det_no_unknown_urls: "No links outside the research",
  det_word_budget: "About one page",
  problem_clear_and_consistent: "Problem clear and consistent with your answers",
  solution_not_a_copy: "Solves the problem, not a copy of an existing app",
  recommendations_supported: "Recommendations supported or labelled",
  technically_plausible: "Technically plausible",
  scope_separates_mvp: "MVP separated from later features",
  success_criteria_measurable: "Measurable success, no invented targets",
  risks_and_questions_disclosed: "Risks and open questions disclosed",
  claims_have_sources: "Claims have sources",
  concise_consistent_readable: "Concise and readable",
};

export function BriefView({ data }: { data: BriefResponse }) {
  const [showChecks, setShowChecks] = useState(false);
  const { brief, validation } = data;
  const passed = validation.checks.filter((c) => c.passed).length;
  const failed = validation.checks.filter((c) => !c.passed);

  return (
    <Card className="animate-fade-up">
      <CardHeader
        eyebrow="Problem statement and solution brief"
        title={
          <span className="flex items-center gap-2">
            <FileText className="size-5 text-brand" aria-hidden />
            <span className="capitalize">{brief.project_overview.proposed_name || brief.project_name}</span>
          </span>
        }
        description={`Draft ${brief.revision + 1} · ${formatDateTime(brief.generated_at)} · ${validation.word_count} words before the appendix`}
        aside={
          <>
            {data.approved_at && (
              <Badge tone="emerald" size="md">
                Approved {formatDateTime(data.approved_at)}
              </Badge>
            )}
            <Badge tone={failed.length ? "amber" : "emerald"} size="md">
              {passed} of {validation.checks.length} checks passed
            </Badge>
            <Button variant="secondary" size="sm" className="no-print" icon={<Printer className="size-4" aria-hidden />} onClick={() => window.print()}>
              Print / save PDF
            </Button>
          </>
        }
      />
      <CardBody className="space-y-4">
        {validation.open_issues.length > 0 && (
          <Callout tone="warning" title="Validated with open issues">
            <p>The validator could not resolve everything within its revision limit. The open issues are listed at the end of the brief.</p>
          </Callout>
        )}
        <div className="no-print">
          <button
            type="button"
            onClick={() => setShowChecks((v) => !v)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline"
          >
            <ClipboardCheck className="size-4" aria-hidden /> {showChecks ? "Hide" : "Show"} the validation checks
          </button>
          {showChecks && <ChecksList checks={validation.checks} summary={validation.llm_summary} />}
        </div>
        <Markdown>{data.markdown}</Markdown>
      </CardBody>
    </Card>
  );
}

function ChecksList({ checks, summary }: { checks: ValidationCheck[]; summary: string }) {
  return (
    <div className="mt-3 space-y-2 rounded-xl bg-slate-50 p-4 text-sm">
      {summary && <p className="text-slate-600">{summary}</p>}
      <ul className="space-y-1.5">
        {checks.map((c) => (
          <li key={`${c.source}-${c.check_id}`} className="flex flex-wrap items-start gap-2">
            <Badge tone={c.passed ? "emerald" : LEVEL_TONE[c.severity]} size="xs">
              {c.passed ? "passed" : c.severity}
            </Badge>
            <span className="text-slate-800">{CHECK_LABEL[c.check_id] ?? c.check_id}</span>
            <span className="text-xs text-slate-400">{c.source === "deterministic" ? "rule" : "review"}</span>
            {!c.passed && c.issue && <span className="w-full pl-1 text-slate-600">{c.issue}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
