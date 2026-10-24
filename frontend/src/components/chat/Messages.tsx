"use client";

import { BookOpen, CircleCheck, HeartPulse, Stethoscope, Users } from "lucide-react";

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

/** Highlighted note above the onboarding questions. */
export function OnboardingBanner({ done }: { done: boolean }) {
  if (done) {
    return (
      <div className="flex items-center gap-2 text-sm text-emerald-300/90">
        <CircleCheck className="size-4" aria-hidden />I got to know your health situation
      </div>
    );
  }
  return (
    <div className="flex gap-3 rounded-2xl border border-teal-400/25 bg-teal-400/10 px-4 py-3">
      <HeartPulse className="mt-0.5 size-5 shrink-0 text-teal-300" aria-hidden />
      <div className="text-sm leading-6">
        <p className="font-medium text-teal-100">Getting to know your health situation</p>
        <p className="text-teal-100/70">
          A few short questions first, so everything I say fits you. Skip any you&apos;d rather not answer.
        </p>
      </div>
    </div>
  );
}

const SECTIONS = [
  { key: "doctors_say", label: "What doctors say", icon: Stethoscope },
  { key: "patients_say", label: "What other patients say", icon: Users },
  { key: "research_says", label: "What research says", icon: BookOpen },
] as const;

/** The short message that ends onboarding. */
export function SummaryMessage({ summary }: { summary: OnboardingSummary }) {
  return (
    <div className="space-y-4 text-base leading-7 text-neutral-100">
      <p>{summary.opening}</p>
      {SECTIONS.map(({ key, label, icon: Icon }) =>
        summary[key] ? (
          <div key={key}>
            <p className="mb-0.5 flex items-center gap-2 text-sm font-semibold text-neutral-300">
              <Icon className="size-4 text-teal-300" aria-hidden />
              {label}
            </p>
            <Markdown dark className="text-neutral-200 [&_p]:leading-7">{summary[key]}</Markdown>
          </div>
        ) : null,
      )}
      <p>{summary.invitation}</p>
    </div>
  );
}
