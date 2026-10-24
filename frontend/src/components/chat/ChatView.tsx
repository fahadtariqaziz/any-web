"use client";

// One patient chat. Two phases on one page:
// 1. Onboarding: the first message → (agents read it) → short questions, ONE AT A TIME, under a highlighted
//    banner → (agents research, plan and judge; only a "Researching…" chip is shown) → a short summary.
//    The questions come from the graph's clarification pause; answers are collected here and sent together.
// 2. Chat: free conversation with a doctor-like agent that has the onboarding report as context.
//
// Status comes from polling GET /api/decisions/{id}; the transcript from GET /api/chats/{id}.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useDecision } from "@/hooks/useDecision";
import { useFetch } from "@/hooks/useFetch";
import { useNow } from "@/hooks/useNow";
import { useStartChat } from "@/hooks/useStartChat";
import { useStoredList } from "@/hooks/useStoredList";
import { ApiError, getChat, resumeDecision, sendChatMessage } from "@/lib/api/client";
import type { ChatMessage, ClarificationPayload } from "@/lib/api/types";
import { runSeconds, stageLabel } from "@/lib/chatStages";

import { useChatList } from "./ChatListContext";
import { Composer } from "./Composer";
import { AssistantMessage, OnboardingBanner, SummaryMessage, UserBubble } from "./Messages";
import { WorkingChip } from "./WorkingChip";

const POLL_MS = 1000; // onboarding takes ~30 s: poll a bit faster than the admin view so the chip feels live
const SKIPPED = "(skipped by user)"; // what the backend stores for an unanswered question

// Shown when intake decided the first message isn't about health (e.g. "can i do fun").
const OFF_TOPIC_REPLY = `I'm your health support companion, so that's not something I can help with. What I can do is support you in feeling better, with:

- **what doctors recommend** for your condition
- **what other patients** found helpful in their daily life
- **the right diet and exercise**, based on doctors' advice and research

Tell me what's going on with your health, for example "I have type 2 diabetes" or "I get migraines a few times a week".`;

export function ChatView({ threadId }: { threadId: string }) {
  const { status, error: statusError, refresh } = useDecision(threadId, POLL_MS);
  const { refresh: refreshList } = useChatList();
  // A first message that wasn't about health: the next message starts a fresh chat in its place.
  const { start: startOver, sending: startingOver, error: startOverError } = useStartChat({ replace: true });

  // Transcript: re-fetched whenever the onboarding moves on (paused / finished / new answers / report).
  const version = status
    ? `${status.run_state}|${status.workflow_status}|${status.counters.clarification_rounds}|${status.has_report}`
    : "";
  const { data: chat, error: chatError } = useFetch(() => getChat(threadId), `${threadId}|${version}`, Boolean(status));

  // --- onboarding questions: answered one by one, kept in localStorage until all are sent -------------
  const paused: ClarificationPayload | null =
    status?.run_state === "paused" && status.pending?.type === "clarification" ? status.pending.payload : null;
  // After sending a round, the status still says "paused" until the next poll: that round is done for us.
  const [sentRound, setSentRound] = useState<number | null>(null);
  const pending = paused && paused.round !== sentRound ? paused : null;
  const [answers, setAnswers] = useStoredList(paused ? `onboarding:${threadId}:${paused.round}` : null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function answer(text: string) {
    if (!pending || submitting) return;
    const next = [...answers, text];
    if (next.length < pending.questions.length) {
      setAnswers(next);
      return;
    }
    // Last question answered: send them all; blank (skipped) answers are left out.
    setSubmitting(true);
    setActionError(null);
    const body = Object.fromEntries(
      pending.questions.map((q, i) => [q, next[i] ?? ""] as const).filter(([, a]) => a.trim() !== ""),
    );
    try {
      await resumeDecision(threadId, { type: "clarification", answers: body });
      setAnswers(next); // shown until the session's own copy of the answers arrives
      setSentRound(pending.round);
      refresh();
    } catch (e) {
      setAnswers(next.slice(0, -1)); // let them send the last answer again
      setActionError(e instanceof ApiError ? e.message : "Your answers could not be sent. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  // --- a run that stopped half way (server restart): pick it up once, automatically ------------------
  const continued = useRef(false);
  useEffect(() => {
    if (status?.run_state !== "interrupted" || continued.current) return;
    continued.current = true;
    resumeDecision(threadId, { type: "continue" }).then(refresh, () => refresh());
  }, [status?.run_state, threadId, refresh]);

  // Answers typed during onboarding are not needed in localStorage once the summary exists.
  const ready = Boolean(chat?.ready);
  useEffect(() => {
    if (!ready) return;
    Object.keys(localStorage)
      .filter((k) => k.startsWith(`onboarding:${threadId}:`))
      .forEach((k) => localStorage.removeItem(k));
  }, [ready, threadId]);

  // The sidebar shows the condition name once intake found it.
  useEffect(() => {
    if (status?.condition_name) refreshList();
  }, [status?.condition_name, refreshList]);

  // --- chat ---------------------------------------------------------------------------------------
  const [sent, setSent] = useState<ChatMessage[]>([]); // this visit's messages (the server has them too)
  const [streaming, setStreaming] = useState<string | null>(null); // reply arriving right now

  async function sendMessage(text: string) {
    if (streaming !== null) return;
    const at = new Date().toISOString();
    setSent((list) => [...list, { role: "user", content: text, created_at: at }]);
    setStreaming("");
    setActionError(null);
    try {
      const reply = await sendChatMessage(threadId, text, (piece) => setStreaming((s) => (s ?? "") + piece));
      setSent((list) => [...list, { role: "assistant", content: reply, created_at: new Date().toISOString() }]);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Your message could not be sent. Please try again.");
    } finally {
      setStreaming(null);
    }
  }

  // --- keep the newest content in view --------------------------------------------------------------
  const now = useNow(status?.run_state === "running");
  const endRef = useRef<HTMLDivElement>(null);
  const contentSize = `${chat?.clarifications.length}|${answers.length}|${sent.length}|${streaming?.length}|${status?.run_state}|${ready}`;
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [contentSize]);

  // --- not loaded / not found -----------------------------------------------------------------------
  if (!status) {
    if (statusError && statusError.status !== 0 && statusError.status < 500) {
      return (
        <Centered>
          <p className="text-neutral-300">This chat doesn&apos;t exist (anymore).</p>
          <Link href="/" className="text-sm text-teal-300 hover:underline">
            Start a new chat
          </Link>
        </Centered>
      );
    }
    return (
      <Centered>
        {statusError ? <p className="text-sm text-neutral-400">{statusError.message}</p> : <WorkingChip label="Opening your chat" />}
      </Centered>
    );
  }

  const waitingAfterSend = paused !== null && pending === null;
  const running = status.run_state === "running" || status.run_state === "interrupted" || submitting || waitingAfterSend;
  const finished = status.run_state === "finished";
  const failed = finished && !status.has_report;
  const offTopic = failed && status.error?.code === "invalid_input";
  const isAdminSession = chat?.mode === "full";
  const answered = chat?.clarifications ?? [];

  // Composer: answer mode while questions are pending, chat mode once ready, otherwise waiting.
  let composer: React.ReactNode;
  if (pending && !submitting) {
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
            className="mb-0.5 rounded-full px-3 py-2 text-sm text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
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
        placeholder="Tell me about your health, e.g. “I have sugar”"
      />
    );
  } else if (ready) {
    composer = <Composer key="chat" onSend={sendMessage} disabled={streaming !== null} autoFocus placeholder="Ask anything about your health" />;
  } else {
    composer = <Composer key="wait" onSend={() => {}} disabled placeholder={failed ? "This chat ended" : "One moment, I'm reading up on your situation…"} />;
  }

  return (
    <>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 pb-8 pt-4">
          <UserBubble>{chat?.question ?? status.question}</UserBubble>

          {isAdminSession ? (
            <p className="text-sm text-neutral-400">
              This session was started in the admin view.{" "}
              <Link href={`/decisions/${threadId}`} className="text-teal-300 hover:underline">
                Open it there
              </Link>
            </p>
          ) : (
            <>
              {!offTopic && <OnboardingBanner done={ready} />}
              {offTopic && <AssistantMessage text={OFF_TOPIC_REPLY} />}

              {/* Questions already answered (stored in the session) */}
              {answered.map(({ question, answer: a }) => (
                <div key={question} className="space-y-6">
                  <AssistantMessage text={question} />
                  <UserBubble muted={a === SKIPPED}>{a === SKIPPED ? "Skipped" : a}</UserBubble>
                </div>
              ))}

              {/* Questions of the current round: answered locally so far, then the current one */}
              {paused &&
                paused.questions.slice(0, pending ? answers.length + 1 : answers.length).map((q, i) => (
                  <div key={q} className="space-y-6">
                    <div>
                      {i === 0 && answered.length === 0 && (
                        <p className="mb-1 text-sm text-neutral-400">Thanks for telling me. A few quick questions:</p>
                      )}
                      <AssistantMessage text={q} />
                      <p className="mt-1 text-xs text-neutral-500">
                        Question {i + 1} of {paused.questions.length}
                      </p>
                    </div>
                    {i < answers.length && (
                      <UserBubble muted={!answers[i]}>{answers[i] || "Skipped"}</UserBubble>
                    )}
                  </div>
                ))}
              {pending?.error && <p className="text-sm text-amber-300">{pending.error}</p>}

              {running && (
                <WorkingChip
                  label={submitting || waitingAfterSend ? "Understanding your answers" : stageLabel(status)}
                  seconds={submitting || waitingAfterSend ? null : runSeconds(status, now)}
                />
              )}

              {failed && !offTopic && (
                <div className="space-y-2 text-neutral-200">
                  <p>I&apos;m sorry, something went wrong while I was reading up on your situation.</p>
                  {status.error && <p className="text-xs text-neutral-500">{status.error.message}</p>}
                  <Link href="/" className="inline-block text-sm text-teal-300 hover:underline">
                    Start a new chat
                  </Link>
                </div>
              )}

              {chat?.onboarding_summary && <SummaryMessage summary={chat.onboarding_summary} />}

              {[...(chat?.messages ?? []), ...sent].map((m, i) =>
                m.role === "user" ? (
                  <UserBubble key={i}>{m.content}</UserBubble>
                ) : (
                  <AssistantMessage key={i} text={m.content} />
                ),
              )}
              {streaming === "" && <WorkingChip label="Thinking" />}
              {streaming && <AssistantMessage text={streaming} />}
            </>
          )}

          {(actionError || startOverError || chatError) && (
            <p className="text-sm text-red-300">{actionError ?? startOverError ?? chatError?.message}</p>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {!isAdminSession && (
        <div className="shrink-0 px-4 pb-3">
          <div className="mx-auto w-full max-w-3xl space-y-2">
            {composer}
            <p className="text-center text-xs text-neutral-500">Health information and support, not a medical diagnosis.</p>
          </div>
        </div>
      )}
    </>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">{children}</div>;
}
