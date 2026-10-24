import { AlertTriangle, CheckCircle2, Info, OctagonAlert } from "lucide-react";
import type { ReactNode } from "react";

type Tone = "info" | "warning" | "danger" | "success";

const STYLE: Record<Tone, { box: string; icon: ReactNode }> = {
  info: { box: "border-sky-200 bg-sky-50 text-sky-900", icon: <Info className="size-5 text-sky-600" /> },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-900", icon: <AlertTriangle className="size-5 text-amber-600" /> },
  danger: { box: "border-red-200 bg-red-50 text-red-900", icon: <OctagonAlert className="size-5 text-red-600" /> },
  success: { box: "border-emerald-200 bg-emerald-50 text-emerald-900", icon: <CheckCircle2 className="size-5 text-emerald-600" /> },
};

export function Callout({
  tone = "info",
  title,
  children,
  className = "",
  role,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  role?: string;
}) {
  return (
    <div role={role ?? (tone === "danger" ? "alert" : undefined)} className={`flex gap-3 rounded-xl border p-4 text-sm ${STYLE[tone].box} ${className}`}>
      <span className="mt-0.5 shrink-0">{STYLE[tone].icon}</span>
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="space-y-1">{children}</div>}
      </div>
    </div>
  );
}
