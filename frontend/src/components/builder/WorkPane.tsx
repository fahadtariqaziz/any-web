"use client";

// The right side of the builder: the live preview, and the documents the conversation is about (brief, plan),
// the build (tasks, build check) and the agents' activity. The tab follows the project (brief review → Brief,
// plan review → Plan, building → Build, running app → Preview) until the user picks another one.

import { Activity as ActivityIcon, FileText, Hammer, ListChecks, MonitorPlay } from "lucide-react";

import { BriefView } from "@/components/report/BriefView";
import { PlanView } from "@/components/report/PlanView";
import { ActivityFeed } from "@/components/session/ActivityFeed";
import { BuildCard, TaskList } from "@/components/session/BuildViews";
import { CostCard } from "@/components/session/CostCard";
import { NowPanel } from "@/components/session/NowPanel";
import { Callout } from "@/components/ui/Callout";
import { Spinner } from "@/components/ui/Spinner";
import type { ApiError } from "@/lib/api/client";
import type { BriefResponse, DecisionStatus, ImplementationResponse, PlanResponse, UsageResponse } from "@/lib/api/types";
import type { Activity } from "@/lib/pipeline";

import { DownloadCode } from "./DownloadCode";
import { PreviewPane } from "./PreviewPane";

export type WorkTab = "preview" | "brief" | "plan" | "build" | "activity";

export function WorkPane({
  threadId,
  tab,
  onTab,
  status,
  activity,
  now,
  fallbackStart,
  brief,
  briefError,
  plan,
  implementation,
  usage,
}: {
  threadId: string;
  tab: WorkTab;
  onTab: (tab: WorkTab) => void;
  status: DecisionStatus;
  activity: Activity;
  now: number;
  fallbackStart: number | null;
  brief: BriefResponse | null;
  briefError: ApiError | null;
  plan: PlanResponse | null;
  implementation: ImplementationResponse | null;
  usage: UsageResponse | null;
}) {
  const running = status.run_state === "running";
  const tabs: { key: WorkTab; label: string; icon: React.ReactNode; disabled: boolean }[] = [
    { key: "preview", label: "Preview", icon: <MonitorPlay className="size-4" aria-hidden />, disabled: false },
    { key: "brief", label: "Brief", icon: <FileText className="size-4" aria-hidden />, disabled: !status.has_brief },
    { key: "plan", label: "Plan", icon: <ListChecks className="size-4" aria-hidden />, disabled: !status.has_plan },
    { key: "build", label: "Build", icon: <Hammer className="size-4" aria-hidden />, disabled: !status.has_build },
    { key: "activity", label: "Activity", icon: <ActivityIcon className="size-4" aria-hidden />, disabled: false },
  ];

  let body: React.ReactNode;
  if (tab === "preview") {
    body = (
      <PreviewPane
        threadId={threadId}
        enabled={status.has_build}
        builderBusy={running}
        emptyText={
          status.has_build
            ? "The coding agent is building it task by task. The preview starts once the build check ran."
            : "First the brief and the plan, each with your approval; then the coding agent builds it and it runs here."
        }
      />
    );
  } else if (tab === "brief") {
    body = (
      <Scroll>
        {brief ? (
          <BriefView data={brief} />
        ) : briefError ? (
          <Callout tone="danger" title="Could not load the brief">
            <p>{briefError.message}</p>
          </Callout>
        ) : (
          <Loading text="Loading the brief…" />
        )}
      </Scroll>
    );
  } else if (tab === "plan") {
    body = <Scroll>{plan ? <PlanView key={`${plan.revision}`} data={plan} defaultOpen /> : <Loading text="Loading the plan…" />}</Scroll>;
  } else if (tab === "build") {
    body = (
      <Scroll>
        {implementation ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
              <span className="truncate">Project folder: {implementation.workspace_dir ?? "unknown"}</span>
            </div>
            {implementation.build && <BuildCard build={implementation.build} />}
            {usage && <CostCard usage={usage} />}
            <TaskList tasks={implementation.tasks} />
          </div>
        ) : (
          <Loading text="Loading the build…" />
        )}
      </Scroll>
    );
  } else {
    body = (
      <Scroll>
        <div className="space-y-4">
          {running && <NowPanel status={status} activity={activity} now={now} fallbackStart={fallbackStart} resuming={false} />}
          <ActivityFeed lines={status.progress} runState={status.run_state} now={now} />
        </div>
      </Scroll>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex shrink-0 items-end gap-2 border-b border-slate-200 px-2 pt-1.5">
        <div role="tablist" aria-label="Project views" className="flex min-w-0 gap-0.5 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.key}
              role="tab"
              type="button"
              aria-selected={tab === t.key}
              disabled={t.disabled}
              onClick={() => onTab(t.key)}
              className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                tab === t.key ? "border-slate-900 text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
        <DownloadCode threadId={threadId} enabled={status.has_build} busy={running} commands={plan?.plan.commands ?? null} />
      </div>
      <div className="min-h-0 flex-1">{body}</div>
    </div>
  );
}

function Scroll({ children }: { children: React.ReactNode }) {
  return <div className="h-full overflow-y-auto bg-slate-50 p-4">{children}</div>;
}

function Loading({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2 py-6 text-sm text-slate-500">
      <Spinner className="size-4 text-brand" /> {text}
    </p>
  );
}
