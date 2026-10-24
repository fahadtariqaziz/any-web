"use client";

// Keeps a session's status fresh: GET every 2 s while the graph runs, stop when it pauses or finishes.
// Everything shown comes from the backend (run_state, progress, pending); the UI never guesses.
// After a POST /resume, call refresh() to start polling again.

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getDecision } from "@/lib/api/client";
import type { DecisionStatus } from "@/lib/api/types";

const POLL_MS = 2000;
const RETRY_MS = 5000; // backend unreachable: keep trying, a bit slower

export function useDecision(threadId: string, pollMs = POLL_MS) {
  const [status, setStatus] = useState<DecisionStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [refreshCount, setRefreshCount] = useState(0); // changing it re-runs the effect below
  const [lastUpdate, setLastUpdate] = useState<number | null>(null); // client time of the last successful GET
  const firstSeenRunning = useRef<number | null>(null); // fallback stage start before any progress line exists

  useEffect(() => {
    let cancelled = false; // set when the page unmounts or threadId changes: ignore late answers
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      try {
        const next = await getDecision(threadId);
        if (cancelled) return;
        if (next.run_state === "running") firstSeenRunning.current ??= Date.now();
        else firstSeenRunning.current = null;
        setStatus(next);
        setError(null);
        setLastUpdate(Date.now());
        if (next.run_state === "running") timer = setTimeout(load, pollMs);
      } catch (e) {
        if (cancelled) return;
        const err = e instanceof ApiError ? e : new ApiError(0, "unknown", String(e));
        setError(err);
        if (err.status === 0 || err.status >= 500) timer = setTimeout(load, RETRY_MS); // 404 etc.: stop
      }
    }

    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [threadId, refreshCount, pollMs]);

  const refresh = useCallback(() => setRefreshCount((n) => n + 1), []);

  return { status, error, refresh, lastUpdate, firstSeenRunning };
}
