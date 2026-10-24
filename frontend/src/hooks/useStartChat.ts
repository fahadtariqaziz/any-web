"use client";

// Start a new patient chat from a first message: create a quick session and open its page.
// Used by the "New chat" screen and by a chat whose first message wasn't about health.

import { useRouter } from "next/navigation";
import { useLayoutEffect, useState } from "react";

import { useChatList } from "@/components/chat/ChatListContext";
import { ApiError, createDecision } from "@/lib/api/client";

export function useStartChat({ replace = false }: { replace?: boolean } = {}) {
  const router = useRouter();
  const { refresh } = useChatList();
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
      const { thread_id } = await createDecision({ question: text, mode: "quick" });
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
