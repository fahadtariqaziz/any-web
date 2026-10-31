"use client";

// Change-request pause (spec §8 / §9): the generated app runs in a preview; the user asks for a change (a new task
// for the coding agent), a new plan (approved again), or finishes. Everything shown is a fact the backend measured:
// the preview is "ready" only after an HTTP answer, a build step passed only on exit code 0, a task is done only when
// its verify commands passed. The full Lovable layout (chat left, preview right) is M10; this is the admin view.

import { Flag, ListRestart, MonitorPlay, Send } from "lucide-react";
import { useState } from "react";

import { BrowserTestsCard, BuildCard, CodeReviewCard, PreviewCard, TaskList } from "@/components/session/BuildViews";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { BuildResults, ChangeRequestPayload, CodeReview, E2EResults, PreviewInfo } from "@/lib/api/types";

type Action = "change" | "replan" | "finish";

export function ChangeRequestPanel({
  threadId,
  payload,
  onSubmitted,
}: {
  threadId: string;
  payload: ChangeRequestPayload;
  onSubmitted: () => void;
}) {
  const [request, setRequest] = useState("");
  const [sending, setSending] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  const build = "steps" in payload.build ? (payload.build as BuildResults) : null;
  const e2e = payload.e2e && "status" in payload.e2e ? (payload.e2e as E2EResults) : null;
  const review = payload.review && "status" in payload.review ? (payload.review as CodeReview) : null;
  const done = payload.tasks.filter((t) => t.status === "done").length;

  async function send(action: Action) {
    if (sending) return;
    if (action !== "finish" && request.trim().length < 3) {
      setError("Describe the change you want first.");
      return;
    }
    setSending(action);
    setError(null);
    try {
      await resumeDecision(threadId, action === "finish" ? { type: "change_request", action } : { type: "change_request", action, request: request.trim() });
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
              <MonitorPlay className="size-5 text-amber-600" aria-hidden />
              Your app is running
            </span>
          }
          description="Try it in the preview. Ask for a change, ask for a new plan, or finish the session."
          aside={
            <>
              <Badge tone={build?.passed ? "emerald" : "red"} size="md">
                Build {build?.passed ? "passed" : "failed"}
              </Badge>
              <Badge tone="slate" size="md">
                {done}/{payload.tasks.length} tasks · ${payload.cost_usd.toFixed(2)}
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
              <label htmlFor="change-request" className="block text-sm font-medium text-slate-900">
                What should change?
              </label>
              <textarea
                id="change-request"
                rows={3}
                value={request}
                onChange={(e) => setRequest(e.target.value)}
                maxLength={4000}
                placeholder="e.g. Make the buttons bigger and add a dark theme."
                className="w-full resize-y rounded-lg border border-slate-300 p-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
              />
            </>
          ) : (
            <Callout tone="info" title="No more changes in this session">
              <p>The maximum number of change requests was reached. Finish the session, or start a new one.</p>
            </Callout>
          )}
          {error && (
            <Callout tone="danger" title="Could not send your request">
              <p>{error}</p>
            </Callout>
          )}
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-4">
            <Button
              variant="secondary"
              onClick={() => send("finish")}
              loading={sending === "finish"}
              disabled={sending !== null}
              icon={<Flag className="size-4" aria-hidden />}
            >
              Finish
            </Button>
            {payload.replan_allowed && (
              <Button
                variant="secondary"
                onClick={() => send("replan")}
                loading={sending === "replan"}
                disabled={!request.trim() || sending !== null}
                icon={<ListRestart className="size-4" aria-hidden />}
              >
                New plan with this
              </Button>
            )}
            {payload.changes_allowed && (
              <Button
                onClick={() => send("change")}
                loading={sending === "change"}
                disabled={!request.trim() || sending !== null}
                icon={<Send className="size-4" aria-hidden />}
                size="lg"
              >
                Make this change
              </Button>
            )}
          </div>
        </CardBody>
      </Card>

      <PreviewCard threadId={threadId} initial={"state" in payload.preview ? (payload.preview as PreviewInfo) : null} />
      {build && <BuildCard build={build} />}
      {review && review.status !== "skipped" && <CodeReviewCard review={review} learnings={[]} />}
      {e2e && <BrowserTestsCard e2e={e2e} />}
      <TaskList tasks={payload.tasks} />
    </div>
  );
}
