"use client";

// The landing page (2026-10-29 redesign): a hero with the idea composer, an animated walk-through of the pipeline,
// one card per functionality with a small live-looking mock of its UI, the guardrails, and the recent projects.
// Sending creates a session (the full pipeline) and opens its builder page.

import { ArrowDown, Bot, Calculator, ListChecks, ShieldCheck, Sparkles, Store } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRef } from "react";

import { Composer } from "@/components/builder/Composer";
import { projectTitle, useProjectList } from "@/components/builder/ProjectListContext";
import { useStartProject } from "@/components/builder/useStartProject";
import { Badge } from "@/components/ui/Badge";
import { relativeTime, WORKFLOW_STATUS_LABEL, workflowStatusTone } from "@/lib/format";

import { Features, Guardrails, Pipeline } from "./Sections";

const EXAMPLES = [
  { icon: Calculator, text: "A simple calculator web app" },
  { icon: Store, text: "A website for my bakery with online pre-orders for pickup" },
  { icon: ListChecks, text: "A habit tracker app for university students" },
  { icon: Bot, text: "A chatbot that answers questions about my product docs" },
];

const EASE = [0.22, 1, 0.36, 1] as const;

export function Landing() {
  const { start, sending, error } = useStartProject();
  const { projects } = useProjectList();
  const recent = (projects ?? []).slice(0, 6);
  const top = useRef<HTMLDivElement>(null);

  return (
    <div className="scroll-thin relative flex-1 overflow-y-auto bg-white">
      {/* ------------------------------------------------------------------ hero ------------------------------ */}
      <section ref={top} className="relative isolate overflow-hidden">

        <div className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 sm:pt-8">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EASE }}
            className="space-y-5 text-center"
          >
            <span className="glass inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium text-slate-700">
              Research-backed app building · you approve the brief and the plan
            </span>
            <h1 className="text-balance text-4xl font-semibold tracking-tight text-slate-900 sm:text-6xl">
              Describe it. <span className="gradient-text whitespace-nowrap">Approve it.</span> Watch it run.
            </h1>
            <p className="mx-auto max-w-2xl text-pretty text-base leading-7 text-slate-600 sm:text-lg">
              Tell the builder what you want. It asks up to five quick questions, researches existing apps, papers and
              feasibility, debates two or three solutions, writes a brief you approve, plans the build you approve,
              codes it task by task with real tests, and shows it live next to the chat.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 18, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.15, ease: EASE }}
            className="mt-8 space-y-3"
          >
            <div className="glass rounded-3xl p-2">
              <Composer onSend={start} disabled={sending} autoFocus size="lg" placeholder="Describe the app or website you want to build" />
            </div>
            {error && <p className="px-2 text-center text-sm text-red-600">{error}</p>}
            <ul className="flex flex-wrap justify-center gap-2">
              {EXAMPLES.map(({ icon: Icon, text }, i) => (
                <motion.li
                  key={text}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 + i * 0.07, duration: 0.35, ease: EASE }}
                >
                  <button
                    type="button"
                    disabled={sending}
                    onClick={() => start(text)}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-3.5 py-1.5 text-sm text-slate-700 shadow-sm backdrop-blur transition duration-150 hover:-translate-y-0.5 hover:border-brand/50 hover:text-brand-strong hover:shadow-md active:scale-95 disabled:opacity-50"
                  >
                    <Icon className="size-4 text-violet-500" aria-hidden />
                    {text}
                  </button>
                </motion.li>
              ))}
            </ul>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8, duration: 0.6 }}
            className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-slate-500"
          >
            <span className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-emerald-500" aria-hidden /> Two approvals before any code</span>
            <span>·</span>
            <span>Every claim cited to its source</span>
            <span>·</span>
            <span>Done means the tests passed</span>
            <span>·</span>
            <span>Stop at any time, nothing lost</span>
          </motion.div>
          <div className="mt-8 flex justify-center text-slate-400">
            <ArrowDown className="size-4 animate-bounce" aria-hidden />
          </div>
        </div>
      </section>

      <Pipeline />
      <Features />
      <Guardrails />

      {/* ------------------------------------------------------------------ recent projects --------------------- */}
      {recent.length > 0 && (
        <section className="mx-auto w-full max-w-5xl px-4 py-14">
          <div className="mb-5 flex items-end justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-brand">Your projects</p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">Pick up where you left off</h2>
            </div>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {recent.map((p, i) => (
              <motion.li
                key={p.thread_id}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: i * 0.05, duration: 0.4, ease: EASE }}
              >
                <Link
                  href={`/c/${p.thread_id}`}
                  title={p.question}
                  className="group block rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-brand/40 hover:shadow-[0_18px_40px_-20px_rgb(79_70_229_/_0.5)]"
                >
                  <p className="truncate font-medium text-slate-900 group-hover:text-brand-strong">{projectTitle(p.project_name, p.question)}</p>
                  <p className="mt-0.5 truncate text-sm text-slate-500">{p.question}</p>
                  <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                    <Badge tone={workflowStatusTone(p.status)} size="xs">
                      {WORKFLOW_STATUS_LABEL[p.status] ?? p.status}
                    </Badge>
                    {relativeTime(p.updated_at ?? p.created_at)}
                  </p>
                </Link>
              </motion.li>
            ))}
          </ul>
        </section>
      )}

      {/* ------------------------------------------------------------------ closing CTA ------------------------- */}
      <section className="relative isolate overflow-hidden px-4 py-20">
        <div className="absolute inset-x-0 top-0 -z-10 h-px bg-gradient-to-r from-transparent via-indigo-300 to-transparent" aria-hidden />
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: EASE }}
          className="relative z-10 mx-auto max-w-2xl text-center"
        >
          <h2 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Ready when you are.</h2>
          <p className="mt-3 text-slate-600">One sentence is enough to start. The questions, the research and the brief do the rest.</p>
          <button
            type="button"
            onClick={() => top.current?.scrollIntoView({ behavior: "smooth" })}
            className="bg-gradient-to-br from-indigo-600 via-violet-600 to-purple-500 hover:brightness-110 mt-6 inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white shadow-[0_12px_28px_-10px_rgb(79_70_229_/_0.9)] transition hover:-translate-y-0.5 active:scale-95"
          >
            <Sparkles className="size-4" aria-hidden />
            Describe your idea
          </button>
        </motion.div>
      </section>
    </div>
  );
}
