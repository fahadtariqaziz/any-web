"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";

import { BuilderView } from "@/components/builder/BuilderView";

// The project id is only known at request time, so the part that reads it sits inside <Suspense>
// (cacheComponents rule, same as /decisions/[threadId]). key={threadId}: switching projects starts fresh.
function ProjectFromUrl() {
  const { threadId } = useParams<{ threadId: string }>();
  return <BuilderView key={threadId} threadId={threadId} />;
}

export default function ProjectPage() {
  return (
    <Suspense fallback={null}>
      <ProjectFromUrl />
    </Suspense>
  );
}
