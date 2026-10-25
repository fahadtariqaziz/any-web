"use client";

// The projects drawer: every session, newest first, with its status. Opens from the top bar on every page.

import { X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { relativeTime, WORKFLOW_STATUS_LABEL, workflowStatusTone } from "@/lib/format";

import { projectTitle, useProjectList } from "./ProjectListContext";

export function ProjectsDrawer({ onClose }: { onClose: () => void }) {
  const pathname = usePathname();
  const { projects, error } = useProjectList();

  return (
    <div className="fixed inset-0 z-50">
      <button type="button" aria-label="Close projects" className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <nav aria-label="Projects" className="relative flex h-full w-[320px] max-w-[85vw] flex-col bg-white shadow-xl">
        <div className="flex h-12 items-center justify-between border-b border-slate-200 px-4">
          <p className="text-sm font-semibold text-slate-900">Your projects</p>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1 text-slate-500 hover:bg-slate-100">
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2 text-sm">
          {error && <li className="px-3 py-2 text-xs text-slate-500">Your projects can&apos;t be loaded right now.</li>}
          {projects && projects.length === 0 && <li className="px-3 py-2 text-xs text-slate-500">No projects yet.</li>}
          {projects?.map((p) => {
            const href = `/c/${p.thread_id}`;
            return (
              <li key={p.thread_id}>
                <Link
                  href={href}
                  onClick={onClose}
                  title={p.question}
                  className={`block rounded-lg px-3 py-2 ${pathname === href ? "bg-slate-100" : "hover:bg-slate-50"}`}
                >
                  <span className="block truncate font-medium text-slate-800">{projectTitle(p.project_name, p.question)}</span>
                  <span className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                    <Badge tone={workflowStatusTone(p.status)} size="xs">
                      {WORKFLOW_STATUS_LABEL[p.status] ?? p.status}
                    </Badge>
                    {relativeTime(p.updated_at ?? p.created_at)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
