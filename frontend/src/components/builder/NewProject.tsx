"use client";

// The home screen: "What do you want to build?", the message box, a few example ideas, and the recent projects.
// Sending creates a session (the full pipeline) and opens its builder page.

import { Bot, Calculator, ListChecks, Store } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { relativeTime, WORKFLOW_STATUS_LABEL, workflowStatusTone } from "@/lib/format";

import { Composer } from "./Composer";
import { projectTitle, useProjectList } from "./ProjectListContext";
import { useStartProject } from "./useStartProject";

const EXAMPLES = [
  { icon: Calculator, text: "A simple calculator web app" },
  { icon: Store, text: "A website for my bakery with online pre-orders for pickup" },
  { icon: ListChecks, text: "A habit tracker app for university students" },
  { icon: Bot, text: "A chatbot that answers questions about my product docs" },
];

export function NewProject() {
  const { start, sending, error } = useStartProject();
  const { projects } = useProjectList();
  const recent = (projects ?? []).slice(0, 6);

  return (
    <div className="flex-1 overflow-y-auto bg-gradient-to-b from-brand-faint to-white">
      <div className="mx-auto w-full max-w-3xl space-y-8 px-4 pb-16 pt-[12vh]">
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">What do you want to build?</h1>
          <p className="text-slate-600">
            Describe an app or website. I ask a few questions, research it, write a brief for your approval, plan it, build it and show
            it running.
          </p>
        </div>
        <div className="space-y-2">
          <Composer onSend={start} disabled={sending} autoFocus size="lg" placeholder="Describe the app or website you want to build" />
          {error && <p className="px-2 text-sm text-red-600">{error}</p>}
        </div>
        <ul className="flex flex-wrap justify-center gap-2">
          {EXAMPLES.map(({ icon: Icon, text }) => (
            <li key={text}>
              <button
                type="button"
                disabled={sending}
                onClick={() => start(text)}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-sm text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
              >
                <Icon className="size-4 text-slate-400" aria-hidden />
                {text}
              </button>
            </li>
          ))}
        </ul>

        {recent.length > 0 && (
          <section className="space-y-3 pt-6">
            <h2 className="text-sm font-semibold text-slate-700">Recent projects</h2>
            <ul className="grid gap-3 sm:grid-cols-2">
              {recent.map((p) => (
                <li key={p.thread_id}>
                  <Link
                    href={`/c/${p.thread_id}`}
                    title={p.question}
                    className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:shadow"
                  >
                    <p className="truncate font-medium text-slate-900">{projectTitle(p.project_name, p.question)}</p>
                    <p className="mt-0.5 truncate text-sm text-slate-500">{p.question}</p>
                    <p className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                      <Badge tone={workflowStatusTone(p.status)} size="xs">
                        {WORKFLOW_STATUS_LABEL[p.status] ?? p.status}
                      </Badge>
                      {relativeTime(p.updated_at ?? p.created_at)}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
