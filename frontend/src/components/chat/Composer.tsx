"use client";

// The message box: grows with the text, Enter sends, Shift+Enter makes a new line.

import { ArrowUp } from "lucide-react";
import { useRef, useState } from "react";

type Props = {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  autoFocus?: boolean;
  extra?: React.ReactNode; // e.g. a "Skip" button next to the send button
};

export function Composer({ onSend, disabled = false, placeholder = "Message", maxLength = 4000, autoFocus = false, extra }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && text.trim().length > 0;

  function resize() {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  function send() {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
    requestAnimationFrame(resize);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
      className="flex items-end gap-2 rounded-[28px] bg-[#303030] py-2.5 pl-5 pr-2.5 shadow-[0_0_0_1px_rgba(255,255,255,0.06)]"
    >
      <textarea
        ref={ref}
        value={text}
        rows={1}
        maxLength={maxLength}
        autoFocus={autoFocus}
        placeholder={placeholder}
        aria-label={placeholder}
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
        className="max-h-[200px] min-h-[40px] flex-1 resize-none bg-transparent py-2 text-base leading-6 text-neutral-100 placeholder:text-neutral-500 focus:outline-none"
      />
      {extra}
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Send"
        className="mb-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-white text-black transition hover:bg-neutral-200 disabled:bg-neutral-600 disabled:text-neutral-400"
      >
        <ArrowUp className="size-5" aria-hidden />
      </button>
    </form>
  );
}
