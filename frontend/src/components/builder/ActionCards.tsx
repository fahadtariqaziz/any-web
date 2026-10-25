"use client";

// The cards at the end of the conversation when the builder needs the user or is building: the brief and plan
// reviews (Approve here; changes are typed in the message box), the build progress, the running app (Finish here;
// changes in the message box) and the finished session. Every number is a fact from the backend.

import { CheckCircle2, FileText, Flag, Hammer, ListChecks, MonitorPlay, PanelRight, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type {
  BriefReviewPayload,
  BuildResults,
  ChangeRequestPayload,
  ImplementationResponse,
  PlanReviewPayload,
  PreviewInfo,
  ReviewTarget,
} from "@/lib/api/types";

import { projectTitle } from "./ProjectListContext";

const TARGETS: { value: ReviewTarget; label: string }[] = [
  { value: "auto", label: "Let the agents decide" },
  { value: "wording", label: "Wording only (fastest)" },
  { value: "proposal", label: "A different solution" },
  { value: "research", label: "More or better research" },
  { value: "requirements", label: "You misunderstood me (redoes everything)" },
];

function ActionCard({ tone = "amber", icon, eyebrow, title, children }: { tone?: "amber" | "brand" | "slate" | "red"; icon: React.ReactNode; eyebrow: string; title: React.ReactNode; children?: React.ReactNode }) {
  const border = { amber: "border-amber-200 bg-amber-50/40", brand: "border-teal-200 bg-brand-faint", slate: "border-slate-200 bg-white", red: "border-red-200 bg-red-50/40" }[tone];
  return (
    <div className={`animate-fade-up space-y-3 rounded-xl border p-4 ${border}`}>
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 shrink-0">{icon}</span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{eyebrow}</p>
          <p className="font-semibold leading-snug text-slate-900">{title}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function OpenButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <Button variant="secondary" size="sm" onClick={onClick} icon={<PanelRight className="size-4" aria-hidden />}>
      {children}
    </Button>
  );
}

export function BriefReviewCard({
  payload,
  target,
  onTarget,
  onApprove,
  approving,
  onOpen,
}: {
  payload: BriefReviewPayload;
  target: ReviewTarget;
  onTarget: (t: ReviewTarget) => void;
  onApprove: () => void;
  approving: boolean;
  onOpen: () => void;
}) {
  const s = payload.validation_summary;
  const targets = payload.wording_only ? TARGETS.filter((t) => t.value === "auto" || t.value === "wording") : TARGETS;
  return (
    <ActionCard
      icon={<FileText className="size-5 text-amber-600" aria-hidden />}
      eyebrow={`Your review · round ${payload.round}`}
      title="Does this brief describe your problem and the solution you want?"
    >
      <p className="text-sm text-slate-600">
        {projectTitle(payload.brief.project_overview.proposed_name || payload.brief.project_name, null)}: {s.word_count} words, {s.checks_passed} of {s.checks_total} checks
        passed{s.open_issues.length ? `, ${s.open_issues.length} open issue${s.open_issues.length > 1 ? "s" : ""}` : ""}. Approve it to plan the build,
        or type what should change below.
      </p>
      {payload.error && <p className="text-sm text-amber-800">Your previous reply was not accepted: {payload.error}</p>}
      {payload.wording_only && (
        <p className="text-sm text-slate-600">
          {payload.wording_only_reason === "built"
            ? "Your app is already built, so the brief is edited directly (no new research or solution, which would describe a different app)."
            : `It was revised ${payload.max_rounds} times: only wording changes are accepted now.`}
        </p>
      )}
      <label className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        A change goes to
        <select
          value={target}
          onChange={(e) => onTarget(e.target.value as ReviewTarget)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
        >
          {targets.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap gap-2">
        <OpenButton onClick={onOpen}>Read the brief</OpenButton>
        <Button size="sm" onClick={onApprove} loading={approving} icon={<CheckCircle2 className="size-4" aria-hidden />}>
          Approve the brief
        </Button>
      </div>
    </ActionCard>
  );
}

export function PlanReviewCard({
  payload,
  onApprove,
  approving,
  onOpen,
}: {
  payload: PlanReviewPayload;
  onApprove: () => void;
  approving: boolean;
  onOpen: () => void;
}) {
  return (
    <ActionCard
      icon={<ListChecks className="size-5 text-amber-600" aria-hidden />}
      eyebrow={`Your review · plan version ${payload.round}`}
      title={
        payload.new_task_count != null && payload.new_task_count < payload.task_count
          ? `${payload.new_task_count} new task${payload.new_task_count === 1 ? "" : "s"} · ${payload.task_count - payload.new_task_count} already built`
          : `${payload.plan.phases.length} phases · ${payload.task_count} tasks`
      }
    >
      <p className="text-sm text-slate-700">{payload.plan.summary}</p>
      <p className="text-xs text-slate-500">
        Written by {payload.model}. Nothing is built before you approve.{" "}
        {payload.changes_allowed ? "Type what should change below, or approve." : "It was revised the maximum number of times: approve it, or start a new project."}
      </p>
      {payload.error && <p className="text-sm text-amber-800">Your previous reply was not accepted: {payload.error}</p>}
      <div className="flex flex-wrap gap-2">
        <OpenButton onClick={onOpen}>Read the plan</OpenButton>
        <Button size="sm" onClick={onApprove} loading={approving} icon={<CheckCircle2 className="size-4" aria-hidden />}>
          Approve and build
        </Button>
      </div>
    </ActionCard>
  );
}

/** While the coding agent works: tasks done so far (done = its verify commands passed) and the task in progress. */
export function BuildProgressCard({ implementation, onOpen }: { implementation: ImplementationResponse; onOpen: () => void }) {
  const tasks = implementation.tasks;
  const done = tasks.filter((t) => t.status === "done").length;
  const failed = tasks.filter((t) => t.status === "failed" || t.status === "blocked").length;
  const current = tasks.find((t) => t.id === implementation.current_task_id && t.status === "pending") ?? tasks.find((t) => t.status === "pending");
  const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
  return (
    <ActionCard tone="slate" icon={<Hammer className="size-5 text-brand" aria-hidden />} eyebrow="Building" title={`${done} of ${tasks.length} tasks done`}>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${pct}%` }} />
      </div>
      {current && (
        <p className="text-sm text-slate-600">
          Now: <span className="font-mono text-slate-500">{current.id}</span> {current.title}
          {current.attempts > 0 && <span className="text-slate-400"> (attempt {current.attempts + 1})</span>}
        </p>
      )}
      {failed > 0 && <p className="text-sm text-red-700">{failed} task{failed > 1 ? "s" : ""} failed or blocked.</p>}
      <OpenButton onClick={onOpen}>Show the tasks</OpenButton>
    </ActionCard>
  );
}

function isBuild(b: ChangeRequestPayload["build"]): b is BuildResults {
  return "steps" in b;
}
function isPreview(p: ChangeRequestPayload["preview"]): p is PreviewInfo {
  return "state" in p;
}

export function AppRunningCard({
  payload,
  onFinish,
  finishing,
  onOpenPreview,
  onOpenBuild,
}: {
  payload: ChangeRequestPayload;
  onFinish: () => void;
  finishing: boolean;
  onOpenPreview: () => void;
  onOpenBuild: () => void;
}) {
  const build = isBuild(payload.build) ? payload.build : null;
  const preview = isPreview(payload.preview) ? payload.preview : null;
  const running = preview?.state === "ready";
  const done = payload.tasks.filter((t) => t.status === "done").length;
  return (
    <ActionCard
      tone={running && build?.passed ? "brand" : "red"}
      icon={running ? <MonitorPlay className="size-5 text-brand" aria-hidden /> : <TriangleAlert className="size-5 text-red-600" aria-hidden />}
      eyebrow={`Your turn · round ${payload.round}`}
      title={running ? "Your app is running in the preview" : "Your app did not start"}
    >
      <div className="flex flex-wrap gap-1.5">
        <Badge tone={build?.passed ? "emerald" : "red"}>Build {build?.passed ? "passed" : "failed"}</Badge>
        <Badge tone={done === payload.tasks.length ? "emerald" : "amber"}>
          {done}/{payload.tasks.length} tasks done
        </Badge>
        <Badge tone="slate">Agent cost ${payload.cost_usd.toFixed(2)}</Badge>
      </div>
      <p className="text-sm text-slate-600">
        {payload.changes_allowed
          ? "Try it, then type a change below (or plan a bigger change). Finish when you are happy."
          : "The maximum number of change requests was reached: finish this project, or start a new one."}
      </p>
      {payload.error && <p className="text-sm text-amber-800">Your previous reply was not accepted: {payload.error}</p>}
      <div className="flex flex-wrap gap-2">
        <OpenButton onClick={running ? onOpenPreview : onOpenBuild}>{running ? "Show the preview" : "Show the errors"}</OpenButton>
        <Button variant="secondary" size="sm" onClick={onFinish} loading={finishing} icon={<Flag className="size-4" aria-hidden />}>
          Finish
        </Button>
      </div>
    </ActionCard>
  );
}
