"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";

import { ChatView } from "@/components/chat/ChatView";

// The chat id is only known at request time, so the part that reads it sits inside <Suspense>
// (cacheComponents rule, same as /decisions/[threadId]). key={threadId}: switching chats starts fresh.
function ChatFromUrl() {
  const { threadId } = useParams<{ threadId: string }>();
  return <ChatView key={threadId} threadId={threadId} />;
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatFromUrl />
    </Suspense>
  );
}
