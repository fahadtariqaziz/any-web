import { ChatShell } from "@/components/chat/ChatShell";

// The patient chat (ChatGPT style, full screen). The admin view with every agent step is at /admin.
export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <ChatShell>{children}</ChatShell>;
}
