import { Callout } from "@/components/ui/Callout";

/** Risky aspects of the idea the intake noticed (legal, privacy, payments, minors...). Informational only: they never
 *  change the route; the brief's risks section deals with them. Withdrawn flags are shown struck through. */
export function RiskFlagBanner({ flags, withdrawn = [] }: { flags: string[]; withdrawn?: { flag: string; reason: string }[] }) {
  if (flags.length === 0 && withdrawn.length === 0) return null;
  return (
    <Callout tone="info" title={flags.length ? "Aspects that need care in this project" : "Earlier risk notes were withdrawn"}>
      {flags.length > 0 && (
        <ul className="list-disc pl-5">
          {flags.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
      {flags.length > 0 && <p className="text-xs opacity-90">For information: the brief lists the risks and how the solution handles them.</p>}
      {withdrawn.length > 0 && (
        <ul className="list-disc pl-5 text-xs opacity-90">
          {withdrawn.map((w) => (
            <li key={w.flag}>
              <span className="line-through">{w.flag}</span> — withdrawn: {w.reason}
            </li>
          ))}
        </ul>
      )}
    </Callout>
  );
}
