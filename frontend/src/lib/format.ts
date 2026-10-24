// Small formatting helpers and the visual vocabulary (colours per perspective / state) used everywhere.

import type { Level, Perspective, RunState, VerificationStatus } from "@/lib/api/types";

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  if (m < 60) return rest ? `${m}m ${rest}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function secondsSince(iso: string | null | undefined, now: number): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? Math.max(0, (now - t) / 1000) : 0;
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const diff = (now - new Date(iso).getTime()) / 1000;
  if (diff < 45) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  if (diff < 7 * 86400) return `${Math.round(diff / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// --- perspectives -------------------------------------------------------------------------------

export const PERSPECTIVES: Perspective[] = ["research", "doctor", "patient"];

export const PERSPECTIVE_META: Record<Perspective, { label: string; short: string; description: string; dot: string; text: string; bg: string; border: string; ring: string }> = {
  research: {
    label: "Research perspective",
    short: "Research",
    description: "Papers, trials, systematic reviews",
    dot: "bg-violet-500",
    text: "text-violet-700",
    bg: "bg-violet-50",
    border: "border-violet-200",
    ring: "ring-violet-300",
  },
  doctor: {
    label: "Doctor perspective",
    short: "Doctor",
    description: "Clinical guidelines, medical references",
    dot: "bg-sky-500",
    text: "text-sky-700",
    bg: "bg-sky-50",
    border: "border-sky-200",
    ring: "ring-sky-300",
  },
  patient: {
    label: "Patient perspective",
    short: "Patient",
    description: "Real-world experiences from forums and reviews",
    dot: "bg-amber-500",
    text: "text-amber-800",
    bg: "bg-amber-50",
    border: "border-amber-200",
    ring: "ring-amber-300",
  },
};

export function perspectiveOf(value: string): Perspective | null {
  return (PERSPECTIVES as string[]).includes(value) ? (value as Perspective) : null;
}

// --- states ---------------------------------------------------------------------------------------

export type Tone = "neutral" | "brand" | "amber" | "orange" | "emerald" | "red" | "violet" | "sky" | "slate";

export const RUN_STATE_META: Record<RunState, { label: string; tone: Tone }> = {
  running: { label: "Agents at work", tone: "brand" },
  paused: { label: "Waiting for you", tone: "amber" },
  interrupted: { label: "Interrupted", tone: "orange" },
  finished: { label: "Finished", tone: "emerald" },
};

export const WORKFLOW_STATUS_LABEL: Record<string, string> = {
  intake: "Understanding your message",
  awaiting_clarification: "Waiting for your answers",
  researching: "Researching",
  debating: "Debating care plans",
  verifying: "Verifying evidence",
  reporting: "Writing the report",
  completed: "Completed",
  completed_with_uncertainty: "Completed with uncertainty",
  failed: "Failed",
};

export function workflowStatusTone(status: string | null | undefined): Tone {
  switch (status) {
    case "completed": return "emerald";
    case "completed_with_uncertainty": return "amber";
    case "failed": return "red";
    case "awaiting_clarification": return "amber";
    default: return "brand";
  }
}

export const VERIFICATION_META: Record<VerificationStatus, { label: string; tone: Tone }> = {
  pending: { label: "Not checked", tone: "slate" },
  verified: { label: "Verified", tone: "emerald" },
  partially_supported: { label: "Partly supported", tone: "amber" },
  unsupported: { label: "Unsupported", tone: "orange" },
  contradicted: { label: "Contradicted", tone: "red" },
  irrelevant: { label: "Irrelevant", tone: "slate" },
  unavailable: { label: "Source unavailable", tone: "slate" },
};

export const LEVEL_TONE: Record<Level, Tone> = { low: "emerald", medium: "amber", high: "red" };
export const CONFIDENCE_TONE: Record<Level, Tone> = { low: "red", medium: "amber", high: "emerald" };

export const RUBRIC: { key: string; label: string; weight: number }[] = [
  { key: "fit_to_user", label: "Fit to you", weight: 0.3 },
  { key: "safety", label: "Safety", weight: 0.25 },
  { key: "evidence_quality", label: "Evidence quality", weight: 0.2 },
  { key: "practicality", label: "Practicality", weight: 0.15 },
  { key: "completeness", label: "Completeness", weight: 0.1 },
];

export const SOURCE_TYPE_LABEL: Record<string, string> = {
  research_paper: "Research paper",
  clinical_guideline: "Clinical guideline",
  medical_reference: "Medical reference",
  patient_community: "Patient community",
  health_article: "Health article",
  other: "Other source",
};

export const STRENGTH_LABEL: Record<string, string> = {
  systematic_review_or_meta_analysis: "Systematic review / meta-analysis",
  randomized_trial: "Randomised trial",
  observational_study: "Observational study",
  clinical_guideline: "Clinical guideline",
  expert_or_reference: "Expert / reference",
  anecdotal: "Anecdotal",
  unknown: "Strength unknown",
};
