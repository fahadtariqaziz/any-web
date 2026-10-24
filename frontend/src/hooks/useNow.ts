"use client";

// A clock that ticks once a second while `active` is true, so elapsed-time displays keep moving
// between polls (the user never looks at a frozen number while agents work).

import { useEffect, useState } from "react";

export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const first = setTimeout(() => setNow(Date.now()), 0); // catch up at once when activity starts
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [active, intervalMs]);
  return now;
}
