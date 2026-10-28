import { BookOpenCheck, FileText, MessageCircleQuestion, Scale, Search, ShieldCheck } from "lucide-react";

const STEPS = [
  {
    icon: MessageCircleQuestion,
    title: "You answer a few questions",
    text: "One round of up to five questions that change the solution, each with answer options to tap (or type your own): who the users are, the goal, must-have features, platform, the one constraint that matters. Skipping is fine; the agents state their assumptions.",
  },
  {
    icon: Search,
    title: "Three domains of research",
    text: "Existing apps and their users' feedback, research papers and technical literature, and technical feasibility are searched separately. Every kept source becomes a short, cited evidence record; rejected sources get a stated reason.",
  },
  {
    icon: Scale,
    title: "Solutions are proposed, challenged and scored",
    text: "A Proposer designs 2–3 different solutions from all the evidence. A Critic challenges each one. A Judge scores them on requirements alignment, problem relevance, evidence quality, feasibility and completeness.",
  },
  {
    icon: BookOpenCheck,
    title: "Claims are verified at the source",
    text: "The winning proposal's claims are re-checked against the exact sources they cite and marked verified, partly supported, unsupported or contradicted.",
  },
  {
    icon: FileText,
    title: "A summary you can act on",
    text: "The recommended solution, the alternatives, why it won, what remains uncertain, and what to decide before planning the build.",
  },
];

export function HowItWorks() {
  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight text-slate-900">How it works</h2>
        <p className="text-sm text-slate-600">Every step is visible while it runs, and every claim links back to its source.</p>
      </div>
      <ol className="grid gap-3 sm:grid-cols-2">
        {STEPS.map((step, i) => (
          <li key={step.title} className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-faint text-brand">
              <step.icon className="size-4.5" aria-hidden />
            </span>
            <div className="space-y-1">
              <p className="text-sm font-semibold text-slate-900">
                <span className="mr-1.5 text-slate-400">{i + 1}.</span>
                {step.title}
              </p>
              <p className="text-sm leading-relaxed text-slate-600">{step.text}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="flex gap-3 rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-900">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-indigo-700" aria-hidden />
        <p>
          <span className="font-semibold">Nothing is invented.</span> Every source URL comes from a real search result, cited
          ids are checked by code, and claims are labelled by how well their sources support them. Gaps and assumptions
          are listed, not hidden.
        </p>
      </div>
    </section>
  );
}
