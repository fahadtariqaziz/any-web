"use client";

// The empty "New chat" screen: a greeting, the message box in the middle, a few example openers.
// Sending creates a quick session (the patient chat flavour of the graph) and opens its page.

import { Activity, Brain, HeartPulse, Moon } from "lucide-react";

import { useStartChat } from "@/hooks/useStartChat";

import { Composer } from "./Composer";

const EXAMPLES = [
  { icon: Activity, text: "I have type 2 diabetes" },
  { icon: Brain, text: "I get migraines a few times a week" },
  { icon: HeartPulse, text: "I was told I have high blood pressure" },
  { icon: Moon, text: "I feel anxious and can't sleep well" },
];

export function NewChat() {
  const { start, sending, error } = useStartChat();

  return (
    <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-[12vh]">
      <div className="w-full max-w-3xl space-y-8">
        <h1 className="text-center text-[28px] font-normal tracking-tight text-neutral-100">How are you feeling today?</h1>
        <div className="space-y-2">
          <Composer
            onSend={start}
            disabled={sending}
            autoFocus
            placeholder="Tell me about your health, e.g. “I have sugar”"
          />
          {error && <p className="px-4 text-sm text-red-300">{error}</p>}
          <p className="px-4 text-center text-xs text-neutral-500">
            I&apos;ll ask a few short questions, then read what doctors, patients and research say (about 30 seconds).
          </p>
        </div>
        <ul className="mx-auto max-w-xl space-y-1">
          {EXAMPLES.map(({ icon: Icon, text }) => (
            <li key={text}>
              <button
                type="button"
                disabled={sending}
                onClick={() => start(text)}
                className="flex w-full items-center gap-4 rounded-xl px-4 py-3 text-left text-[15px] text-neutral-300 hover:bg-white/5 disabled:opacity-50"
              >
                <Icon className="size-5 text-neutral-500" aria-hidden />
                {text}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
