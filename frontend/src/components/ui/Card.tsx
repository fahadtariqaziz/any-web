import type { HTMLAttributes, ReactNode } from "react";

export function Card({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`} {...rest}>
      {children}
    </div>
  );
}

/** Eyebrow (small caps) + title + optional right-side content. */
export function CardHeader({
  eyebrow,
  title,
  description,
  aside,
  className = "",
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4 ${className}`}>
      <div className="min-w-0 space-y-0.5">
        {eyebrow && <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{eyebrow}</p>}
        <h2 className="text-base font-semibold leading-tight text-slate-900">{title}</h2>
        {description && <p className="text-sm text-slate-600">{description}</p>}
      </div>
      {aside && <div className="flex shrink-0 items-center gap-2">{aside}</div>}
    </div>
  );
}

export function CardBody({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`px-5 py-4 ${className}`}>{children}</div>;
}
