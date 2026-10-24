"use client";

// Session page. Everything shown comes from the backend: the status (polled every 2 s while running),
// the live snapshot (re-fetched whenever a node finishes) and, once finished, the report.
//
// Layout: header → pipeline stepper → [main column | activity rail]. The main column shows exactly one
// thing for the current state: the live "now" panel, the clarification questions,
// the interrupted or failed panel, or the final report. Below it, tabs expose the agents' work so far.

import { AlertTriangle, FileText, Scale, Search, UserRound, WifiOff } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DebateView } from "@/components/debate/DebateView";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import { ReportView } from "@/components/report/ReportView";
import { ActivityFeed } from "@/components/session/ActivityFeed";
import { CaseCard } from "@/components/session/CaseCard";
import { ClarificationForm } from "@/components/session/ClarificationForm";
import { InterruptedPanel } from "@/components/session/InterruptedPanel";
import { NowPanel } from "@/components/session/NowPanel";
import { PipelineStepper } from "@/components/session/PipelineStepper";
import { RedFlagBanner } from "@/components/session/RedFlagBanner";
import { SessionHeader } from "@/components/session/SessionHeader";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { Tabs } from "@/components/ui/Tabs";
import { useDecision } from "@/hooks/useDecision";
import { useEvidence, useLive, useReport } from "@/hooks/useLive";
import { useNow } from "@/hooks/useNow";
import { deriveActivity, stageStates } from "@/lib/pipeline";

type WorkTab = "plans" | "evidence" | "profile";

export function DecisionView() {
  const { threadId } = useParams<{ threadId: string }>();
  const { status, error, refresh, lastUpdate, firstSeenRunning } = useDecision(threadId);
  const [resumeAt, setResumeAt] = useState<number | null>(null);
  const [tab, setTab] = useState<WorkTab>("plans");

  // After POST /resume the status is stale until the next GET answers: show "sending" meanwhile.
  const resuming = resumeAt != null && (lastUpdate ?? 0) < resumeAt;
  const running = status?.run_state === "running";
  const now = useNow(running || resuming);

  const activity = useMemo(() => (status ? deriveActivity(status) : null), [status]);
  const version = status
    ? `${status.run_state}|${activity?.finishedCount ?? 0}|${status.pending?.type ?? ""}|${status.counters.care_plans}|${status.counters.evidence}|${status.counters.claims_checked}`
    : "";
  const { data: live } = useLive(threadId, version, !!status);
  const finishedWithReport = status?.run_state === "finished" && status.has_report;
  const { data: reportData, error: reportError } = useReport(threadId, !!finishedWithReport);
  const { data: evidence, loading: evidenceLoading, error: evidenceError } = useEvidence(threadId, version, !!status && tab === "evidence");

  function onSubmitted() {
    setResumeAt(Date.now());
    setTab("plans");
    refresh();
  }

  if (!status) {
    if (error && error.status !== 0 && error.status < 500) {
      return (
        <div className="mx-auto max-w-lg space-y-4 py-10 text-center">
          <Callout tone="danger" title="Session not found">
            <p>{error.message}</p>
          </Callout>
          <Link href="/admin" className="text-sm font-medium text-brand hover:underline">
            Start a new session
          </Link>
        </div>
      );
    }
    return (
      <div className="space-y-4" aria-busy>
        {error ? (
          <Callout tone="warning" title="Cannot reach the backend">
            <p>{error.message} Retrying every few seconds…</p>
          </Callout>
        ) : (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner className="size-4 text-brand" /> Opening your session…
          </p>
        )}
        <div className="h-24 animate-pulse rounded-xl bg-slate-200/70" />
        <div className="h-16 animate-pulse rounded-xl bg-slate-200/70" />
      </div>
    );
  }

  const act = activity!;
  const states = stageStates(status, act);
  const pending = status.pending;
  const showRedFlagBanner = status.red_flags.length > 0;

  let main: React.ReactNode;
  if (resuming || running) {
    main = <NowPanel status={status} activity={act} now={now} fallbackStart={firstSeenRunning.current} resuming={resuming} />;
  } else if (status.run_state === "paused" && pending) {
    main = <ClarificationForm threadId={threadId} payload={pending.payload} onSubmitted={onSubmitted} />;
  } else if (status.run_state === "interrupted") {
    main = <InterruptedPanel threadId={threadId} status={status} onSubmitted={onSubmitted} />;
  } else if (finishedWithReport) {
    main = reportData ? (
      <ReportView report={reportData.report} workflowStatus={reportData.workflow_status} live={live} />
    ) : reportError ? (
      <Callout tone="danger" title="Could not load the report">
        <p>{reportError.message}</p>
      </Callout>
    ) : (
      <p className="flex items-center gap-2 text-sm text-slate-500">
        <Spinner className="size-4 text-brand" /> Loading the report…
      </p>
    );
  } else {
    main = (
      <Callout tone="danger" title="This session failed">
        <p>{status.error ? status.error.message : "The graph ended without a report."}</p>
        <div className="pt-2">
          <Link href="/admin">
            <Button variant="secondary" size="sm">Start a new session</Button>
          </Link>
        </div>
      </Callout>
    );
  }

  const planCount = live?.debate.care_plans.length ?? status.counters.care_plans;
  const evidenceCount = status.counters.evidence;

  return (
    <div className="space-y-6">
      {running && (
        <div className="no-print fixed inset-x-0 top-0 z-40 h-0.5 bg-teal-100">
          <div className="shimmer-bar h-full w-full" />
        </div>
      )}

      <SessionHeader status={status} now={now} />

      <PipelineStepper states={states} activeNode={act.activeNode} counters={status.counters} running={running} />

      {error && (
        <Callout tone="warning" title="Connection to the backend lost">
          <p className="flex items-center gap-2">
            <WifiOff className="size-4" aria-hidden /> {error.message} Showing the last known state; retrying automatically.
          </p>
        </Callout>
      )}
      {status.error && status.run_state !== "finished" && (
        <Callout tone="warning" title="The agents hit an error">
          <p className="flex items-center gap-2">
            <AlertTriangle className="size-4" aria-hidden /> {status.error.code}: {status.error.message}
          </p>
        </Callout>
      )}
      {showRedFlagBanner && <RedFlagBanner flags={status.red_flags} withdrawn={live?.case.withdrawn_red_flags ?? []} />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-6">
          {main}

          <section className="space-y-3">
            <Tabs<WorkTab>
              items={[
                { key: "plans", label: <span className="inline-flex items-center gap-1.5"><Scale className="size-4" aria-hidden /> Plans & debate</span>, count: planCount },
                { key: "evidence", label: <span className="inline-flex items-center gap-1.5"><Search className="size-4" aria-hidden /> Evidence</span>, count: evidenceCount },
                { key: "profile", label: <span className="inline-flex items-center gap-1.5"><UserRound className="size-4" aria-hidden /> Your profile</span> },
              ]}
              value={tab}
              onChange={setTab}
            />
            {tab === "plans" && (live ? <DebateView live={live} /> : <LoadingLine text="Loading the agents' work…" />)}
            {tab === "evidence" && <EvidencePanel data={evidence} loading={evidenceLoading} error={evidenceError} />}
            {tab === "profile" && (live ? <CaseCard view={live.case} /> : <LoadingLine text="Loading your profile…" />)}
          </section>

          {finishedWithReport && !reportData && !reportError && (
            <Card>
              <CardBody className="flex items-center gap-2 text-sm text-slate-500">
                <FileText className="size-4" aria-hidden /> The report is being fetched…
              </CardBody>
            </Card>
          )}
        </div>

        <aside className="no-print min-w-0 lg:sticky lg:top-20 lg:self-start">
          <ActivityFeed lines={status.progress} runState={status.run_state} now={now} />
        </aside>
      </div>
    </div>
  );
}

function LoadingLine({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2 py-6 text-sm text-slate-500">
      <Spinner className="size-4 text-brand" /> {text}
    </p>
  );
}
