"use client";

// The message box: grows with the text, Enter sends, Shift+Enter makes a new line. `modes` adds a small switch
// above the text (e.g. "Request some change in app" / "Ask about app"); the parent owns the selected mode. If onSend returns
// (or resolves to) false, the text comes back into the box so nothing typed is lost.

import { ArrowUp } from "lucide-react";
import { useRef, useState } from "react";

export type ComposerMode<K extends string> = { key: K; label: string; placeholder: string; hint?: string }; // hint: tooltip

type Props<K extends string> = {
  onSend: (text: string) => void | boolean | Promise<void | boolean>;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  autoFocus?: boolean;
  extra?: React.ReactNode; // e.g. a "Skip" button next to the send button
  modes?: ComposerMode<K>[];
  mode?: K;
  onModeChange?: (mode: K) => void;
  size?: "md" | "lg";
};

export function Composer<K extends string>({
  onSend,
  disabled = false,
  placeholder = "Message",
  maxLength = 4000,
  autoFocus = false,
  extra,
  modes,
  mode,
  onModeChange,
  size = "md",
}: Props<K>) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && text.trim().length > 0;
  const current = modes?.find((m) => m.key === mode);
  const hint = current?.placeholder ?? placeholder;

  function resize() {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  async function send() {
    if (!canSend) return;
    const sent = text.trim();
    setText("");
    requestAnimationFrame(resize);
    if ((await onSend(sent)) === false) {
      setText(sent);
      requestAnimationFrame(resize);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
      className="rounded-2xl border border-slate-300 bg-white shadow-sm focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20"
    >
      {modes && modes.length > 1 && (
        <div role="radiogroup" aria-label="What this message does" className="flex flex-wrap gap-1 px-3 pt-2.5">
          {modes.map((m) => (
            <button
              key={m.key}
              type="button"
              role="radio"
              aria-checked={m.key === mode}
              title={m.hint}
              onClick={() => onModeChange?.(m.key)}
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition ${
                m.key === mode ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 py-2 pl-4 pr-2">
        <textarea
          ref={ref}
          value={text}
          rows={size === "lg" ? 2 : 1}
          maxLength={maxLength}
          autoFocus={autoFocus}
          disabled={disabled}
          placeholder={hint}
          aria-label={hint}
          onChange={(e) => {
            setText(e.target.value);
            resize();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send();
            }
          }}
          className={`max-h-[200px] flex-1 resize-none bg-transparent py-1.5 leading-6 text-slate-900 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed ${
            size === "lg" ? "min-h-[56px] text-base" : "min-h-[36px] text-[15px]"
          }`}
        />
        {extra}
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Send"
          className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white transition hover:bg-slate-700 disabled:bg-slate-200 disabled:text-slate-400"
        >
          <ArrowUp className="size-4" aria-hidden />
        </button>
      </div>
    </form>
  );
}
