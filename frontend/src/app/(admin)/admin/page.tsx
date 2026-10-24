import { HowItWorks } from "@/components/home/HowItWorks";
import { NewDecisionForm } from "@/components/home/NewDecisionForm";
import { RecentSessions } from "@/components/home/RecentSessions";

// Server Component: static text rendered on the server; the interactive parts are Client Components.
export default function Home() {
  return (
    <div className="space-y-10">
      <section className="mx-auto max-w-3xl space-y-4 text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand">Three domains, one honest brief</p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
          Turn an app idea into a researched, honest plan
        </h1>
        <p className="text-base text-slate-600 sm:text-lg">
          Describe what you want to build. AI agents ask you a few questions, research existing apps, papers and
          feasibility, propose and judge solutions, verify every claim against its source, and summarise what to build
          and why. You watch every step as it happens.
        </p>
      </section>

      <div className="mx-auto max-w-3xl">
        <NewDecisionForm />
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <HowItWorks />
        <RecentSessions />
      </div>
    </div>
  );
}
