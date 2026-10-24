"use client";

// Renders agent-written text (summaries, explanations, report sections). The agents sometimes use
// markdown (lists, bold, links), so we render it instead of showing raw asterisks. GitHub-flavoured
// markdown adds tables, strikethrough and task lists. Links open in a new tab.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = { children: string; className?: string; compact?: boolean; dark?: boolean };

export function Markdown({ children, className = "", compact = false, dark = false }: Props) {
  if (!children) return null;
  return (
    <div className={`prose max-w-none ${dark ? "prose-invert" : "prose-slate"} ${compact ? "prose-sm prose-p:my-1 prose-ul:my-1 prose-li:my-0" : "prose-sm sm:prose-base"} ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className={`${dark ? "text-teal-300" : "text-brand"} underline-offset-2`}>
              {children}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
