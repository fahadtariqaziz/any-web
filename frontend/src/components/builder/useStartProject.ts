"use client";

// Start a new project from a first message: create a session (the full pipeline, like the admin view) and open
// its builder page. Used by the home screen and by a project whose first message wasn't an app idea.

import { useRouter } from "next/navigation";
import { useLayoutEffect, useState } from "react";

import { ApiError, createDecision } from "@/lib/api/client";

import { useProjectList } from "./ProjectListContext";

export function useStartProject({ replace = false }: { replace?: boolean } = {}) {
  const router = useRouter();
  const { refresh } = useProjectList();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Next keeps a visited page alive (hidden) after we navigate away. Reset when it's hidden, so coming
  // back shows a usable screen instead of the disabled "sending" state.
  useLayoutEffect(() => {
    return () => {
      setSending(false);
      setError(null);
    };
  }, []);

  async function start(text: string) {
    if (sending) return;
    setSending(true);
    setError(null);
    try {
      const { thread_id } = await createDecision({ question: text, mode: "full" });
      refresh();
      if (replace) router.replace(`/c/${thread_id}`);
      else router.push(`/c/${thread_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setSending(false);
    }
  }

  return { start, sending, error };
}
