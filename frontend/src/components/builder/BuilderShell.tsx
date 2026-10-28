"use client";

// Full-screen builder layout (Lovable style): a thin frosted top bar (projects, logo, new project, admin view) and
// the page below it, which fills the rest of the screen (the project page splits it into chat | preview).

import { Blocks, LayoutDashboard, PanelLeft, Plus } from "lucide-react";
import { AnimatePresence } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import { ProjectListProvider } from "./ProjectListContext";
import { ProjectsDrawer } from "./ProjectsDrawer";

export function BuilderShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <ProjectListProvider>
      <div className="flex h-dvh flex-col overflow-hidden bg-white text-slate-900">
        <header className="glass relative z-20 flex h-12 shrink-0 items-center gap-2 border-b border-slate-200/70 px-2 sm:px-3">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            aria-label="Your projects"
            title="Your projects"
          >
            <PanelLeft className="size-5" aria-hidden />
          </button>
          <Link href="/" className="group flex items-center gap-2 px-1">
            <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-[0_6px_16px_-6px_rgb(124_58_237_/_0.8)] transition group-hover:scale-105">
              <Blocks className="size-4" aria-hidden />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">AI App Builder</span>
          </Link>
          <div className="flex-1" />
          <Link
            href="/admin"
            className="hidden items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
          >
            <LayoutDashboard className="size-4" aria-hidden />
            Admin view
          </Link>
          <Link
            href="/"
            className="bg-gradient-to-br from-indigo-600 via-violet-600 to-purple-500 hover:brightness-110 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-white shadow-[0_6px_16px_-8px_rgb(79_70_229_/_0.9)] transition hover:-translate-y-px"
          >
            <Plus className="size-4" aria-hidden />
            <span className="hidden sm:inline">New project</span>
          </Link>
        </header>
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        <AnimatePresence>{open && <ProjectsDrawer onClose={() => setOpen(false)} />}</AnimatePresence>
      </div>
    </ProjectListProvider>
  );
}
