"use client";

// One small hook for the "fetch when something changes, keep the old data meanwhile" pattern used by
// the live snapshot, the report and the evidence list. `version` is any string: when it changes, we
// fetch again. `enabled` false = do nothing (e.g. a tab that is not open).

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";

export function useFetch<T>(fetcher: () => Promise<T>, version: string, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [settledVersion, setSettledVersion] = useState<string | null>(null); // version the data/error belong to
  const loading = enabled && settledVersion !== version; // derived, so no setState in the effect body

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetcher()
      .then((next) => {
        if (cancelled) return;
        setData(next);
        setError(null);
        setSettledVersion(version);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e : new ApiError(0, "unknown", String(e)));
        setSettledVersion(version);
      });
    return () => {
      cancelled = true;
    };
    // `fetcher` is recreated on every render; `version` is the real trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, enabled]);

  return { data, error, loading };
}
