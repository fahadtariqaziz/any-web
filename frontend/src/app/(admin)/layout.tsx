import { Activity, MessageCircle, Plus } from "lucide-react";
import Link from "next/link";

// The admin view: every agent step, pause, score and verdict is visible. The patient chat lives at "/".
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-slate-50 text-slate-900">
      <header className="no-print sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link href="/admin" className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-brand text-white">
              <Activity className="size-4" aria-hidden />
            </span>
            <span className="font-semibold tracking-tight text-slate-900">Health Decision Arena</span>
            <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
              admin
            </span>
          </Link>
          <nav className="flex items-center gap-3">
            <span className="hidden text-xs text-slate-500 lg:block">Health information only, not medical advice</span>
            <Link href="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
              <MessageCircle className="size-4" aria-hidden />
              Patient chat
            </Link>
            <Link
              href="/admin"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
            >
              <Plus className="size-4" aria-hidden />
              New session
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      <footer className="no-print border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-4 text-xs leading-relaxed text-slate-500 sm:px-6">
          This tool summarises published research, clinical references and patient experiences found on the web. It is
          health information to discuss with a qualified clinician, not a diagnosis or a prescription. Never start,
          stop or change a medication based on it. If you have emergency warning signs, seek urgent care now.
        </div>
      </footer>
    </div>
  );
}
