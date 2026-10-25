"use client";

// One project in the builder (spec §9): the conversation on the left, the live preview (and the brief, the plan,
// the build, the agents' activity) on the right. On small screens one side at a time, with a switch.
//
// Everything comes from the backend: the status (useDecision: every 2 s while running, 5 s while paused), the
// brief / plan / build when they exist (re-fetched when the project moves on), the preview (PreviewPane polls).

import { MessageSquare, MonitorPlay } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { Spinner } from "@/components/ui/Spinner";
import { useDecision } from "@/hooks/useDecision";
import { useFetch } from "@/hooks/useFetch";
import { useNow } from "@/hooks/useNow";
import { getBrief, getImplementation, getPlan, getUsage } from "@/lib/api/client";
import type { DecisionStatus } from "@/lib/api/types";
import { deriveActivity } from "@/lib/pipeline";

import { ChatPane } from "./ChatPane";
import { ResizeHandle, useChatWidth } from "./ResizeHandle";
import { WorkPane, type WorkTab } from "./WorkPane";

/** The tab the project suggests right now; the user's own choice wins until the suggestion changes. */
function suggestedTab(status: DecisionStatus): WorkTab {
  const pending = status.run_state === "paused" ? status.pending?.type : null;
  if (pending === "brief_review") return "brief";
  if (pending === "plan_review") return "plan";
  if (status.run_state === "running" && ["implementing", "building"].includes(status.workflow_status ?? "")) return "build";
  if (status.has_build) return "preview";
  return "activity";
}

export function BuilderView({ threadId }: { threadId: string }) {
  const { status, error, refresh, lastUpdate, firstSeenRunning } = useDecision(threadId);
  const [manual, setManual] = useState<{ tab: WorkTab; forSuggested: WorkTab } | null>(null);
  const [mobileSide, setMobileSide] = useState<"chat" | "work">("chat");
  const now = useNow(status?.run_state === "running");
  const [chatWidth, setChatWidth] = useChatWidth(); // null = default widths (400 px, 440 px from lg)
  const chatRef = useRef<HTMLElement>(null);

  const pending = status?.run_state === "paused" ? status.pending : null;
  const round = pending ? `${pending.type}:${pending.payload.round}` : "";
  const moved = status ? `${status.workflow_status}|${status.run_state}|${round}` : "";
  const brief = useFetch(() => getBrief(threadId), `${threadId}|${moved}`, Boolean(status?.has_brief));
  const plan = useFetch(() => getPlan(threadId), `${threadId}|${moved}`, Boolean(status?.has_plan));
  // While the coding agent works, every task attempt adds progress lines: re-fetch the task list with them.
  const implementation = useFetch(() => getImplementation(threadId), `${threadId}|${moved}|${status?.progress.length}`, Boolean(status?.has_build));
  const usage = useFetch(() => getUsage(threadId), `${threadId}|${moved}|${status?.progress.length}`, Boolean(status?.has_build));

  if (!status) {
    if (error && error.status !== 0 && error.status < 500) {
      return (
        <Centered>
          <p className="text-slate-700">This project doesn&apos;t exist (anymore).</p>
          <Link href="/" className="text-sm text-brand hover:underline">
            Start a new project
          </Link>
        </Centered>
      );
    }
    return (
      <Centered>
        {error ? (
          <p className="text-sm text-slate-500">{error.message} Retrying…</p>
        ) : (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner className="size-4 text-brand" /> Opening your project…
          </p>
        )}
      </Centered>
    );
  }

  const suggested = suggestedTab(status);
  const tab = manual && manual.forSuggested === suggested ? manual.tab : suggested;
  function openTab(next: WorkTab) {
    setManual({ tab: next, forSuggested: suggested });
    setMobileSide("work");
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 gap-1 border-b border-slate-200 p-1.5 md:hidden" role="tablist" aria-label="Show">
        <SideButton active={mobileSide === "chat"} onClick={() => setMobileSide("chat")} icon={<MessageSquare className="size-4" aria-hidden />}>
          Chat
        </SideButton>
        <SideButton active={mobileSide === "work"} onClick={() => setMobileSide("work")} icon={<MonitorPlay className="size-4" aria-hidden />}>
          Preview & documents
        </SideButton>
      </div>
      <div className="flex min-h-0 flex-1">
        <section
          ref={chatRef}
          aria-label="Conversation"
          style={chatWidth ? ({ "--chat-w": `${chatWidth}px` } as React.CSSProperties) : undefined}
          className={`${mobileSide === "chat" ? "flex" : "hidden"} min-h-0 w-full flex-col md:flex md:w-[var(--chat-w,400px)] md:shrink-0 lg:w-[var(--chat-w,440px)]`}
        >
          <ChatPane threadId={threadId} status={status} lastUpdate={lastUpdate} refresh={refresh} implementation={implementation.data} usage={usage.data} onOpenTab={openTab} />
        </section>
        <ResizeHandle width={chatWidth} onWidth={setChatWidth} chatLeft={() => chatRef.current?.getBoundingClientRect().left ?? 0} />
        <section aria-label="Preview and documents" className={`${mobileSide === "work" ? "flex" : "hidden"} min-h-0 min-w-0 flex-1 flex-col bg-slate-100 p-2 md:flex`}>
          <WorkPane
            threadId={threadId}
            tab={tab}
            onTab={openTab}
            status={status}
            activity={deriveActivity(status)}
            now={now}
            fallbackStart={firstSeenRunning.current}
            brief={brief.data}
            briefError={brief.error}
            plan={plan.data}
            implementation={implementation.data}
            usage={usage.data}
          />
        </section>
      </div>
    </div>
  );
}

function SideButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`inline-flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}
    >
      {icon}
      {children}
    </button>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">{children}</div>;
}
