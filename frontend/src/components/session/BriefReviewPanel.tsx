"use client";

// Brief review pause (spec §6): the validated brief, an explicit Approve button, and a text field for changes or
// additions. A change request goes back to the step that can make it (auto = the backend decides), the brief is
// revised and revalidated, and comes back here. Nothing is planned or built before an explicit approval.

import { CheckCircle2, FileText, PencilLine } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Markdown } from "@/components/ui/Markdown";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { BriefReviewPayload, ReviewTarget } from "@/lib/api/types";

const TARGETS: { value: ReviewTarget; label: string; hint: string }[] = [
  { value: "auto", label: "Let the agents decide", hint: "The request is read and sent to the right step." },
  { value: "wording", label: "Wording only", hint: "The content is right; change how it is written. Fastest." },
  { value: "proposal", label: "A different solution", hint: "Another approach, architecture, technology or feature set." },
  { value: "research", label: "More or better research", hint: "Facts or sources are missing or wrong." },
  { value: "requirements", label: "You misunderstood me", hint: "Audience, purpose, features or constraints are wrong. Redoes everything." },
];

export function BriefReviewPanel({
  threadId,
  payload,
  onSubmitted,
}: {
  threadId: string;
  payload: BriefReviewPayload;
  onSubmitted: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [target, setTarget] = useState<ReviewTarget>("auto");
  const [sending, setSending] = useState<"approve" | "request_changes" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const summary = payload.validation_summary;
  const targets = payload.wording_only ? TARGETS.filter((t) => t.value === "auto" || t.value === "wording") : TARGETS;

  async function send(action: "approve" | "request_changes") {
    if (sending) return;
    if (action === "request_changes" && feedback.trim().length < 3) {
      setError("Describe the change you want first.");
      return;
    }
    setSending(action);
    setError(null);
    try {
      await resumeDecision(
        threadId,
        action === "approve"
          ? { type: "brief_review", action }
          : { type: "brief_review", action, feedback: feedback.trim(), target: payload.wording_only && target !== "auto" ? "wording" : target },
      );
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
              <FileText className="size-5 text-amber-600" aria-hidden />
              Does this describe your problem and the solution you want?
            </span>
          }
          description="Read the brief below. Approve it to continue to planning, or say what to change or add. A revised brief is checked again before you see it."
          aside={
            <>
              <Badge tone="amber" size="md">
                Review round {payload.round}
              </Badge>
              <Badge tone={summary.open_issues.length ? "amber" : "emerald"} size="md">
                {summary.checks_passed} of {summary.checks_total} checks passed
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
          {payload.wording_only && (
            <Callout tone="info" title="Only wording changes now">
              <p>The brief was revised {payload.max_rounds} times. You can still approve it or change its wording.</p>
            </Callout>
          )}
          <label htmlFor="brief-feedback" className="block text-sm font-medium text-slate-900">
            What should change or be added? <span className="font-normal text-slate-500">(leave empty to approve)</span>
          </label>
          <textarea
            id="brief-feedback"
            rows={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            maxLength={4000}
            placeholder="e.g. It must work offline on phones, and the name should be StudyStreak."
            className="w-full resize-y rounded-lg border border-slate-300 p-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
          />
          {feedback.trim() && (
            <fieldset className="space-y-1.5">
              <legend className="text-sm font-medium text-slate-900">What kind of change is it?</legend>
              {targets.map((t) => (
                <label key={t.value} className="flex cursor-pointer items-start gap-2 text-sm">
                  <input type="radio" name="target" value={t.value} checked={target === t.value} onChange={() => setTarget(t.value)} className="mt-1" />
                  <span>
                    <span className="font-medium text-slate-800">{t.label}</span>
                    <span className="text-slate-500"> · {t.hint}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          {error && (
            <Callout tone="danger" title="Could not send your review">
              <p>{error}</p>
            </Callout>
          )}
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-4">
            <Button
              variant="secondary"
              onClick={() => send("request_changes")}
              loading={sending === "request_changes"}
              disabled={!feedback.trim() || sending !== null}
              icon={<PencilLine className="size-4" aria-hidden />}
            >
              Request changes
            </Button>
            <Button
              onClick={() => send("approve")}
              loading={sending === "approve"}
              disabled={!!feedback.trim() || sending !== null}
              icon={<CheckCircle2 className="size-4" aria-hidden />}
              size="lg"
            >
              Approve the brief
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          {summary.open_issues.length > 0 && (
            <Callout tone="warning" title="The validator left open issues">
              <p>They are listed at the end of the brief. You can approve anyway or ask for changes.</p>
            </Callout>
          )}
          <Markdown>{payload.brief_markdown}</Markdown>
        </CardBody>
      </Card>
    </div>
  );
}
