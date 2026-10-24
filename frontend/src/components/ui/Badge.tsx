import type { ReactNode } from "react";

import type { Tone } from "@/lib/format";

const TONE: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
  slate: "bg-slate-100 text-slate-600 ring-slate-200",
  brand: "bg-brand-soft text-brand-strong ring-teal-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  orange: "bg-orange-50 text-orange-800 ring-orange-200",
  emerald: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  sky: "bg-sky-50 text-sky-700 ring-sky-200",
};

const DOT: Record<Tone, string> = {
  neutral: "bg-slate-400",
  slate: "bg-slate-400",
  brand: "bg-brand",
  amber: "bg-amber-500",
  orange: "bg-orange-500",
  emerald: "bg-emerald-500",
  red: "bg-red-500",
  violet: "bg-violet-500",
  sky: "bg-sky-500",
};

export function Badge({
  tone = "neutral",
  dot = false,
  pulse = false,
  size = "sm",
  className = "",
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  size?: "xs" | "sm" | "md";
  className?: string;
  children: ReactNode;
}) {
  const pad = size === "xs" ? "px-1.5 py-0 text-[11px]" : size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-medium ring-1 ring-inset ${TONE[tone]} ${pad} ${className}`}>
      {dot && (
        <span className="relative flex size-1.5">
          {pulse && <span className={`absolute inline-flex size-full animate-ping rounded-full opacity-75 ${DOT[tone]}`} />}
          <span className={`relative inline-flex size-1.5 rounded-full ${DOT[tone]}`} />
        </span>
      )}
      {children}
    </span>
  );
}
