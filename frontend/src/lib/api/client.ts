// The only place that talks to the backend. UI components call these functions and never use fetch directly.
//
// Every backend error looks like {"error": {"code", "message"}}; it is thrown as an ApiError so the UI
// can show the message and decide by status / code (e.g. 409 "already_running").

import type {
  Accepted,
  ArtifactList,
  BriefResponse,
  PlanResponse,
  ChatTranscript,
  CodeExportResponse,
  CreateDecisionRequest,
  DecisionStatus,
  EvidenceResponse,
  ImplementationResponse,
  LiveSnapshot,
  PreviewResponse,
  ReportResponse,
  ResumeRequest,
  SessionList,
  SessionMode,
} from "./types";

// NEXT_PUBLIC_ variables are copied into the browser bundle: only put public values here, never API keys.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BASE = "/api/decisions";
const CHATS = "/api/chats";

export class ApiError extends Error {
  constructor(
    public status: number, // HTTP status; 0 = the backend could not be reached
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Long-term memory without a login: a random id kept in this browser and sent with every request, so the
// agents can remember the user from one session to the next (backend memory.py). Not a secret, not an account.
const USER_KEY = "userId";

export function userId(): string | null {
  if (typeof window === "undefined") return null; // server render: no browser storage
  let id = localStorage.getItem(USER_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(USER_KEY, id);
  }
  return id;
}

function userHeader(): Record<string, string> {
  const id = userId();
  return id ? { "X-User-Id": id } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...userHeader(), ...init?.headers },
      cache: "no-store", // status changes every few seconds: never reuse an old answer
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the backend at ${API_URL}. Is it running?`);
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}

function toApiError(status: number, body: { error?: { code?: string; message?: string } } | null): ApiError {
  return new ApiError(status, body?.error?.code ?? "http_error", body?.error?.message ?? `Request failed with status ${status}.`);
}

/** Start a session. Returns at once (202) with the thread_id; the graph runs in the background. */
export function createDecision(body: CreateDecisionRequest): Promise<Accepted> {
  return request(BASE, { method: "POST", body: JSON.stringify(body) });
}

/** Current state of a session: run_state, progress lines, pending pause. Poll this. */
export function getDecision(threadId: string): Promise<DecisionStatus> {
  return request(`${BASE}/${encodeURIComponent(threadId)}`);
}

/** Answer the pending pause (or {type: "continue"} for an interrupted run). */
export function resumeDecision(threadId: string, body: ResumeRequest): Promise<Accepted> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/resume`, { method: "POST", body: JSON.stringify(body) });
}

/** The final report. 409 "not_finished" until the session is finished. */
export function getReport(threadId: string): Promise<ReportResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/report`);
}

/** The validated problem statement + solution brief. 409 "no_brief" until the validator approved a draft. */
export function getBrief(threadId: string): Promise<BriefResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/brief`);
}

/** The implementation plan. 409 "no_plan" until the planner wrote one. */
export function getPlan(threadId: string): Promise<PlanResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/plan`);
}

/** The coding agent's tasks, attempt log and last build check. 409 "no_implementation" before the build started. */
export function getImplementation(threadId: string): Promise<ImplementationResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/implementation`);
}

/** Live state of the session's dev server (reading it keeps the preview from the idle stop). 409 "no_preview" before. */
export function getPreview(threadId: string): Promise<PreviewResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/preview`);
}

/** Restart the dev server; answers after the health check (up to a minute). */
export function restartPreview(threadId: string): Promise<PreviewResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/preview/restart`, { method: "POST" });
}

export function stopPreview(threadId: string): Promise<PreviewResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/preview/stop`, { method: "POST" });
}

/** The generated project's files (JSON, base64) for writing them into a folder the user picks. */
export function getCode(threadId: string): Promise<CodeExportResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/code`);
}

/** The same files as a zip (one top-level folder): a plain link, for browsers without a folder picker. */
export function codeZipUrl(threadId: string): string {
  return `${API_URL}${BASE}/${encodeURIComponent(threadId)}/code.zip`;
}

/** Approved versions of the brief (and later the plan). 503 if the database cannot be read. */
export function getArtifacts(threadId: string): Promise<ArtifactList> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/artifacts`);
}

/** Evidence kept so far, with verification status. */
export function getEvidence(threadId: string): Promise<EvidenceResponse> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/evidence`);
}

/** Everything the agents produced so far: case facts, evidence counts, plans, criticisms, scores, verdicts. */
export function getLive(threadId: string): Promise<LiveSnapshot> {
  return request(`${BASE}/${encodeURIComponent(threadId)}/live`);
}

/** Recent sessions, newest first (503 if the database cannot be read). mode: only admin or only chat sessions. */
export function listDecisions(limit = 20, mode?: SessionMode): Promise<SessionList> {
  return request(`${BASE}?limit=${limit}${mode ? `&mode=${mode}` : ""}`);
}

// --- builder chat (conversation + Ask mode) ---------------------------------------------------------

/** The chat's onboarding (first message, answered questions, summary) and its messages. */
export function getChat(threadId: string): Promise<ChatTranscript> {
  return request(`${CHATS}/${encodeURIComponent(threadId)}`);
}

/** Send a chat message. The reply streams back as plain text: onText gets each new piece as it arrives.
 *  Resolves with the whole reply once the stream ends. */
export async function sendChatMessage(threadId: string, content: string, onText: (piece: string) => void): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${CHATS}/${encodeURIComponent(threadId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...userHeader() },
      body: JSON.stringify({ content }),
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the backend at ${API_URL}. Is it running?`);
  }
  if (!response.ok || !response.body) {
    throw toApiError(response.status, await response.json().catch(() => null));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder(); // stream: true below keeps multi-byte characters split across chunks intact
  let reply = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const piece = decoder.decode(value, { stream: true });
    reply += piece;
    onText(piece);
  }
  return reply;
}
