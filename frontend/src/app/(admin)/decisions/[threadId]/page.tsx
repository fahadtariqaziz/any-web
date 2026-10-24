import { Suspense } from "react";

import { DecisionView } from "@/components/session/DecisionView";

// The thread_id is only known at request time, so the client view (which reads it with useParams)
// sits inside <Suspense>: Next.js renders the fallback first, then the view (cacheComponents rule).
export default function DecisionPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">Opening your session…</p>}>
      <DecisionView />
    </Suspense>
  );
}
