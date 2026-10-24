"use client";

import { CircleCheck, Lightbulb, Sparkles } from "lucide-react";

import { Markdown } from "@/components/ui/Markdown";
import type { OnboardingSummary } from "@/lib/api/types";

export function UserBubble({ children, muted = false }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <div className="flex justify-end">
      <div
        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-3xl bg-[#303030] px-5 py-2.5 text-base leading-7 ${muted ? "italic text-neutral-400" : "text-neutral-100"}`}
      >
        {children}
      </div>
    </div>
  );
}

/** Assistant text: no bubble, full column width, markdown rendered (like ChatGPT). */
export function AssistantMessage({ text }: { text: string }) {
  return <Markdown dark className="text-neutral-100 [&_p]:leading-7">{text}</Markdown>;
}

/** Highlighted note above the clarification questions. */
export function OnboardingBanner({ done }: { done: boolean }) {
  if (done) {
    return (
      <div className="flex items-center gap-2 text-sm text-emerald-300/90">
        <CircleCheck className="size-4" aria-hidden />I researched your idea
      </div>
    );
  }
  return (
    <div className="flex gap-3 rounded-2xl border border-teal-400/25 bg-teal-400/10 px-4 py-3">
      <Lightbulb className="mt-0.5 size-5 shrink-0 text-teal-300" aria-hidden />
      <div className="text-sm leading-6">
        <p className="font-medium text-teal-100">Understanding your idea</p>
        <p className="text-teal-100/70">
          A few short questions first, so the research and the proposals fit what you want. Skip any you are unsure about.
        </p>
      </div>
    </div>
  );
}

/** The short message that ends the research phase: overview, the recommended solution, next steps. */
export function SummaryMessage({ summary }: { summary: OnboardingSummary }) {
  return (
    <div className="space-y-4 text-base leading-7 text-neutral-100">
      <p>{summary.opening}</p>
      {summary.details && (
        <div>
          <p className="mb-0.5 flex items-center gap-2 text-sm font-semibold text-neutral-300">
            <Sparkles className="size-4 text-teal-300" aria-hidden />
            What the research and the debate found
          </p>
          <Markdown dark className="text-neutral-200 [&_p]:leading-7">{summary.details}</Markdown>
        </div>
      )}
      <p>{summary.invitation}</p>
    </div>
  );
}
