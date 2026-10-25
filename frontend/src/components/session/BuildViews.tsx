"use client";

// The built app as facts the backend measured (M9): the preview (ready only after an HTTP answer), the last build
// check (exit codes) and the task list (done = the task's own verify commands passed). Shared by the change-request
// pause (ChangeRequestPanel) and a finished session (AppView).

import { CheckCircle2, ExternalLink, RotateCw } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ApiError, restartPreview } from "@/lib/api/client";
import type { BuildResults, PreviewInfo, TaskStatus } from "@/lib/api/types";
import type { Tone } from "@/lib/format";

const TASK_TONE: Record<TaskStatus, Tone> = {
  done: "emerald",
  pending: "slate",
  failed: "red",
  blocked: "amber",
  skipped: "slate",
};

export function PreviewCard({ threadId, initial }: { threadId: string; initial: PreviewInfo | null }) {
  const [preview, setPreview] = useState<PreviewInfo | null>(initial);
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [frameKey, setFrameKey] = useState(0);

  async function restart() {
    setRestarting(true);
    setError(null);
    try {
      setPreview(await restartPreview(threadId));
      setFrameKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not restart the preview.");
    } finally {
      setRestarting(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Preview"
        aside={
          <>
            {preview && (
              <Badge tone={preview.state === "ready" ? "emerald" : preview.state === "failed" ? "red" : "slate"} size="md" dot>
                {preview.state}
              </Badge>
            )}
            <Button variant="secondary" size="sm" onClick={restart} loading={restarting} icon={<RotateCw className="size-4" aria-hidden />}>
              {preview?.state === "ready" ? "Restart" : "Start"}
            </Button>
          </>
        }
      />
      <CardBody className="space-y-3">
        {error && (
          <Callout tone="danger" title="Could not start the preview">
            <p>{error}</p>
          </Callout>
        )}
        {preview?.state === "ready" && preview.url ? (
          <>
            <iframe
              key={frameKey}
              src={preview.url}
              title="Preview of the generated app"
              className="h-[520px] w-full rounded-lg border border-slate-200 bg-white"
              sandbox="allow-scripts allow-forms allow-same-origin"
            />
            <a href={preview.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
              Open {preview.url} in a new tab <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </>
        ) : preview?.state === "stopped" ? (
          <Callout tone="info" title="The preview is stopped">
            <p>Previews stop after a while without being looked at. Press Start to run the app again.</p>
          </Callout>
        ) : (
          <Callout tone="danger" title="The app is not running">
            <p>
              Command: <code>{preview?.command ?? "unknown"}</code>
            </p>
            {preview?.last_error && <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs">{preview.last_error}</pre>}
          </Callout>
        )}
      </CardBody>
    </Card>
  );
}

export function BuildCard({ build }: { build: BuildResults }) {
  return (
    <Card>
      <CardHeader
        title={`Build check ${build.round}`}
        description="install → test → build, run by the builder in the project folder"
        aside={
          <Badge tone={build.passed ? "emerald" : "red"} size="md">
            {build.passed ? "passed" : "failed"}
          </Badge>
        }
      />
      <CardBody>
        <ul className="space-y-2">
          {build.steps.map((s) => (
            <li key={`${s.phase}-${s.command}`} className="text-sm">
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone={s.ok ? "emerald" : "red"}>{s.phase}</Badge>
                <code className="text-slate-800">{s.command}</code>
                <span className="text-slate-500">{s.summary}</span>
                {s.skipped_tests ? (
                  <span title="Reported by the test runner: these tests did not run, so a passing exit code does not cover them.">
                    <Badge tone="amber">{s.skipped_tests} skipped</Badge>
                  </span>
                ) : null}
              </span>
              {!s.ok && s.output && <pre className="mt-1 max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs whitespace-pre-wrap">{s.output}</pre>}
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

export function TaskList({ tasks }: { tasks: { id: string; title: string; status: TaskStatus; attempts: number }[] }) {
  return (
    <Card>
      <CardHeader title="Tasks" description="Done means the task's own test commands passed; the agent's report does not count." />
      <CardBody>
        <ul className="divide-y divide-slate-100">
          {tasks.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="text-slate-800">
                <span className="font-mono text-slate-500">{t.id}</span> {t.title}
              </span>
              <span className="flex items-center gap-2">
                {t.attempts > 1 && <span className="text-xs text-slate-500">{t.attempts} attempts</span>}
                <Badge tone={TASK_TONE[t.status]}>
                  {t.status === "done" && <CheckCircle2 className="mr-1 inline size-3" aria-hidden />}
                  {t.status}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
