"use client";

import { PlayCircle } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { ApiError, resumeDecision } from "@/lib/api/client";
import type { DecisionStatus } from "@/lib/api/types";
import { nodeLabel } from "@/lib/pipeline";

/** The run stopped mid-way (server restart or crash). Everything up to the last finished step is saved. */
export function InterruptedPanel({ threadId, status, onSubmitted }: { threadId: string; status: DecisionStatus; onSubmitted: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = status.next_nodes[0];

  async function resume() {
    setBusy(true);
    setError(null);
    try {
      await resumeDecision(threadId, { type: "continue" });
      onSubmitted();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Callout tone="warning" title="This run was interrupted">
        <p>
          The backend stopped before the session finished (for example it was restarted). Every finished step is saved
          {next ? <>; the next step is <strong>{nodeLabel(next)}</strong>.</> : "."}
        </p>
        {status.error && <p className="text-xs opacity-80">Last recorded error: {status.error.message}</p>}
        <div className="pt-2">
          <Button onClick={resume} loading={busy} icon={<PlayCircle className="size-4" aria-hidden />}>
            Continue from the last step
          </Button>
        </div>
      </Callout>
      {error && (
        <Callout tone="danger">
          <p>{error}</p>
        </Callout>
      )}
    </div>
  );
}
