"use client";

// A list of strings kept in localStorage under `key`, so it survives a page reload (used for onboarding
// answers typed before the last question: the backend only receives them all at once).
// useSyncExternalStore reads localStorage during render without an effect; the server render sees [].

import { useCallback, useMemo, useSyncExternalStore } from "react";

const CHANGE_EVENT = "stored-list-change"; // "storage" only fires in OTHER tabs, so we announce our own writes

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

export function useStoredList(key: string | null) {
  const raw = useSyncExternalStore(
    subscribe,
    () => (key ? localStorage.getItem(key) : null),
    () => null,
  );
  const list = useMemo<string[]>(() => {
    try {
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }, [raw]);

  const setList = useCallback(
    (next: string[] | null) => {
      if (!key) return;
      if (next) localStorage.setItem(key, JSON.stringify(next));
      else localStorage.removeItem(key);
      window.dispatchEvent(new Event(CHANGE_EVENT));
    },
    [key],
  );

  return [list, setList] as const;
}
