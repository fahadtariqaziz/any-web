"use client";

// The landing page's sections below the hero: the pipeline walk-through, one card per functionality with a small
// mock of its UI (pure markup, animated on scroll), and the guardrails strip. Every number here is a fact of the
// builder as it is (prompts / evals / tests counts live in docs/builder-agent-anatomy.md).

import {
  BookOpenCheck,
  CheckCircle2,
  FileText,
  Hammer,
  ListChecks,
  MessageCircleQuestion,
  MessageSquareText,
  MonitorPlay,
  Scale,
  Search,
  ShieldCheck,
  Square,
} from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

const EASE = [0.22, 1, 0.36, 1] as const;

function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-[11px] font-semibold uppercase tracking-wider text-brand">{children}</p>;
}

// --- 1. the pipeline -----------------------------------------------------------------------------------------

const STEPS: { icon: typeof Search; title: string; text: string; you?: boolean }[] = [
  { icon: MessageCircleQuestion, title: "Questions", text: "Up to five, with answer options to tap. One round, then the research starts." },
  { icon: Search, title: "Research", text: "Existing apps and their users' complaints, papers, and technical feasibility: three domains, in parallel." },
  { icon: Scale, title: "Debate", text: "Two or three solutions are proposed, criticised, and scored. The winner's claims are checked at the source." },
  { icon: FileText, title: "Brief", text: "A compact brief: problem, evidence, solution, requirements, architecture, scope, risks. Every line labelled and cited.", you: true },
  { icon: ListChecks, title: "Plan", text: "A task-by-task implementation plan with the files each task owns and the commands that verify it.", you: true },
  { icon: Hammer, title: "Build", text: "A coding agent builds one task at a time, up to three in parallel. Done means the tests passed." },
  { icon: MonitorPlay, title: "Preview", text: "The app runs next to the chat. Ask for changes; bigger ones go through the brief and the plan again." },
];

export function Pipeline() {
  return (
    <section className="relative mx-auto w-full max-w-6xl px-4 py-16">
      <Reveal className="mb-10 max-w-2xl">
        <Eyebrow>How it works</Eyebrow>
        <h2 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Seven steps, two of them yours.</h2>
        <p className="mt-3 text-slate-600">
          Nothing is planned before you approve the brief; nothing is built before you approve the plan. The rest runs on its
          own and shows you every step while it works.
        </p>
      </Reveal>
      <ol className="relative grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <motion.div
          aria-hidden
          className="absolute left-6 right-6 top-7 hidden h-px origin-left bg-gradient-to-r from-indigo-400 via-violet-400 to-fuchsia-400 lg:block"
          initial={{ scaleX: 0 }}
          whileInView={{ scaleX: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 1.2, ease: "easeOut" }}
        />
        {STEPS.map(({ icon: Icon, title, text, you }, i) => (
          <motion.li
            key={title}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.45, delay: i * 0.08, ease: EASE }}
            className="group relative rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition duration-200 hover:-translate-y-1 hover:shadow-[0_18px_40px_-20px_rgb(79_70_229_/_0.5)]"
          >
            <div className="flex items-center justify-between">
              <span className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-[0_8px_18px_-8px_rgb(124_58_237_/_0.9)] transition group-hover:scale-105">
                <Icon className="size-5" aria-hidden />
              </span>
              <span className="text-xs font-semibold text-slate-400">0{i + 1}</span>
            </div>
            <p className="mt-3 flex items-center gap-2 font-semibold text-slate-900">
              {title}
              {you && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">you approve</span>}
            </p>
            <p className="mt-1 text-sm leading-6 text-slate-600">{text}</p>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}

// --- 2. one card per functionality, with a mock of its UI ------------------------------------------------------

function Chip({ children, active = false }: { children: ReactNode; active?: boolean }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${
        active ? "border-brand/50 bg-brand-faint text-brand-strong" : "border-slate-200 bg-white text-slate-700"
      }`}
    >
      {children}
    </span>
  );
}

function Label({ tone, children }: { tone: "verified" | "research" | "you" | "rec"; children: ReactNode }) {
  const cls = {
    verified: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    research: "bg-sky-50 text-sky-700 ring-sky-200",
    you: "bg-amber-50 text-amber-800 ring-amber-200",
    rec: "bg-violet-50 text-violet-700 ring-violet-200",
  }[tone];
  return <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset ${cls}`}>{children}</span>;
}

function Bar({ value, delay }: { value: number; delay: number }) {
  return (
    <span className="block h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <motion.span
        className="block h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500"
        initial={{ width: 0 }}
        whileInView={{ width: `${value}%` }}
        viewport={{ once: true }}
        transition={{ duration: 0.9, delay, ease: "easeOut" }}
      />
    </span>
  );
}

function MockQuestions() {
  return (
    <div className="space-y-2 text-xs">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-brand">Question 2 of 5</p>
      <p className="font-medium text-slate-900">Where will people use the budgeting app?</p>
      <div className="flex flex-wrap gap-1.5">
        <Chip active>Web app in the browser</Chip>
        <Chip>iPhone and Android app</Chip>
        <Chip>Both</Chip>
      </div>
      <p className="text-[11px] text-slate-500">Tap an option, or type your own answer.</p>
    </div>
  );
}

function MockResearch() {
  const rows = [
    ["apps", "Users of app X complain that sync loses entries", "review site"],
    ["papers", "Categorisation accuracy depends on labelled history", "research paper"],
    ["tech", "Library Y caches responses for offline reading", "official docs"],
  ] as const;
  return (
    <ul className="space-y-1.5 text-xs">
      {rows.map(([domain, text, kind], i) => (
        <motion.li
          key={domain}
          initial={{ opacity: 0, x: -8 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.15 + i * 0.12, duration: 0.35 }}
          className="flex items-start gap-2 rounded-lg border border-slate-200 bg-white p-2"
        >
          <span className="mt-0.5 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">{domain}</span>
          <span className="min-w-0 flex-1 text-slate-800">{text}</span>
          <span className="shrink-0 text-[10px] text-slate-400">{kind}</span>
        </motion.li>
      ))}
    </ul>
  );
}

function MockDebate() {
  const rows = [
    ["Offline-first PWA", 78, true],
    ["Native app with sync", 64, false],
    ["Spreadsheet companion", 41, false],
  ] as const;
  return (
    <ul className="space-y-2 text-xs">
      {rows.map(([name, score, winner], i) => (
        <li key={name} className="space-y-1">
          <div className="flex items-center justify-between">
            <span className={`font-medium ${winner ? "text-slate-900" : "text-slate-600"}`}>
              {name}
              {winner && <span className="ml-1.5 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-emerald-200">winner</span>}
            </span>
            <span className="font-mono text-[11px] text-slate-500">{(score / 10).toFixed(1)}/10</span>
          </div>
          <Bar value={score} delay={0.1 + i * 0.1} />
        </li>
      ))}
    </ul>
  );
}

function MockBrief() {
  return (
    <div className="space-y-1.5 text-xs text-slate-800">
      <p className="font-semibold text-slate-900">4. Proposed solution</p>
      <p>
        An offline-first budgeting app with automatic categorisation <Label tone="research">research [2]</Label>
      </p>
      <p>
        Users lose entries when sync fails <Label tone="verified">verified [1]</Label>
      </p>
      <p>
        Mobile first, no accounts in version one <Label tone="you">you said</Label>
      </p>
      <p>
        Keep a plain export to CSV <Label tone="rec">recommended</Label>
      </p>
    </div>
  );
}

function MockBuild() {
  const tasks = [
    ["T1", "Design foundation and app shell", "done"],
    ["T2", "Expense entry and list", "done"],
    ["T3", "Categorisation rules + tests", "running"],
    ["T4", "CSV export", "pending"],
  ] as const;
  return (
    <ul className="space-y-1.5 font-mono text-[11px]">
      {tasks.map(([id, title, state], i) => (
        <motion.li
          key={id}
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 + i * 0.1 }}
          className="flex items-center gap-2 rounded-lg bg-slate-900 px-2.5 py-1.5 text-slate-200"
        >
          <span className="text-slate-500">{id}</span>
          <span className="min-w-0 flex-1 truncate">{title}</span>
          {state === "done" && <span className="text-emerald-400">exit 0 ✓</span>}
          {state === "running" && <span className="animate-pulse text-violet-300">running…</span>}
          {state === "pending" && <span className="text-slate-500">queued</span>}
        </motion.li>
      ))}
    </ul>
  );
}

function MockPreview() {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white text-xs">
      <div className="flex items-center gap-1.5 border-b border-slate-100 bg-slate-50 px-2 py-1.5">
        <span className="size-2 rounded-full bg-red-300" />
        <span className="size-2 rounded-full bg-amber-300" />
        <span className="size-2 rounded-full bg-emerald-300" />
        <span className="ml-2 flex-1 truncate rounded bg-white px-2 py-0.5 text-[10px] text-slate-400">localhost:4102</span>
        <span className="rounded-full bg-emerald-50 px-1.5 text-[10px] font-medium text-emerald-700">ready</span>
      </div>
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-slate-900">Budget</span>
          <span className="rounded-md bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-2 py-0.5 text-[10px] font-medium text-white">+ Add expense</span>
        </div>
        <div className="grid grid-cols-3 gap-1.5">
          {["Food 42%", "Rent 38%", "Fun 20%"].map((c) => (
            <span key={c} className="rounded-md border border-slate-200 px-1.5 py-1 text-center text-[10px] text-slate-600">{c}</span>
          ))}
        </div>
        <Bar value={68} delay={0.3} />
      </div>
    </div>
  );
}

function MockAsk() {
  return (
    <div className="space-y-2 text-xs">
      <div className="ml-6 rounded-2xl rounded-tr-md bg-slate-100 px-3 py-2 text-slate-800">Why did you pick an offline-first design?</div>
      <div className="mr-6 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-3 py-2 text-slate-700">
        Because two sources report entries lost during sync <Label tone="verified">kb_12</Label>, and you said mobile first. The
        alternative scored 6.4 against 7.8.
      </div>
    </div>
  );
}

const FEATURES: { icon: typeof Search; title: string; text: string; mock: ReactNode }[] = [
  { icon: MessageCircleQuestion, title: "Questions you can tap through", text: "One round, five questions at most, each with answer options. Type if you prefer. The answers shape the research.", mock: <MockQuestions /> },
  { icon: Search, title: "Research in three domains", text: "Web search runs at a fixed step; every source, link and quote comes from the search result, never from the model.", mock: <MockResearch /> },
  { icon: Scale, title: "A debate, scored in Python", text: "A proposer, a critic per proposal, a judge with a fixed rubric. The totals are computed, not guessed, and the winner's claims are checked at the source.", mock: <MockDebate /> },
  { icon: FileText, title: "A brief with labelled claims", text: "Verified, research-backed, you said, recommended or assumption: every statement says what it is, and cites its source. No appendix.", mock: <MockBrief /> },
  { icon: Hammer, title: "Built task by task, verified by tests", text: "Each task owns its files; up to three run in parallel. A task is done only when its commands exit 0. Fix tasks get a triage procedure.", mock: <MockBuild /> },
  { icon: MonitorPlay, title: "A live preview you can change", text: "The dev server runs next to the chat, checked in a real browser. Ask for a change; a bigger one updates the brief and the plan first.", mock: <MockPreview /> },
  { icon: MessageSquareText, title: "Ask anything, any time", text: "A project assistant that knows the research, the brief, the plan and the build, with a knowledge base and a research sub-agent.", mock: <MockAsk /> },
];

export function Features() {
  return (
    <section className="relative isolate bg-slate-50/70 py-16">
      <div className="bg-grid absolute inset-0 -z-10" aria-hidden />
      <div className="mx-auto w-full max-w-6xl px-4">
        <Reveal className="mb-10 max-w-2xl">
          <Eyebrow>Everything you get</Eyebrow>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Each step has its own screen.</h2>
          <p className="mt-3 text-slate-600">What you see below is how it looks in the builder: the questions, the evidence, the scores, the brief, the tasks, the preview.</p>
        </Reveal>
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text, mock }, i) => (
            <motion.li
              key={title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.5, delay: (i % 3) * 0.1, ease: EASE }}
              className="group flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-brand/40 hover:shadow-[0_24px_50px_-24px_rgb(79_70_229_/_0.55)]"
            >
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-xl bg-brand-faint text-brand transition group-hover:bg-gradient-to-br group-hover:from-indigo-500 group-hover:to-fuchsia-500 group-hover:text-white">
                  <Icon className="size-4.5" aria-hidden />
                </span>
                <h3 className="font-semibold text-slate-900">{title}</h3>
              </div>
              <p className="mt-2.5 text-sm leading-6 text-slate-600">{text}</p>
              <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50/80 p-3">{mock}</div>
            </motion.li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// --- 3. guardrails ---------------------------------------------------------------------------------------------

const GUARDRAILS: { icon: typeof Search; title: string; text: string }[] = [
  { icon: CheckCircle2, title: "Two approvals, bound to the text", text: "The brief and the plan are approved by hash. Change a word and the approval is void." },
  { icon: BookOpenCheck, title: "Facts from Python, not the model", text: "Sources, links, scores and 'did it build' come from search results and exit codes." },
  { icon: ShieldCheck, title: "A sandbox and a secret scan", text: "Generated apps run in their own folder with allowlisted commands; every build check scans the code for keys." },
  { icon: Square, title: "Stop at any time", text: "The current step finishes and is saved. Nothing later starts until you press Continue." },
];

export function Guardrails() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-16">
      <Reveal className="mb-8 max-w-2xl">
        <Eyebrow>Built on facts</Eyebrow>
        <h2 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Predictable, not just impressive.</h2>
      </Reveal>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {GUARDRAILS.map(({ icon: Icon, title, text }, i) => (
          <motion.li
            key={title}
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.45, delay: i * 0.08, ease: EASE }}
            className="gradient-border rounded-2xl p-5 shadow-sm"
          >
            <Icon className="size-5 text-brand" aria-hidden />
            <p className="mt-3 font-semibold text-slate-900">{title}</p>
            <p className="mt-1 text-sm leading-6 text-slate-600">{text}</p>
          </motion.li>
        ))}
      </ul>
    </section>
  );
}
