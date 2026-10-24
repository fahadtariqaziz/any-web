"use client";

// Clarification pause: the questions the agent asked, one answer box each. Leaving a box empty skips
// the question (the agents then state an assumption). Keys sent to the backend are the exact question texts.

import { MessageCircleQuestion, Send } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { ClarificationPayload } from "@/lib/api/types";

const MAX_ROUNDS = 2; // config.max_clarification_rounds

export function ClarificationForm({
  threadId,
  payload,
  onSubmitted,
}: {
  threadId: string;
  payload: ClarificationPayload;
  onSubmitted: () => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answered = payload.questions.filter((q) => (answers[q] ?? "").trim()).length;

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    const filled: Record<string, string> = {};
    for (const q of payload.questions) {
      const a = (answers[q] ?? "").trim();
      if (a) filled[q] = a;
    }
    try {
      await resumeDecision(threadId, { type: "clarification", answers: filled });
      onSubmitted();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setSubmitting(false);
    }
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  }

  return (
    <Card className="animate-fade-up border-amber-200">
      <CardHeader
        eyebrow="Your turn"
        title={
          <span className="flex items-center gap-2">
            <MessageCircleQuestion className="size-5 text-amber-600" aria-hidden />
            A few questions to tailor the research
          </span>
        }
        description="Answer what you can in your own words. Leave a question empty to skip it; the agents will state what they assumed."
        aside={
          <Badge tone="amber" size="md">
            Round {payload.round} of {MAX_ROUNDS}
          </Badge>
        }
      />
      <CardBody className="space-y-5">
        {payload.error && (
          <Callout tone="warning" title="Your previous reply was not accepted">
            <p>{payload.error}</p>
          </Callout>
        )}
        <ol className="space-y-4">
          {payload.questions.map((q, i) => (
            <li key={q} className="space-y-2">
              <label htmlFor={`q-${i}`} className="flex gap-2 text-sm font-medium text-slate-900">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-semibold text-amber-800">{i + 1}</span>
                <span className="pt-0.5">{q}</span>
              </label>
              <textarea
                id={`q-${i}`}
                rows={2}
                value={answers[q] ?? ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q]: e.target.value }))}
                onKeyDown={onKeyDown}
                maxLength={2000}
                placeholder="Your answer (optional)"
                className="ml-8 w-[calc(100%-2rem)] resize-y rounded-lg border border-slate-300 p-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
              />
            </li>
          ))}
        </ol>
        {error && (
          <Callout tone="danger" title="Could not send your answers">
            <p>{error}</p>
          </Callout>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
          <p className="text-sm text-slate-600">
            {answered} of {payload.questions.length} answered
            {answered === 0 && <span className="text-slate-500"> · sending with no answers is allowed; the agents will assume more</span>}
          </p>
          <Button onClick={submit} loading={submitting} icon={<Send className="size-4" aria-hidden />} size="lg">
            {submitting ? "Sending…" : "Send answers"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
