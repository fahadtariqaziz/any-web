"use client";

import type { ReactNode } from "react";

export interface TabItem<K extends string> {
  key: K;
  label: ReactNode;
  count?: number | null;
  disabled?: boolean;
}

/** A controlled, accessible tab list. The parent owns the selected key and renders the panel. */
export function Tabs<K extends string>({
  items,
  value,
  onChange,
  size = "md",
  className = "",
}: {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <div role="tablist" className={`flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1 ${className}`}>
      {items.map((item) => {
        const selected = item.key === value;
        return (
          <button
            key={item.key}
            role="tab"
            type="button"
            aria-selected={selected}
            disabled={item.disabled}
            onClick={() => onChange(item.key)}
            className={`inline-flex items-center gap-1.5 rounded-md font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
              size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm"
            } ${selected ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
          >
            {item.label}
            {item.count != null && (
              <span className={`rounded-full px-1.5 text-[11px] ${selected ? "bg-slate-100 text-slate-700" : "bg-slate-200/70 text-slate-600"}`}>
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
