"use client";

import { LayoutDashboard, SquarePen } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useChatList } from "./ChatListContext";

export function ChatSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data, error } = useChatList();
  const chats = data?.sessions ?? [];

  return (
    <nav className="flex h-full flex-col gap-1 p-2 text-sm" aria-label="Chats">
      <Link
        href="/"
        onClick={onNavigate}
        className="flex items-center gap-3 rounded-lg px-3 py-2.5 font-medium text-neutral-100 hover:bg-white/5"
      >
        <SquarePen className="size-[18px]" aria-hidden />
        New chat
      </Link>

      <p className="mt-5 px-3 pb-1 text-xs font-medium text-neutral-500">Recents</p>
      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {error && <li className="px-3 py-2 text-xs text-neutral-500">Your chats can&apos;t be loaded right now.</li>}
        {data && chats.length === 0 && <li className="px-3 py-2 text-xs text-neutral-500">No chats yet.</li>}
        {chats.map((chat) => {
          const href = `/c/${chat.thread_id}`;
          const active = pathname === href;
          return (
            <li key={chat.thread_id}>
              <Link
                href={href}
                onClick={onNavigate}
                title={chat.question}
                className={`block truncate rounded-lg px-3 py-2 ${active ? "bg-white/10 text-neutral-100" : "text-neutral-300 hover:bg-white/5"}`}
              >
                {titleOf(chat.condition_name, chat.question)}
              </Link>
            </li>
          );
        })}
      </ul>

      <Link
        href="/admin"
        className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-neutral-400 hover:bg-white/5 hover:text-neutral-200"
      >
        <LayoutDashboard className="size-4" aria-hidden />
        Admin view
      </Link>
    </nav>
  );
}

/** "type 2 diabetes" → "Type 2 diabetes"; falls back to the first message. */
function titleOf(condition: string | null, question: string): string {
  const text = condition && condition !== "unspecified condition" ? condition : question;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
