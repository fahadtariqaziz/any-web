"use client";

// Settings the generated app needs to run (its .env.example variables), above the live preview. Shown when the
// render check found the page blank or a setting is missing: the browser error, setup steps per service, and a form.
// Values go to the backend once and are never shown again: they are kept in the session's .builder/app.env and given
// to the dev server only — not to the code, the AI or the download. That is why the chat is NOT the place for keys.

import { AlertTriangle, CheckCircle2, ChevronDown, Database, ExternalLink, KeyRound } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError, checkAppDatabase, getAppSettings, saveAppSettings, setupAppDatabase } from "@/lib/api/client";
import type { AppDatabase, AppSettingsResponse, PreviewResponse, RenderCheck } from "@/lib/api/types";

export function AppSettingsPanel({
  threadId,
  render,
  serverStartedAt,
  builderBusy,
  onPreview,
}: {
  threadId: string;
  render: RenderCheck | null | undefined;
  serverStartedAt: string | null | undefined; // reload the list after every restart
  builderBusy: boolean;
  onPreview: (preview: PreviewResponse) => void;
}) {
  const [settings, setSettings] = useState<AppSettingsResponse | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [toggled, setToggled] = useState<boolean | null>(null); // the user's choice; null = automatic
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAppSettings(threadId)
      .then((next) => !cancelled && setSettings(next))
      .catch(() => !cancelled && setSettings(null)); // nothing built yet: the panel simply does not show
    return () => {
      cancelled = true;
    };
  }, [threadId, serverStartedAt]); // reload after every restart

  const blank = render?.status === "blank";
  const missing = settings?.missing ?? [];
  const dbMissing = settings?.database?.check?.status === "missing";
  const open = toggled ?? (blank || missing.length > 0 || dbMissing); // open while something needs attention

  if (!blank && (!settings || settings.variables.length === 0)) return null;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const result = await saveAppSettings(threadId, values);
      setSettings(result);
      setValues({});
      setSaved(true);
      if (result.preview) onPreview(result.preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the settings.");
    } finally {
      setSaving(false);
    }
  }

  const variables = settings?.variables ?? [];
  const needsSettings = missing.length > 0;
  const title = blank
    ? needsSettings
      ? `Your app shows a blank page: it needs ${missing.length} setting${missing.length === 1 ? "" : "s"} to run`
      : "Your app shows a blank page: it crashed in the browser before drawing anything"
    : needsSettings
      ? `Your app needs ${missing.length} setting${missing.length === 1 ? "" : "s"} to work fully`
      : dbMissing
        ? "Your app's database is not set up yet: its tables are missing"
        : "App settings: all set";
  const tone = blank ? "border-red-200 bg-red-50 text-red-900" : needsSettings || dbMissing ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-slate-50 text-slate-700";
  const typed = Object.values(values).some((v) => v.trim());

  return (
    <div className={`shrink-0 border-b text-xs ${tone} ${open ? "max-h-[65%] overflow-auto" : ""}`}>
      <button type="button" onClick={() => setToggled(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left font-semibold" aria-expanded={open}>
        {blank ? <AlertTriangle className="size-4 shrink-0" aria-hidden /> : <KeyRound className="size-4 shrink-0" aria-hidden />}
        <span className="flex-1">{title}</span>
        <ChevronDown className={`size-4 shrink-0 transition ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && (
        <div className="space-y-3 px-3 pb-3">
          {blank && render && render.errors.length > 0 && (
            <details>
              <summary className="cursor-pointer font-medium">What the browser reported</summary>
              <pre className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap rounded bg-white/70 p-2">{render.errors.join("\n\n")}</pre>
            </details>
          )}

          {variables.length > 0 ? (
            <>
              {settings!.guides.map((g) => (
                <div key={g.service} className="rounded-lg bg-white/70 p-2.5 text-slate-800">
                  <p className="mb-1 font-semibold">
                    How to get the {g.service} settings{" "}
                    <a href={g.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-normal text-brand underline">
                      open {g.service} <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </p>
                  <ol className="list-decimal space-y-0.5 pl-5">
                    {g.steps.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ol>
                </div>
              ))}

              <form onSubmit={save} className="space-y-2 rounded-lg bg-white/70 p-2.5 text-slate-800">
                {variables.map((v) => (
                  <label key={v.name} className="block space-y-0.5">
                    <span className="flex items-center gap-2 font-mono font-medium">
                      {v.name}
                      <span className={`rounded px-1 font-sans text-[10px] ${v.set ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{v.set ? "saved" : "missing"}</span>
                    </span>
                    {v.help.map((h) => (
                      <span key={h} className="block text-slate-500">
                        {h}
                      </span>
                    ))}
                    <input
                      type={v.public ? "text" : "password"}
                      autoComplete="off"
                      spellCheck={false}
                      value={values[v.name] ?? ""}
                      onChange={(e) => setValues((cur) => ({ ...cur, [v.name]: e.target.value }))}
                      placeholder={v.set ? "saved (type to replace)" : v.example || "paste the value"}
                      className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 font-mono text-xs focus:border-brand focus:outline-none"
                    />
                  </label>
                ))}
                {variables.some((v) => v.public) && (
                  <p className="text-slate-500">
                    Names starting with VITE_ / NEXT_PUBLIC_ end up in the browser by design: use public keys (e.g. the Supabase anon key), never a
                    service-role or secret key.
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <Button type="submit" size="sm" loading={saving} disabled={!typed}>
                    {builderBusy ? "Save" : "Save and restart the preview"}
                  </Button>
                  {saved && <span className="text-emerald-700">Saved{builderBusy ? ": the preview uses them at its next start." : "."}</span>}
                  {error && <span className="text-red-700">{error}</span>}
                </div>
              </form>

              {settings!.database && <DatabaseSection threadId={threadId} database={settings!.database} onSettings={setSettings} />}

              <p className="text-slate-600">
                <strong>Don&apos;t paste keys into the chat.</strong> Chat messages go to the AI, and a change request would write them into the code.
                Values saved here stay on this computer and are given only to the preview&apos;s dev server. They are never added to the code or the
                download.
              </p>
              <p className="text-slate-600">
                No account yet? Use <em>Request some change in app</em>, e.g. &quot;run in demo mode with sample data when the settings are missing&quot;.
              </p>
            </>
          ) : (
            <p>
              The app has no settings to fill in (no .env.example). Describe the fix as a change request in the chat, e.g. &quot;the preview is blank:
              fix the error above&quot;.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Supabase apps: is the database set up (read-only check), and run the migration files on the user's request. */
function DatabaseSection({ threadId, database, onSettings }: { threadId: string; database: AppDatabase; onSettings: (s: AppSettingsResponse) => void }) {
  const [dbUrl, setDbUrl] = useState("");
  const [busy, setBusy] = useState<"check" | "setup" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const check = database.check;
  const ready = check?.status === "ready";

  async function run(kind: "check" | "setup") {
    setBusy(kind);
    setError(null);
    try {
      const result = kind === "check" ? await checkAppDatabase(threadId) : await setupAppDatabase(threadId, dbUrl);
      onSettings(result);
      if (kind === "setup" && result.database?.setup?.ok) setDbUrl(""); // used once: not kept in the page either
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
    } finally {
      setBusy(null);
    }
  }

  const status = !check
    ? "Not checked yet: save the Supabase settings above, or check now."
    : check.status === "ready"
      ? `Database ready: all ${database.tables.length} tables of the app exist.`
      : check.status === "missing"
        ? `${check.missing?.length} of ${database.tables.length} tables are missing: ${check.missing?.join(", ")}.`
        : check.status === "unknown"
          ? `Could not check every table: ${check.errors?.join("; ")}`
          : `Not checked: ${check.reason}.`;
  const setup = database.setup;

  return (
    <div className="space-y-2 rounded-lg bg-white/70 p-2.5 text-slate-800">
      <p className="flex items-center gap-1.5 font-semibold">
        {ready ? <CheckCircle2 className="size-4 text-emerald-600" aria-hidden /> : <Database className="size-4" aria-hidden />} Database
      </p>
      <p className={ready ? "text-emerald-700" : check?.status === "missing" ? "text-amber-800" : "text-slate-600"}>{status}</p>
      <Button type="button" size="sm" variant="ghost" loading={busy === "check"} disabled={busy !== null} onClick={() => run("check")}>
        Check again
      </Button>

      {!ready && (
        <div className="space-y-1.5 border-t border-slate-200 pt-2">
          <p className="font-medium">Set up the database for you</p>
          <p className="text-slate-600">
            The builder runs the app&apos;s {database.migrations.length} migration file{database.migrations.length === 1 ? "" : "s"} ({database.migrations.join(", ")}) on your Supabase project, in order, each in its own transaction. Files already run are skipped. This changes your project&apos;s database.
          </p>
          <ol className="list-decimal space-y-0.5 pl-5 text-slate-600">
            <li>In your Supabase project, click <strong>Connect</strong> (top bar) and pick the <strong>Session pooler</strong> connection string (URI).</li>
            <li>Replace [YOUR-PASSWORD] with your database password (forgot it? Project Settings → Database → Reset password).</li>
            <li>Paste it below and press the button. It is used for this run only: not saved, not shown to the AI, not added to the code.</li>
          </ol>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={dbUrl}
            onChange={(e) => setDbUrl(e.target.value)}
            placeholder="postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 font-mono text-xs focus:border-brand focus:outline-none"
          />
          <Button type="button" size="sm" loading={busy === "setup"} disabled={busy !== null || dbUrl.trim().length < 10} onClick={() => run("setup")}>
            Set up database
          </Button>
          <p className="text-slate-500">Prefer to do it yourself? Run the same files in that order in the Supabase SQL Editor, then press Check again.</p>
        </div>
      )}

      {setup && (
        <div className={`rounded p-2 ${setup.ok ? "bg-emerald-50 text-emerald-900" : "bg-red-50 text-red-900"}`}>
          {setup.files.map((f) => (
            <p key={f.file}>
              <span className="font-mono">{f.file}</span>: {f.status}
              {f.error ? ` (${f.error})` : ""}
            </p>
          ))}
          {setup.error && <p className="font-medium">{setup.error}</p>}
          {setup.ok && <p>Done. Accounts created before this setup may miss data the database creates at sign-up: sign up again with a new account if screens stay empty.</p>}
        </div>
      )}
      {error && <p className="text-red-700">{error}</p>}
    </div>
  );
}
