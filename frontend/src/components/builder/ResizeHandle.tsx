"use client";

// The draggable border between the chat and the preview (desktop only). The chat width is remembered in this browser
// (localStorage); the preview takes the rest. Double-click resets, arrow keys move it by 24 px.
//
// An iframe (the preview) swallows pointer events: the handle captures the pointer for the drag, and once the pointer
// moves a transparent cover lies over the page (resize cursor everywhere, no text selection). The cover waits for a
// real move so a double-click still reaches the handle.

import { useCallback, useState, useSyncExternalStore } from "react";

const KEY = "builder:chatWidth";
const EVENT = "builder:chatWidth"; // same-tab updates (the storage event only fires in other tabs)
export const MIN_CHAT = 320;
const MIN_PREVIEW = 420;
const MAX_CHAT = 900;
const STEP = 24;

function clamp(width: number): number {
  const max = Math.min(MAX_CHAT, window.innerWidth - MIN_PREVIEW);
  return Math.round(Math.max(MIN_CHAT, Math.min(width, max)));
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  window.addEventListener("resize", onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("resize", onChange);
  };
}

function read(): number | null {
  const raw = Number(localStorage.getItem(KEY));
  return raw > 0 ? clamp(raw) : null;
}

/** The stored chat width in px, or null = the default layout widths. null on the server (no hydration mismatch). */
export function useChatWidth(): [number | null, (width: number | null) => void] {
  const width = useSyncExternalStore(subscribe, read, () => null);
  const setWidth = useCallback((next: number | null) => {
    if (next === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(clamp(next)));
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [width, setWidth];
}

export function ResizeHandle({ width, onWidth, chatLeft }: { width: number | null; onWidth: (w: number | null) => void; chatLeft: () => number }) {
  const [dragging, setDragging] = useState(false);

  function start(e: React.PointerEvent) {
    e.preventDefault();
    // Pointer capture: the drag's events keep coming to the handle even over the preview iframe (which would
    // otherwise swallow them before the cover below appears).
    e.currentTarget.setPointerCapture(e.pointerId);
    const left = chatLeft(); // the chat's left edge: width = pointer x - left
    const startX = e.clientX;
    let moved = false; // the cover appears only once the pointer moves: a double-click must reach the handle
    const move = (ev: PointerEvent) => {
      if (!moved && Math.abs(ev.clientX - startX) < 3) return;
      if (!moved) setDragging(true);
      moved = true;
      onWidth(ev.clientX - left);
    };
    const stop = () => {
      setDragging(false);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  return (
    <>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the chat"
        aria-valuemin={MIN_CHAT}
        aria-valuenow={width ?? undefined}
        tabIndex={0}
        title="Drag to resize · double-click to reset"
        onPointerDown={start}
        onDoubleClick={() => onWidth(null)}
        onKeyDown={(e) => {
          if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
          e.preventDefault();
          const shown = (e.currentTarget.previousElementSibling as HTMLElement | null)?.offsetWidth; // the chat as drawn now
          onWidth((width ?? shown ?? MIN_CHAT) + (e.key === "ArrowRight" ? STEP : -STEP));
        }}
        className={`group relative hidden w-1.5 shrink-0 cursor-col-resize touch-none bg-slate-200 transition-colors hover:bg-brand/40 focus-visible:bg-brand/60 focus-visible:outline-none md:block ${dragging ? "bg-brand/60" : ""}`}
      >
        <span className="absolute left-1/2 top-1/2 h-8 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-400 group-hover:bg-white" aria-hidden />
      </div>
      {dragging && <div className="fixed inset-0 z-50 cursor-col-resize" aria-hidden />}
    </>
  );
}
