"use client";

// The pieces of the builder conversation: the user's bubbles, the assistant's text (markdown, no bubble), short
// assistant notes ("Draft 2 of your brief is ready") and the research summary.

import { CircleCheck, Lightbulb, Sparkles } from "lucide-react";
import { motion } from "motion/react";

import { Markdown } from "@/components/ui/Markdown";
import type { OnboardingSummary } from "@/lib/api/types";

export function UserBubble({ children, muted = false, tag }: { children: React.ReactNode; muted?: boolean; tag?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="flex flex-col items-end gap-1"
    >
      {tag && <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{tag}</span>}
      <div
        className={`max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-md px-4 py-2 text-[15px] leading-6 shadow-sm ${
          muted ? "bg-slate-100 italic text-slate-500" : "bg-gradient-to-br from-indigo-50 to-violet-50 text-slate-900 ring-1 ring-indigo-100"
        }`}
      >
        {children}
      </div>
    </motion.div>
  );
}

/** Assistant text: no bubble, full column width, markdown rendered. */
export function AssistantMessage({ text }: { text: string }) {
  return <Markdown compact className="text-slate-800 [&_p]:leading-6">{text}</Markdown>;
}

/** A one-line event from the builder ("Draft 2 of your brief is ready"), with an icon. */
export function AssistantNote({ icon, children, tone = "slate" }: { icon: React.ReactNode; children: React.ReactNode; tone?: "slate" | "emerald" | "red" | "amber" }) {
  const color = { slate: "text-slate-600", emerald: "text-emerald-700", red: "text-red-700", amber: "text-amber-700" }[tone];
  return <div className={`flex items-start gap-2 text-sm ${color}`}><span className="mt-0.5 shrink-0">{icon}</span><div className="min-w-0">{children}</div></div>;
}

/** Highlighted note above the clarification questions. */
export function OnboardingBanner({ done }: { done: boolean }) {
  if (done) {
    return (
      <div className="flex items-center gap-2 text-sm text-emerald-700">
        <CircleCheck className="size-4" aria-hidden />I researched your idea
      </div>
    );
  }
  return (
    <div className="flex gap-3 rounded-2xl border border-indigo-100 bg-gradient-to-br from-brand-faint to-violet-50/60 px-4 py-3">
      <Lightbulb className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />
      <div className="text-sm leading-6">
        <p className="font-medium text-indigo-950">Understanding your idea</p>
        <p className="text-indigo-950/70">
          A few quick questions first, so the research and the proposals fit what you want. Tap an option or type; skip any you are unsure about.
        </p>
      </div>
    </div>
  );
}

/** The short message that ends the research phase: overview, the recommended solution, next steps. */
export function SummaryMessage({ summary }: { summary: OnboardingSummary }) {
  return (
    <div className="space-y-3 text-[15px] leading-6 text-slate-800">
      <p>{summary.opening}</p>
      {summary.details && (
        <div>
          <p className="mb-0.5 flex items-center gap-2 text-sm font-semibold text-slate-600">
            <Sparkles className="size-4 text-brand" aria-hidden />
            What the research and the debate found
          </p>
          <Markdown compact className="text-slate-700 [&_p]:leading-6">{summary.details}</Markdown>
        </div>
      )}
      <p>{summary.invitation}</p>
    </div>
  );
}
