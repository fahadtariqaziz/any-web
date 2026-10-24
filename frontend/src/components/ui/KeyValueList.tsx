import { titleCase } from "@/lib/format";

/** Profile-style facts (age: 42, medications: metformin...). */
export function KeyValueList({ items, emptyText = "Nothing recorded." }: { items: Record<string, string>; emptyText?: string }) {
  const entries = Object.entries(items);
  if (entries.length === 0) return <p className="text-sm text-slate-500">{emptyText}</p>;
  return (
    <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="font-medium text-slate-600">{titleCase(k)}</dt>
          <dd className="text-slate-900">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
