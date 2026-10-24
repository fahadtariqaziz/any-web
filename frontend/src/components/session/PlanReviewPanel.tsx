"use client";

// Plan review pause (spec §7): the implementation plan written from the approved brief, an explicit Approve button
// and a text field for changes. Brief approval and plan approval are separate checkpoints (spec §12): nothing is
// built before this approval either.

import { CheckCircle2, ListChecks, PencilLine } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Markdown } from "@/components/ui/Markdown";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { PlanReviewPayload } from "@/lib/api/types";

export function PlanReviewPanel({
  threadId,
  payload,
  onSubmitted,
}: {
  threadId: string;
  payload: PlanReviewPayload;
  onSubmitted: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [sending, setSending] = useState<"approve" | "request_changes" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(action: "approve" | "request_changes") {
    if (sending) return;
    if (action === "request_changes" && feedback.trim().length < 3) {
      setError("Describe the change you want first.");
      return;
    }
    setSending(action);
    setError(null);
    try {
      await resumeDecision(threadId, action === "approve" ? { type: "plan_review", action } : { type: "plan_review", action, feedback: feedback.trim() });
      onSubmitted();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setSending(null);
    }
  }

  return (
    <div className="animate-fade-up space-y-4">
      <Card className="border-amber-200">
        <CardHeader
          eyebrow="Your turn"
          title={
            <span className="flex items-center gap-2">
              <ListChecks className="size-5 text-amber-600" aria-hidden />
              Approve the implementation plan?
            </span>
          }
          description="This is how the coding agent will build your app, task by task. Approve it to continue, or say what to change. Nothing is built before you approve."
          aside={
            <>
              <Badge tone="amber" size="md">
                Plan version {payload.round}
              </Badge>
              <Badge tone="slate" size="md">
                {payload.task_count} tasks · {payload.model}
              </Badge>
            </>
          }
        />
        <CardBody className="space-y-4">
          {payload.error && (
            <Callout tone="warning" title="Your previous reply was not accepted">
              <p>{payload.error}</p>
            </Callout>
          )}
          {payload.changes_allowed ? (
            <>
              <label htmlFor="plan-feedback" className="block text-sm font-medium text-slate-900">
                What should change? <span className="font-normal text-slate-500">(leave empty to approve)</span>
              </label>
              <textarea
                id="plan-feedback"
                rows={3}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                maxLength={4000}
                placeholder="e.g. Use plain JavaScript instead of Vite, and add a task for a dark theme."
                className="w-full resize-y rounded-lg border border-slate-300 p-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
              />
            </>
          ) : (
            <Callout tone="info" title="Changes are no longer possible">
              <p>The plan was revised {payload.max_revisions} times. Approve it to continue, or start a new session.</p>
            </Callout>
          )}
          {error && (
            <Callout tone="danger" title="Could not send your review">
              <p>{error}</p>
            </Callout>
          )}
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-4">
            {payload.changes_allowed && (
              <Button
                variant="secondary"
                onClick={() => send("request_changes")}
                loading={sending === "request_changes"}
                disabled={!feedback.trim() || sending !== null}
                icon={<PencilLine className="size-4" aria-hidden />}
              >
                Request changes
              </Button>
            )}
            <Button
              onClick={() => send("approve")}
              loading={sending === "approve"}
              disabled={!!feedback.trim() || sending !== null}
              icon={<CheckCircle2 className="size-4" aria-hidden />}
              size="lg"
            >
              Approve the plan
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <Markdown>{payload.plan_markdown}</Markdown>
        </CardBody>
      </Card>
    </div>
  );
}
