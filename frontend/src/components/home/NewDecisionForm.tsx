"use client";

// Problem input (requirements §10 A): question + optional context → POST /api/decisions → session page.

import { ArrowRight, ChevronDown, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { ApiError, createDecision } from "@/lib/api/client";

const MAX_CHARS = 4000; // same limits as the backend (intake.py)
const MIN_CHARS = 3;

const EXAMPLES = [
  "I have type 2 diabetes, diagnosed last year",
  "I get migraines twice a week",
  "My father was told he has high blood pressure",
  "I was diagnosed with hypothyroidism and feel tired all the time",
];

export function NewDecisionForm() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState("");
  const [showContext, setShowContext] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tooShort = question.trim().length < MIN_CHARS;

  async function submit() {
    if (tooShort || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { thread_id } = await createDecision({ question: question.trim(), context: context.trim() });
      router.push(`/decisions/${thread_id}`); // the thread_id lives in the URL: refresh-safe and shareable
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
      setSubmitting(false);
    }
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
    >
      <div className="space-y-2">
        <label htmlFor="question" className="block text-sm font-medium text-slate-800">
          Your condition or symptoms
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MAX_CHARS}
          rows={4}
          autoFocus
          placeholder="e.g. I have type 2 diabetes, diagnosed last year. I take metformin and want to lose some weight."
          className="w-full resize-y rounded-xl border border-slate-300 p-3.5 text-base text-slate-900 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
          required
        />
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
          <span>Write in your own words. Nothing you type is used to diagnose you.</span>
          <span>
            {question.length} / {MAX_CHARS}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-xs text-slate-500">
          <Sparkles className="size-3.5" aria-hidden /> Try an example
        </span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => setQuestion(ex)}
            className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-700 hover:border-brand hover:text-brand"
          >
            {ex}
          </button>
        ))}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowContext((v) => !v)}
          className="inline-flex items-center gap-1 text-sm font-medium text-slate-700 hover:text-slate-900"
          aria-expanded={showContext}
        >
          <ChevronDown className={`size-4 transition ${showContext ? "rotate-180" : ""}`} aria-hidden />
          Add context <span className="font-normal text-slate-500">(optional: diet, budget, medications, goals)</span>
        </button>
        {showContext && (
          <textarea
            id="context"
            value={context}
            onChange={(e) => setContext(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={MAX_CHARS}
            rows={2}
            placeholder="e.g. vegetarian, limited budget, already taking metformin 500 mg twice a day"
            className="mt-2 w-full resize-y rounded-xl border border-slate-300 p-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
          />
        )}
      </div>

      {error && (
        <Callout tone="danger" title="Could not start the session">
          <p>{error}</p>
        </Callout>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <p className="text-xs text-slate-500">
          Takes about 3–5 minutes. You answer a few questions first, then watch the agents work.
          <span className="hidden sm:inline"> Press ⌘/Ctrl + Enter to start.</span>
        </p>
        <Button type="submit" size="lg" loading={submitting} disabled={tooShort} icon={<ArrowRight className="size-4" aria-hidden />}>
          {submitting ? "Starting…" : "Start the research"}
        </Button>
      </div>
    </form>
  );
}
