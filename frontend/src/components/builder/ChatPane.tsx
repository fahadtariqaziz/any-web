"use client";

// The left side of the builder (spec §9): the whole conversation of one project, and the one message box that
// drives it. In order: the first message, the clarification questions (one at a time), the research summary, then
// every reply the user gave the builder (brief / plan reviews, change requests, Ask-mode questions) in time order,
// and at the end what happens now (the agents at work, or a card when the builder needs the user).
//
// The message box changes with the project: an answer to the current question; a change to the brief or the plan
// while it is under review; a change (or a bigger change through a new plan) once the app runs, also after Finish (it reopens the project:
// {type: "reopen"}); and, from the research summary on, "Ask about app"
// (questions about the project that change nothing, answered by the project assistant, backend chat.py).
//
// Status comes from the parent (polled GET /api/decisions/{id}); the conversation from GET /api/chats/{id}.

import {
  CheckCircle2,
  CircleSlash,
  FileText,
  Flag,
  Hammer,
  ListChecks,
  Loader2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { useFetch } from "@/hooks/useFetch";
import { useNow } from "@/hooks/useNow";
import { useStoredList } from "@/hooks/useStoredList";
import {
  ApiError,
  getChat,
  resumeDecision,
  sendChatMessage,
} from "@/lib/api/client";
import type {
  ChangeTurn,
  ChatMessage,
  ChatTranscript,
  ClarificationPayload,
  DecisionStatus,
  ImplementationResponse,
  ResumeRequest,
  ReviewTarget,
  ReviewTurn,
  UsageResponse,
} from "@/lib/api/types";
import { latestDetail, runSeconds, stageLabel } from "@/lib/chatStages";
import { WORKFLOW_STATUS_LABEL } from "@/lib/format";

import { projectTotal } from "@/components/session/CostCard";
import {
  AppRunningCard,
  BriefReviewCard,
  BuildProgressCard,
  PlanReviewCard,
} from "./ActionCards";
import { Composer, type ComposerMode } from "./Composer";
import {
  AssistantMessage,
  AssistantNote,
  OnboardingBanner,
  SummaryMessage,
  UserBubble,
} from "./Messages";
import { projectTitle, useProjectList } from "./ProjectListContext";
import { StageChips } from "./StageChips";
import { useStartProject } from "./useStartProject";
import { WorkingChip } from "./WorkingChip";
import type { WorkTab } from "./WorkPane";

const SKIPPED = "(skipped by user)"; // what the backend stores for an unanswered question

// Shown when intake decided the first message isn't an app or website idea (e.g. "can i do fun").
const OFF_TOPIC_REPLY = `I build apps and websites from ideas, so that's not something I can help with. Tell me what you want to build and I will:

- **ask a few questions** to understand the users, the goal and the must-have features
- **research** existing apps and what their users say, relevant papers, and what is technically feasible
- **write a brief and a plan** for your approval, then **build the app** and show it running here

Try something like "A simple calculator web app" or "A website for my bakery with online pre-orders".`;

const TARGET_LABEL: Record<string, string> = {
  auto: "the agents decide",
  wording: "wording",
  proposal: "a different solution",
  research: "more research",
  requirements: "requirements",
};

const CHANGE_HINT =
  "One task for the coding agent on the current plan, then the build is checked and the preview restarts.";
const REPLAN_HINT =
  "For a big change (new features, screens, another architecture): your brief is updated first, then a plan with only the new work; you approve both, then it is built.";

type Mode = "brief" | "plan" | "change" | "replan" | "ask";
type Optimistic = {
  tag: string;
  text: string;
  seen: (t: ChatTranscript) => boolean;
};
type Item = { at: number; key: string; node: React.ReactNode };

export function ChatPane({
  threadId,
  status,
  lastUpdate,
  refresh,
  implementation,
  usage,
  onOpenTab,
}: {
  threadId: string;
  status: DecisionStatus;
  lastUpdate: number | null; // client time of the last status poll
  refresh: () => void;
  implementation: ImplementationResponse | null;
  usage: UsageResponse | null;
  onOpenTab: (tab: WorkTab) => void;
}) {
  const { refresh: refreshProjects } = useProjectList();
  const {
    start: startOver,
    sending: startingOver,
    error: startOverError,
  } = useStartProject({ replace: true });
  const pending = status.run_state === "paused" ? status.pending : null;
  const pauseKey = pending ? `${pending.type}:${pending.payload.round}` : "";

  // --- the conversation (re-fetched whenever the project moves on, and after every reply) -------------------
  const [bump, setBump] = useState(0);
  const version = `${status.run_state}|${status.workflow_status}|${status.current_node}|${status.counters.clarification_rounds}|${status.has_report}|${pauseKey}|${bump}`;
  const { data: chat, error: chatError } = useFetch(
    () => getChat(threadId),
    `${threadId}|${version}`,
  );
  const ready = Boolean(chat?.ready);

  // --- clarification questions: answered one by one, kept in localStorage until all are sent ----------------
  const paused: ClarificationPayload | null =
    pending?.type === "clarification" ? pending.payload : null;
  const [sentRound, setSentRound] = useState<number | null>(null); // the status says "paused" until the next poll
  const question = paused && paused.round !== sentRound ? paused : null;
  const [answers, setAnswers] = useStoredList(
    paused ? `onboarding:${threadId}:${paused.round}` : null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function answer(text: string) {
    if (!question || submitting) return;
    const next = [...answers, text];
    if (next.length < question.questions.length) {
      setAnswers(next);
      return;
    }
    // Last question answered: send them all; blank (skipped) answers are left out.
    setSubmitting(true);
    setActionError(null);
    const body = Object.fromEntries(
      question.questions
        .map((q, i) => [q, next[i] ?? ""] as const)
        .filter(([, a]) => a.trim() !== ""),
    );
    try {
      await resumeDecision(threadId, { type: "clarification", answers: body });
      setAnswers(next); // shown until the session's own copy of the answers arrives
      setSentRound(question.round);
      refresh();
    } catch (e) {
      setAnswers(next.slice(0, -1)); // let them send the last answer again
      setActionError(
        e instanceof ApiError
          ? e.message
          : "Your answers could not be sent. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // Answers typed during onboarding are not needed in localStorage once the summary exists.
  useEffect(() => {
    if (!ready) return;
    Object.keys(localStorage)
      .filter((k) => k.startsWith(`onboarding:${threadId}:`))
      .forEach((k) => localStorage.removeItem(k));
  }, [ready, threadId]);

  // A run that stopped half way (server restart): pick it up once, automatically.
  const continued = useRef(false);
  useEffect(() => {
    if (status.run_state !== "interrupted" || continued.current) return;
    continued.current = true;
    resumeDecision(threadId, { type: "continue" }).then(refresh, () =>
      refresh(),
    );
  }, [status.run_state, threadId, refresh]);

  // The projects drawer shows the project name once intake found it.
  useEffect(() => {
    if (status.project_name) refreshProjects();
  }, [status.project_name, refreshProjects]);

  // --- replies to the pauses: approve buttons in the cards, changes from the message box ----------------------
  const [sending, setSending] = useState<string | null>(null); // which action is on its way
  const [sentAt, setSentAt] = useState<number | null>(null); // when the last reply went out
  const [optimistic, setOptimistic] = useState<Optimistic | null>(null);
  const [target, setTarget] = useState<ReviewTarget>("auto");

  async function reply(
    body: ResumeRequest,
    action: string,
    shown: Optimistic | null,
  ): Promise<boolean> {
    if (sending) return false;
    setSending(action);
    setActionError(null);
    try {
      await resumeDecision(threadId, body);
      setSentAt(Date.now());
      setOptimistic(shown);
      setBump((n) => n + 1);
      refresh();
      return true;
    } catch (e) {
      setActionError(
        e instanceof ApiError
          ? e.message
          : "Your reply could not be sent. Please try again.",
      );
      return false;
    } finally {
      setSending(null);
    }
  }
  // We replied and no status newer than the reply has arrived yet (the next poll shows running, or a re-ask with error).
  const answered = sentAt !== null && (lastUpdate ?? 0) < sentAt;

  // --- Ask mode: a streamed answer from the project assistant -------------------------------------------------
  const [asked, setAsked] = useState<ChatMessage[]>([]); // this visit's messages until the transcript has them
  const [streaming, setStreaming] = useState<string | null>(null);

  async function ask(text: string): Promise<boolean> {
    if (streaming !== null) return false;
    setAsked((list) => [
      ...list,
      { role: "user", content: text, created_at: new Date().toISOString() },
    ]);
    setStreaming("");
    setActionError(null);
    try {
      const answerText = await sendChatMessage(threadId, text, (piece) =>
        setStreaming((s) => (s ?? "") + piece),
      );
      setAsked((list) => [
        ...list,
        {
          role: "assistant",
          content: answerText,
          created_at: new Date().toISOString(),
        },
      ]);
      setBump((n) => n + 1);
      return true;
    } catch (e) {
      setAsked((list) => list.slice(0, -1));
      setActionError(
        e instanceof ApiError
          ? e.message
          : "Your question could not be sent. Please try again.",
      );
      return false;
    } finally {
      setStreaming(null);
    }
  }

  // --- the message box: what it does depends on the pause ------------------------------------------------------
  const modes: ComposerMode<Mode>[] = [];
  if (!answered && pending?.type === "brief_review")
    modes.push({
      key: "brief",
      label: "Change the brief",
      placeholder: "What should change or be added in the brief?",
    });
  if (
    !answered &&
    pending?.type === "plan_review" &&
    pending.payload.changes_allowed
  )
    modes.push({
      key: "plan",
      label: "Change the plan",
      placeholder: "What should change in the plan?",
    });
  if (
    !answered &&
    pending?.type === "change_request" &&
    pending.payload.changes_allowed
  ) {
    modes.push({
      key: "change",
      label: "Request some change in app",
      placeholder: "Describe the change, e.g. make the buttons bigger",
      hint: CHANGE_HINT,
    });
    if (pending.payload.replan_allowed)
      modes.push({
        key: "replan",
        label: "Plan a bigger change",
        placeholder:
          "Describe the bigger change; the brief, then a plan come back for your approval",
        hint: REPLAN_HINT,
      });
  }
  if (ready)
    modes.push({
      key: "ask",
      label: "Ask about app",
      placeholder: "Ask about the research, the brief, the plan or the build",
      hint: "A question about the project. Changes nothing.",
    });
  // After Finish, Ask stays the default (first): a change reopens the project and costs a coding-agent run.
  const finishedOpen =
    status.run_state === "finished" && !answered ? status.reopen_actions : [];
  if (finishedOpen.includes("change"))
    modes.push({
      key: "change",
      label: "Request some change in app",
      placeholder: "Describe a change; it reopens the project",
      hint: CHANGE_HINT,
    });
  if (finishedOpen.includes("replan"))
    modes.push({
      key: "replan",
      label: "Plan a bigger change",
      placeholder:
        "Describe the bigger change; the brief, then a plan come back for your approval",
      hint: REPLAN_HINT,
    });
  const [modeChoice, setModeChoice] = useState<{
    pause: string;
    mode: Mode;
  } | null>(null);
  const mode =
    modeChoice &&
    modeChoice.pause === pauseKey &&
    modes.some((m) => m.key === modeChoice.mode)
      ? modeChoice.mode
      : modes[0]?.key;

  function send(text: string): Promise<boolean> | boolean {
    switch (mode) {
      case "ask":
        return ask(text);
      case "brief": {
        const t =
          pending?.type === "brief_review" &&
          pending.payload.wording_only &&
          target !== "auto"
            ? "wording"
            : target;
        return reply(
          {
            type: "brief_review",
            action: "request_changes",
            feedback: text,
            target: t,
          },
          "brief",
          {
            tag: "Change to the brief",
            text,
            seen: (c) =>
              c.reviews.some((r) => r.kind === "brief" && r.feedback === text),
          },
        );
      }
      case "plan":
        return reply(
          { type: "plan_review", action: "request_changes", feedback: text },
          "plan",
          {
            tag: "Change to the plan",
            text,
            seen: (c) =>
              c.reviews.some((r) => r.kind === "plan" && r.feedback === text),
          },
        );
      case "change":
      case "replan":
        return reply(
          status.run_state === "finished"
            ? { type: "reopen", action: mode, request: text }
            : { type: "change_request", action: mode, request: text },
          mode,
          {
            tag:
              mode === "change" ? "Change request" : "Bigger change (new plan)",
            text,
            seen: (c) => c.changes.some((x) => x.request === text),
          },
        );
      default:
        return false;
    }
  }

  // --- keep the newest content in view ---------------------------------------------------------------------------
  const running =
    status.run_state === "running" ||
    status.run_state === "interrupted" ||
    submitting ||
    answered ||
    (paused !== null && question === null);
  const now = useNow(running);
  const endRef = useRef<HTMLDivElement>(null);
  const contentSize = `${chat?.clarifications.length}|${chat?.reviews.length}|${chat?.changes.length}|${chat?.messages.length}|${answers.length}|${asked.length}|${streaming?.length}|${pauseKey}|${status.run_state}|${ready}`;
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [contentSize]);

  // --- the timeline after the summary: reviews, change requests and Ask messages in time order ----------------
  const timeline = useMemo(() => {
    if (!chat) return [];
    const serverMessages = chat.messages;
    const local = asked.filter(
      (m) =>
        !serverMessages.some(
          (s) => s.role === m.role && s.content.trim() === m.content.trim(),
        ),
    );
    const items: Item[] = [
      ...chat.reviews.map((r, i) => ({
        at: Date.parse(r.at),
        key: `r${i}`,
        node: <ReviewItem turn={r} />,
      })),
      ...chat.changes.map((c, i) => ({
        at: Date.parse(c.at),
        key: `c${i}`,
        node: <ChangeItem turn={c} />,
      })),
      ...[...serverMessages, ...local].map((m, i) => ({
        at: Date.parse(m.created_at),
        key: `m${i}`,
        node:
          m.role === "user" ? (
            <UserBubble tag="Ask about app">{m.content}</UserBubble>
          ) : (
            <AssistantMessage text={m.content} />
          ),
      })),
    ];
    return items.sort((a, b) => a.at - b.at); // stable: equal times keep their order
  }, [chat, asked]);

  const finished = status.run_state === "finished";
  const failed = finished && status.workflow_status === "failed";
  const offTopic = failed && status.error?.code === "invalid_input";
  const showOptimistic = optimistic && chat && !optimistic.seen(chat);
  const buildingNow =
    running &&
    implementation &&
    ["implementing", "building"].includes(status.workflow_status ?? "");

  // --- the live area at the end ------------------------------------------------------------------------------------
  let live: React.ReactNode = null;
  if (running) {
    live = (
      <div className="space-y-3">
        {buildingNow && (
          <BuildProgressCard
            implementation={implementation}
            onOpen={() => onOpenTab("build")}
          />
        )}
        <WorkingChip
          label={
            submitting || answered ? "Reading your reply" : stageLabel(status)
          }
          seconds={submitting || answered ? null : runSeconds(status, now)}
          detail={submitting || answered ? null : latestDetail(status)}
        />
      </div>
    );
  } else if (pending?.type === "brief_review") {
    live = (
      <BriefReviewCard
        payload={pending.payload}
        target={target}
        onTarget={setTarget}
        approving={sending === "approve_brief"}
        onOpen={() => onOpenTab("brief")}
        onApprove={() =>
          reply({ type: "brief_review", action: "approve" }, "approve_brief", {
            tag: "",
            text: "",
            seen: (c) =>
              c.reviews.some(
                (r) => r.kind === "brief" && r.action === "approve",
              ),
          })
        }
      />
    );
  } else if (pending?.type === "plan_review") {
    live = (
      <PlanReviewCard
        payload={pending.payload}
        approving={sending === "approve_plan"}
        onOpen={() => onOpenTab("plan")}
        onApprove={() =>
          reply({ type: "plan_review", action: "approve" }, "approve_plan", {
            tag: "",
            text: "",
            seen: (c) =>
              c.reviews.some(
                (r) => r.kind === "plan" && r.action === "approve",
              ),
          })
        }
      />
    );
  } else if (pending?.type === "change_request") {
    live = (
      <AppRunningCard
        payload={pending.payload}
        totalUsd={usage ? projectTotal(usage) : null}
        finishing={sending === "finish"}
        onOpenPreview={() => onOpenTab("preview")}
        onOpenBuild={() => onOpenTab("build")}
        onFinish={() =>
          reply({ type: "change_request", action: "finish" }, "finish", {
            tag: "",
            text: "",
            seen: (c) => c.changes.some((x) => x.action === "finish"),
          })
        }
      />
    );
  } else if (finished && !failed) {
    live = (
      <AssistantNote
        icon={<CheckCircle2 className="size-4" aria-hidden />}
        tone={status.workflow_status === "completed" ? "emerald" : "amber"}
      >
        <p className="font-medium">
          {WORKFLOW_STATUS_LABEL[status.workflow_status ?? ""] ?? "Finished"}.
          {status.workflow_status === "completed_with_uncertainty" && (
            <span className="font-normal text-slate-600">
              {" "}
              Some research claims, brief checks, tasks or the last build were
              not confirmed (Details).
            </span>
          )}
        </p>
        {status.has_build && (
          <p className="text-slate-600">
            The app stays in the preview (it stops after 30 minutes without
            being looked at; you can start it again there).{" "}
            {status.reopen_actions.includes("change")
              ? 'Want more? Type a change below in "Request some change in app": the project reopens, the coding agent makes it and the preview restarts.'
              : "You can still ask questions below."}
          </p>
        )}
      </AssistantNote>
    );
  } else if (failed && !offTopic) {
    live = (
      <div className="space-y-2 text-sm text-slate-800">
        <p>I&apos;m sorry, something went wrong in this project.</p>
        {status.error && (
          <p className="text-xs text-slate-500">{status.error.message}</p>
        )}
        <Link href="/" className="inline-block text-brand hover:underline">
          Start a new project
        </Link>
      </div>
    );
  }

  // --- the message box ----------------------------------------------------------------------------------------------
  let composer: React.ReactNode;
  if (question && !submitting) {
    composer = (
      <Composer
        key={`answer-${answers.length}`}
        onSend={answer}
        autoFocus
        placeholder="Type your answer…"
        extra={
          <button
            type="button"
            onClick={() => answer("")}
            className="mb-0.5 rounded-full px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          >
            Skip
          </button>
        }
      />
    );
  } else if (offTopic) {
    composer = (
      <Composer
        key="start-over"
        onSend={startOver}
        disabled={startingOver}
        autoFocus
        placeholder="Describe the app or website you want to build"
      />
    );
  } else if (mode) {
    composer = (
      <Composer
        key="main"
        modes={modes}
        mode={mode}
        onModeChange={(m) => setModeChoice({ pause: pauseKey, mode: m })}
        onSend={send}
        disabled={sending !== null || streaming !== null}
      />
    );
  } else {
    composer = (
      <Composer
        key="wait"
        onSend={() => false}
        disabled
        placeholder={
          failed
            ? "This project ended"
            : "One moment, I'm working on your idea…"
        }
      />
    );
  }

  const clarifications = chat?.clarifications ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-2 border-b border-slate-200 px-4 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <p
            className="truncate text-sm font-semibold text-slate-900"
            title={status.question ?? ""}
          >
            {projectTitle(status.project_name, status.question)}
          </p>
          <Link
            href={`/decisions/${threadId}`}
            className="shrink-0 text-xs text-slate-500 hover:text-slate-900 hover:underline"
          >
            Details
          </Link>
        </div>
        <StageChips status={status} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-5 px-4 pb-6 pt-4">
          <UserBubble>{chat?.question ?? status.question}</UserBubble>
          {!offTopic && <OnboardingBanner done={ready} />}
          {offTopic && <AssistantMessage text={OFF_TOPIC_REPLY} />}

          {/* Questions already answered (stored in the session) */}
          {clarifications.map(({ question: q, answer: a }) => (
            <div key={q} className="space-y-3">
              <AssistantMessage text={q} />
              <UserBubble muted={a === SKIPPED}>
                {a === SKIPPED ? "Skipped" : a}
              </UserBubble>
            </div>
          ))}

          {/* Questions of the current round: answered locally so far, then the current one */}
          {paused &&
            paused.questions
              .slice(0, question ? answers.length + 1 : answers.length)
              .map((q, i) => (
                <div key={q} className="space-y-3">
                  <div>
                    {i === 0 && clarifications.length === 0 && (
                      <p className="mb-1 text-sm text-slate-500">
                        Thanks for telling me. A few quick questions:
                      </p>
                    )}
                    <AssistantMessage text={q} />
                    <p className="mt-1 text-xs text-slate-400">
                      Question {i + 1} of {paused.questions.length}
                    </p>
                  </div>
                  {i < answers.length && (
                    <UserBubble muted={!answers[i]}>
                      {answers[i] || "Skipped"}
                    </UserBubble>
                  )}
                </div>
              ))}
          {question?.error && (
            <p className="text-sm text-amber-700">{question.error}</p>
          )}

          {chat?.onboarding_summary && (
            <SummaryMessage summary={chat.onboarding_summary} />
          )}

          {timeline.map((item) => (
            <div key={item.key}>{item.node}</div>
          ))}
          {showOptimistic && optimistic.text && (
            <UserBubble tag={optimistic.tag}>{optimistic.text}</UserBubble>
          )}
          {streaming === "" && <WorkingChip label="Thinking" />}
          {streaming && <AssistantMessage text={streaming} />}

          {live}

          {(actionError || startOverError || chatError) && (
            <p className="text-sm text-red-600">
              {actionError ?? startOverError ?? chatError?.message}
            </p>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="shrink-0 space-y-1.5 px-3 pb-3 pt-1">
        {composer}
        <p className="text-center text-[11px] text-slate-400">
          Nothing is planned or built before you approve it. Build results come
          from real commands.
        </p>
      </div>
    </div>
  );
}

function ReviewItem({ turn }: { turn: ReviewTurn }) {
  const what = turn.kind === "brief" ? "brief" : "plan";
  if (turn.action === "approve") {
    return (
      <AssistantNote
        icon={<CheckCircle2 className="size-4" aria-hidden />}
        tone="emerald"
      >
        You approved the {what}
        {turn.kind === "plan"
          ? " (version " + turn.round + "). The build starts."
          : ` (review round ${turn.round}). Planning starts.`}
      </AssistantNote>
    );
  }
  return (
    <div className="space-y-2">
      <AssistantNote
        icon={
          turn.kind === "brief" ? (
            <FileText className="size-4" aria-hidden />
          ) : (
            <ListChecks className="size-4" aria-hidden />
          )
        }
      >
        {turn.kind === "brief"
          ? `Brief ready for review (round ${turn.round})`
          : `Plan version ${turn.round} ready for review`}
      </AssistantNote>
      <UserBubble
        tag={`Change to the ${what}${turn.target ? ` · ${TARGET_LABEL[turn.target] ?? turn.target}` : ""}`}
      >
        {turn.feedback}
      </UserBubble>
    </div>
  );
}

function ChangeItem({ turn }: { turn: ChangeTurn }) {
  if (turn.action === "finish") {
    return (
      <AssistantNote
        icon={<Flag className="size-4" aria-hidden />}
        tone="emerald"
      >
        You finished the project.
      </AssistantNote>
    );
  }
  const outcome =
    turn.action === "replan" ? (
      <AssistantNote icon={<ListChecks className="size-4" aria-hidden />}>
        Your brief is updated with this first; after you approve it, a plan with
        only the new work comes for your approval.
      </AssistantNote>
    ) : turn.task_status === "done" ? (
      <AssistantNote
        icon={<CheckCircle2 className="size-4" aria-hidden />}
        tone="emerald"
      >
        {turn.task_id} done: the change passed its tests; the build is checked
        again and the preview restarted.
      </AssistantNote>
    ) : turn.task_status === "failed" ? (
      <AssistantNote
        icon={<XCircle className="size-4" aria-hidden />}
        tone="red"
      >
        {turn.task_id} failed: its tests did not pass. See the Build tab, or
        describe the problem in a new change request.
      </AssistantNote>
    ) : turn.task_status === "blocked" || turn.task_status === "skipped" ? (
      <AssistantNote
        icon={<CircleSlash className="size-4" aria-hidden />}
        tone="amber"
      >
        {turn.task_id} {turn.task_status}.
      </AssistantNote>
    ) : turn.task_id ? (
      <AssistantNote
        icon={<Loader2 className="size-4 animate-spin" aria-hidden />}
      >
        <span className="inline-flex items-center gap-1">
          <Hammer className="size-3.5" aria-hidden /> Working on it (
          {turn.task_id})…
        </span>
      </AssistantNote>
    ) : null;
  return (
    <div className="space-y-2">
      <UserBubble
        tag={`${turn.action === "change" ? `Change request ${turn.round}` : "Bigger change (new plan)"}${
          turn.cost_usd ? ` · cost $${turn.cost_usd.toFixed(2)}` : ""
        }`}
      >
        {turn.request}
      </UserBubble>
      {outcome}
    </div>
  );
}
