"use client";

// A finished session's built app (M9): the preview (still running until the idle stop, or startable again), the last
// build check and every task with its verified status. The same cards as the change-request pause (BuildViews).

import { Boxes } from "lucide-react";

import { BuildCard, PreviewCard, TaskList } from "@/components/session/BuildViews";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import type { ImplementationResponse, PreviewResponse } from "@/lib/api/types";

export function AppView({
  threadId,
  implementation,
  preview,
}: {
  threadId: string;
  implementation: ImplementationResponse;
  preview: PreviewResponse | null;
}) {
  const done = implementation.tasks.filter((t) => t.status === "done").length;
  return (
    <section className="animate-fade-up space-y-4" aria-label="Your app">
      <Card>
        <CardHeader
          eyebrow="Your app"
          title={
            <span className="flex items-center gap-2">
              <Boxes className="size-5 text-brand" aria-hidden />
              {done} of {implementation.tasks.length} tasks done
            </span>
          }
          description={`Project folder: ${implementation.workspace_dir ?? "unknown"}`}
          aside={
            <>
              {implementation.build && (
                <Badge tone={implementation.build.passed ? "emerald" : "red"} size="md">
                  Build {implementation.build.passed ? "passed" : "failed"}
                </Badge>
              )}
              <Badge tone="slate" size="md">
                Agent cost ${implementation.cost_usd.toFixed(2)}
              </Badge>
            </>
          }
        />
      </Card>
      <PreviewCard threadId={threadId} initial={preview} />
      {implementation.build && <BuildCard build={implementation.build} />}
      <TaskList tasks={implementation.tasks} />
    </section>
  );
}
