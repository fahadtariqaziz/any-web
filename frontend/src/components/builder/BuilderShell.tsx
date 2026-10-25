"use client";

// Full-screen builder layout (Lovable style): a thin top bar (projects, logo, new project, admin view) and the
// page below it, which fills the rest of the screen (the project page splits it into chat | preview).

import { Blocks, LayoutDashboard, PanelLeft, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ProjectListProvider } from "./ProjectListContext";
import { ProjectsDrawer } from "./ProjectsDrawer";

export function BuilderShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <ProjectListProvider>
      <div className="flex h-dvh flex-col overflow-hidden bg-white text-slate-900">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 px-2 sm:px-3">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            aria-label="Your projects"
            title="Your projects"
          >
            <PanelLeft className="size-5" aria-hidden />
          </button>
          <Link href="/" className="flex items-center gap-2 px-1">
            <span className="flex size-7 items-center justify-center rounded-lg bg-brand text-white">
              <Blocks className="size-4" aria-hidden />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">AI App Builder</span>
          </Link>
          <div className="flex-1" />
          <Link
            href="/admin"
            className="hidden items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
          >
            <LayoutDashboard className="size-4" aria-hidden />
            Admin view
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            <Plus className="size-4" aria-hidden />
            <span className="hidden sm:inline">New project</span>
          </Link>
        </header>
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        {open && <ProjectsDrawer onClose={() => setOpen(false)} />}
      </div>
    </ProjectListProvider>
  );
}
