"use client";

// The live preview (spec §9, right side): the session's dev server in an iframe, with a small browser bar (state,
// address, reload, desktop / phone width, open in a new tab, restart). Facts only: the app is shown when the
// backend's health check said "ready"; otherwise the dev server's own error and log are shown.
//
// GET /preview is polled (every 5 s while something is changing, every 30 s while it runs). Reading it counts as
// "looked at", so an open preview is not idle-stopped. The iframe reloads by itself when the dev server was
// restarted (a change was applied: new started_at).

import { ExternalLink, Laptop, MonitorPlay, Play, RotateCw, Smartphone } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError, getPreview, restartPreview } from "@/lib/api/client";
import type { PreviewResponse } from "@/lib/api/types";

const BUSY_POLL_MS = 5000;
const IDLE_POLL_MS = 30000;

/** Polls GET /preview while enabled. `null` = no preview was started yet (409 no_preview). */
export function usePreviewStatus(threadId: string, enabled: boolean, busy: boolean) {
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      let next: PreviewResponse | null = null;
      try {
        next = await getPreview(threadId);
        if (cancelled) return;
        setPreview(next);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.code === "no_preview") setPreview(null);
        else setError(e instanceof ApiError ? e.message : "Could not read the preview.");
      }
      setLoaded(true);
      const settled = next?.state === "ready" || next?.state === "stopped";
      timer = setTimeout(load, busy || !settled ? BUSY_POLL_MS : IDLE_POLL_MS);
    }
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [threadId, enabled, busy, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { preview, setPreview, error, loaded, reload };
}

export function PreviewPane({
  threadId,
  enabled,
  builderBusy,
  emptyText,
}: {
  threadId: string;
  enabled: boolean; // the build started (has_build)
  builderBusy: boolean; // the graph is running: the preview restarts itself after changes
  emptyText: string;
}) {
  const { preview, setPreview, error, loaded } = usePreviewStatus(threadId, enabled, builderBusy);
  const [reloads, setReloads] = useState(0);
  const [phone, setPhone] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  async function restart() {
    setRestarting(true);
    setRestartError(null);
    try {
      setPreview(await restartPreview(threadId));
    } catch (e) {
      setRestartError(e instanceof ApiError ? e.message : "Could not start the preview.");
    } finally {
      setRestarting(false);
    }
  }

  const state = preview?.state;
  const url = state === "ready" ? preview?.url : null;
  const dot = state === "ready" ? "bg-emerald-500" : state === "failed" ? "bg-red-500" : state === "starting" ? "bg-amber-400 animate-pulse" : "bg-slate-300";

  let body: React.ReactNode;
  if (!enabled || (loaded && !preview && !error)) {
    body = (
      <Placeholder icon={<MonitorPlay className="size-8 text-slate-300" aria-hidden />} title="Your app will appear here">
        {emptyText}
      </Placeholder>
    );
  } else if (!loaded) {
    body = <Placeholder icon={<Spinner className="size-6 text-brand" />} title="Loading the preview…" />;
  } else if (url) {
    body = (
      <div className="flex h-full justify-center overflow-auto bg-slate-100">
        <iframe
          key={`${preview?.started_at}|${reloads}`}
          src={url}
          title="Preview of your app"
          className={`h-full bg-white ${phone ? "my-3 h-[calc(100%-1.5rem)] w-[390px] rounded-xl border border-slate-300 shadow" : "w-full"}`}
          sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-modals"
        />
      </div>
    );
  } else if (state === "starting") {
    body = <Placeholder icon={<Spinner className="size-6 text-brand" />} title="Starting your app…">The dev server counts as ready once it answers.</Placeholder>;
  } else if (state === "stopped") {
    body = (
      <Placeholder icon={<Play className="size-8 text-slate-300" aria-hidden />} title="The preview is stopped">
        <p>Previews stop after a while without being looked at. Start it to run your app again.</p>
        <Button className="mt-3" size="sm" onClick={restart} loading={restarting} disabled={builderBusy} icon={<Play className="size-4" aria-hidden />}>
          Start the preview
        </Button>
      </Placeholder>
    );
  } else {
    body = (
      <div className="h-full space-y-3 overflow-auto p-5">
        <p className="font-semibold text-red-700">Your app did not start</p>
        <p className="text-sm text-slate-600">
          Command: <code className="rounded bg-slate-100 px-1">{preview?.command ?? "unknown"}</code>
        </p>
        {preview?.last_error && <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-red-50 p-3 text-xs text-red-900">{preview.last_error}</pre>}
        {preview?.log_tail && (
          <details>
            <summary className="cursor-pointer text-sm font-medium text-slate-700">Dev server output</summary>
            <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{preview.log_tail}</pre>
          </details>
        )}
        <p className="text-sm text-slate-600">Describe the problem as a change request in the chat, or restart the preview.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-11 shrink-0 items-center gap-1.5 border-b border-slate-200 px-2">
        <ToolbarButton label="Reload" onClick={() => setReloads((n) => n + 1)} disabled={!url}>
          <RotateCw className="size-4" aria-hidden />
        </ToolbarButton>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
          <span className={`size-2 shrink-0 rounded-full ${dot}`} aria-hidden />
          <span className="truncate">{url ?? (state ? `preview ${state}` : "no preview yet")}</span>
        </div>
        <ToolbarButton label={phone ? "Desktop width" : "Phone width"} onClick={() => setPhone((p) => !p)} disabled={!url}>
          {phone ? <Laptop className="size-4" aria-hidden /> : <Smartphone className="size-4" aria-hidden />}
        </ToolbarButton>
        {url && (
          <a href={url} target="_blank" rel="noreferrer" title="Open in a new tab" aria-label="Open in a new tab" className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900">
            <ExternalLink className="size-4" aria-hidden />
          </a>
        )}
        {preview && (
          <Button
            variant="ghost"
            size="sm"
            onClick={restart}
            loading={restarting}
            disabled={builderBusy}
            title={builderBusy ? "The builder is working; the preview restarts itself" : "Restart the dev server"}
          >
            {state === "ready" ? "Restart" : "Start"}
          </Button>
        )}
      </div>
      {(error || restartError) && <p className="border-b border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-800">{restartError ?? error}</p>}
      <div className="min-h-0 flex-1">{body}</div>
    </div>
  );
}

function ToolbarButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={label} aria-label={label} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-40">
      {children}
    </button>
  );
}

function Placeholder({ icon, title, children }: { icon: React.ReactNode; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
      {icon}
      <p className="font-medium text-slate-700">{title}</p>
      {children && <div className="max-w-sm text-sm text-slate-500">{children}</div>}
    </div>
  );
}
