"use client";

// One clarification question (2026-10-29): the question, its answer options as tappable chips (the backend's
// clarification_options), a Skip, and a hint that typing a free answer in the message box also works. Animated in;
// the chips appear one after another. Keys sent to the backend are the exact question texts (ChatPane).

import { Sparkles } from "lucide-react";
import { motion } from "motion/react";

export function QuestionCard({
  question,
  options,
  index,
  total,
  disabled = false,
  error,
  onPick,
  onSkip,
}: {
  question: string;
  options: string[];
  index: number; // 0-based
  total: number;
  disabled?: boolean;
  error?: string | null;
  onPick: (answer: string) => void;
  onSkip: () => void;
}) {
  return (
    <motion.div
      key={question}
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="gradient-border rounded-2xl p-4 shadow-[0_10px_30px_-12px_rgb(79_70_229_/_0.35)]"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-brand">
          <Sparkles className="size-3.5" aria-hidden />
          Question {index + 1} of {total}
        </span>
        <ol className="flex items-center gap-1" aria-label={`${index + 1} of ${total}`}>
          {Array.from({ length: total }, (_, i) => (
            <li
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i < index ? "w-3 bg-brand/50" : i === index ? "w-6 bg-gradient-to-r from-indigo-500 to-fuchsia-500" : "w-3 bg-slate-200"
              }`}
            />
          ))}
        </ol>
      </div>
      <p className="mt-2.5 text-[15.5px] font-medium leading-6 text-slate-900">{question}</p>
      {options.length > 0 && (
        <ul className="mt-3.5 flex flex-wrap gap-2" aria-label="Answer options">
          {options.map((option, i) => (
            <motion.li
              key={option}
              initial={{ opacity: 0, y: 6, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: 0.08 + i * 0.06, duration: 0.3, ease: "easeOut" }}
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => onPick(option)}
                className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-sm text-slate-800 shadow-sm transition duration-150 hover:-translate-y-0.5 hover:border-brand/60 hover:bg-brand-faint hover:text-brand-strong hover:shadow-md active:translate-y-0 active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {option}
              </button>
            </motion.li>
          ))}
        </ul>
      )}
      <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span>{options.length ? "Tap an option, or type your own answer below." : "Type your answer below."}</span>
        <button
          type="button"
          disabled={disabled}
          onClick={onSkip}
          className="rounded-full px-2.5 py-1 font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50"
        >
          Skip
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-amber-700">{error}</p>}
    </motion.div>
  );
}
