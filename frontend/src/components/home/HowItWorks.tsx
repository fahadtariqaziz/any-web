import { BookOpenCheck, FileText, MessageCircleQuestion, Scale, Search, ShieldCheck } from "lucide-react";

const STEPS = [
  {
    icon: MessageCircleQuestion,
    title: "You answer a few questions",
    text: "The clarification agent asks 5–6 questions that change the research: confirmed type, duration, symptoms, treatments, other conditions, routine and goals. Skipping is fine; the agents state their assumptions.",
  },
  {
    icon: Search,
    title: "Three lanes of research",
    text: "Research papers, clinical guidance and patient communities are searched separately. Every kept source becomes a short, cited evidence record. Sources are rejected with a stated reason.",
  },
  {
    icon: Scale,
    title: "Plans are proposed, challenged and scored",
    text: "Each lane proposes 2–3 care plans from its own evidence. A Critic challenges every plan against all evidence. A Judge scores them on fit, safety, evidence, practicality and completeness.",
  },
  {
    icon: BookOpenCheck,
    title: "Claims are verified at the source",
    text: "The winning plans' claims are re-checked against the exact sources they cite and marked verified, partly supported, unsupported or contradicted.",
  },
  {
    icon: FileText,
    title: "A report to bring to your doctor",
    text: "One best plan per perspective, where they agree and differ, what remains uncertain, and the questions to ask next.",
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
      <div className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-red-600" aria-hidden />
        <p>
          <span className="font-semibold">Safety first.</span> If your message or answers mention emergency warning signs,
          the agents pause and ask you whether to continue. The tool never diagnoses, never invents doses and never
          advises stopping a medication.
        </p>
      </div>
    </section>
  );
}
