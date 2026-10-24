"use client";

// Full-screen chat layout (ChatGPT style): a sidebar with "New chat" and the recent chats, and the
// chat area. On small screens the sidebar slides in from a menu button.

import { HeartPulse, PanelLeft } from "lucide-react";
import { Suspense, useState } from "react";

import { ChatListProvider } from "./ChatListContext";
import { ChatSidebar } from "./ChatSidebar";

export function ChatShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false); // mobile only; the desktop sidebar is always visible

  return (
    <ChatListProvider>
      <div className="flex h-dvh overflow-hidden bg-[#212121] text-neutral-100 [color-scheme:dark]">
        {/* Desktop sidebar */}
        <aside className="hidden w-[260px] shrink-0 flex-col bg-[#171717] md:flex">
          <Suspense fallback={null}>
            <ChatSidebar />
          </Suspense>
        </aside>

        {/* Mobile sidebar (overlay) */}
        {open && (
          <div className="fixed inset-0 z-40 md:hidden">
            <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
            <aside className="relative flex h-full w-[280px] flex-col bg-[#171717] shadow-xl">
              <Suspense fallback={null}>
                <ChatSidebar onNavigate={() => setOpen(false)} />
              </Suspense>
            </aside>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center gap-2 px-3">
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="rounded-lg p-2 text-neutral-400 hover:bg-white/5 hover:text-neutral-100 md:hidden"
              aria-label="Open menu"
            >
              <PanelLeft className="size-5" aria-hidden />
            </button>
            <span className="flex items-center gap-2 px-1 text-[17px] font-medium text-neutral-200">
              <HeartPulse className="size-5 text-teal-400" aria-hidden />
              Health Companion
            </span>
          </header>
          {children}
        </div>
      </div>
    </ChatListProvider>
  );
}
