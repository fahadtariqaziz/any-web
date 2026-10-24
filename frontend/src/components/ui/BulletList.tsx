import { Markdown } from "./Markdown";

/** A list of short agent-written items (benefits, risks, next steps...). Markdown inside each item is rendered. */
export function BulletList({
  items,
  emptyText,
  numbered = false,
  className = "",
}: {
  items: string[];
  emptyText?: string;
  numbered?: boolean;
  className?: string;
}) {
  if (items.length === 0) return emptyText ? <p className="text-sm text-slate-500">{emptyText}</p> : null;
  const Tag = numbered ? "ol" : "ul";
  return (
    <Tag className={`space-y-1.5 text-sm text-slate-800 ${numbered ? "list-decimal" : "list-disc"} pl-5 ${className}`}>
      {items.map((item, i) => (
        <li key={i} className="marker:text-slate-400">
          <Markdown compact>{item}</Markdown>
        </li>
      ))}
    </Tag>
  );
}
