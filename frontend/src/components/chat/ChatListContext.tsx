"use client";

// The sidebar's list of chats, shared with the pages so they can refresh it (a new chat was created,
// a chat got its condition name after intake...).

import { createContext, useCallback, useContext, useState } from "react";

import { useFetch } from "@/hooks/useFetch";
import { listDecisions } from "@/lib/api/client";
import type { SessionList } from "@/lib/api/types";
import type { ApiError } from "@/lib/api/client";

type ChatList = {
  data: SessionList | null;
  error: ApiError | null;
  refresh: () => void;
};

const ChatListContext = createContext<ChatList | null>(null);

export function ChatListProvider({ children }: { children: React.ReactNode }) {
  const [version, setVersion] = useState(0);
  const { data, error } = useFetch(() => listDecisions(50, "quick"), `chats|${version}`);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  return <ChatListContext.Provider value={{ data, error, refresh }}>{children}</ChatListContext.Provider>;
}

export function useChatList(): ChatList {
  const value = useContext(ChatListContext);
  if (!value) throw new Error("useChatList must be used inside <ChatListProvider>");
  return value;
}
