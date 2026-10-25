"use client";

// "Download code" (right of the work-pane tabs): the generated project as a folder on the user's computer.
//
// Chrome / Edge: a folder picker (File System Access API); the project is written into a NEW subfolder of the chosen
// folder (e.g. Projects/simple-calculator-web-app/), after a confirmation if that subfolder already has files. Other
// browsers have no folder picker for web pages: the button downloads a zip (the browser decides where it is saved).
// Left out by the backend: node_modules, build output, .git, .env* (except .env.example), symlinks.
// Paths come from our backend but are written to the user's disk, so each one is checked again here.

import { Download } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError, codeZipUrl, getCode } from "@/lib/api/client";
import type { PlanCommands } from "@/lib/api/types";

// Not in TypeScript's DOM lib yet (Chromium only): the parts we use.
type DirectoryHandle = {
  name: string;
  getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<DirectoryHandle>;
  getFileHandle(name: string, options?: { create?: boolean }): Promise<{ createWritable(): Promise<{ write(data: BufferSource): Promise<void>; close(): Promise<void> }> }>;
  keys(): AsyncIterableIterator<string>;
};
type PickerWindow = Window & { showDirectoryPicker?: (options?: { id?: string; mode?: "readwrite" }) => Promise<DirectoryHandle> };

/** "src/ui/app.js" → ["src", "ui", "app.js"]; null for anything that could leave the chosen folder. */
function safeParts(path: string): string[] | null {
  const parts = path.split("/");
  const bad = path.startsWith("/") || path.includes("\\") || path.includes(":") || parts.some((p) => p === "" || p === "." || p === "..");
  return bad ? null : parts;
}

function decode(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

type Result = { tone: "ok" | "error"; text: string; skipped?: string[] };

export function DownloadCode({ threadId, enabled, busy, commands }: { threadId: string; enabled: boolean; busy: boolean; commands: PlanCommands | null }) {
  const [working, setWorking] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  async function download() {
    setResult(null);
    const picker = (window as PickerWindow).showDirectoryPicker;
    if (!picker) {
      window.location.href = codeZipUrl(threadId); // zip: the browser's own download (Content-Disposition: attachment)
      setResult({ tone: "ok", text: "Downloading a zip: this browser cannot save into a folder you pick (Chrome and Edge can)." });
      return;
    }
    let parent: DirectoryHandle;
    try {
      parent = await picker({ id: "builder-code", mode: "readwrite" });
    } catch {
      return; // the user closed the picker
    }
    setWorking(true);
    try {
      const code = await getCode(threadId);
      const target = await parent.getDirectoryHandle(code.folder_name, { create: true });
      let existing = 0;
      for await (const name of target.keys()) {
        void name;
        existing++;
      }
      if (existing > 0 && !window.confirm(`"${parent.name}/${code.folder_name}" already has files. Overwrite the ones with the same names?`)) {
        return;
      }
      let written = 0;
      for (const file of code.files) {
        const parts = safeParts(file.path);
        if (!parts) continue;
        let dir = target;
        for (const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
        const writable = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
        await writable.write(decode(file.content_b64));
        await writable.close();
        written++;
      }
      const run = commands ? [...commands.install, commands.dev].filter(Boolean).join(" → ") : "";
      setResult({
        tone: "ok",
        text: `Saved ${written} files to ${parent.name}/${code.folder_name}.${run ? ` Run it there: ${run}.` : ""}`,
        skipped: code.skipped,
      });
    } catch (e) {
      setResult({ tone: "error", text: e instanceof ApiError ? e.message : `Could not save the code: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="relative ml-auto flex items-center pb-1">
      <Button
        variant="secondary"
        size="sm"
        onClick={download}
        loading={working}
        disabled={!enabled || busy}
        title={!enabled ? "Available once the app is built" : busy ? "Wait until the builder is done with this step" : "Save the project's source code on your computer"}
        icon={<Download className="size-4" aria-hidden />}
      >
        Download code
      </Button>
      {result && (
        <div
          role="status"
          className={`absolute right-0 top-full z-20 mt-1 w-80 rounded-lg border p-3 text-xs shadow-lg ${result.tone === "ok" ? "border-emerald-200 bg-white text-slate-700" : "border-red-200 bg-red-50 text-red-800"}`}
        >
          <p>{result.text}</p>
          {result.skipped && result.skipped.length > 0 && (
            <details className="mt-1.5 text-slate-500">
              <summary className="cursor-pointer">Left out: {result.skipped.length}</summary>
              <ul className="mt-1 list-disc pl-4">
                {result.skipped.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </details>
          )}
          <button type="button" onClick={() => setResult(null)} className="mt-1.5 text-slate-500 underline hover:text-slate-800">
            Close
          </button>
        </div>
      )}
    </div>
  );
}
