"use client";

// The agents' work so far (plans, scores, verdicts...). Re-fetched whenever a node finishes or the
// run state changes, so the user watches results appear, not only log lines.

import { getBrief, getEvidence, getImplementation, getLive, getPlan, getPreview, getReport, listDecisions } from "@/lib/api/client";
import { useFetch } from "@/hooks/useFetch";

export function useLive(threadId: string, version: string, enabled = true) {
  return useFetch(() => getLive(threadId), `${threadId}|${version}`, enabled);
}

export function useReport(threadId: string, enabled: boolean) {
  return useFetch(() => getReport(threadId), threadId, enabled);
}

export function useBrief(threadId: string, enabled: boolean) {
  return useFetch(() => getBrief(threadId), threadId, enabled);
}

export function usePlan(threadId: string, enabled: boolean) {
  return useFetch(() => getPlan(threadId), threadId, enabled);
}

export function useImplementation(threadId: string, enabled: boolean) {
  return useFetch(() => getImplementation(threadId), threadId, enabled);
}

/** GET /preview also counts as "looked at" for the idle stop. 409 "no_preview" when nothing was started. */
export function usePreview(threadId: string, enabled: boolean) {
  return useFetch(() => getPreview(threadId), threadId, enabled);
}

export function useEvidence(threadId: string, version: string, enabled: boolean) {
  return useFetch(() => getEvidence(threadId), `${threadId}|${version}`, enabled);
}

export function useSessions(enabled = true) {
  return useFetch(() => listDecisions(20), "sessions", enabled);
}
