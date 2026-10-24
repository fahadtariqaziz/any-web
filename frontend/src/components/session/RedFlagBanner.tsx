import { Callout } from "@/components/ui/Callout";

/** Always at the top of the page when active red flags exist (requirement: red flags first). */
export function RedFlagBanner({ flags, withdrawn = [] }: { flags: string[]; withdrawn?: { flag: string; reason: string }[] }) {
  if (flags.length === 0 && withdrawn.length === 0) return null;
  return (
    <Callout tone={flags.length ? "danger" : "warning"} title={flags.length ? "Possible emergency signs were reported" : "Earlier warning signs were withdrawn"}>
      {flags.length > 0 && (
        <ul className="list-disc pl-5">
          {flags.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
      {flags.length > 0 && (
        <p className="font-medium">If any of these is happening now, call your local emergency number or go to the nearest emergency department.</p>
      )}
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
