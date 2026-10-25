"use client";

// The list of projects (sessions) for the projects drawer and the home page, shared so a page can refresh it
// (a project was created, intake found its name...). Every session is listed, newest first, except first
// messages that intake rejected (not an app idea: nothing to reopen).

import { createContext, useCallback, useContext, useState } from "react";

import { useFetch } from "@/hooks/useFetch";
import { listDecisions } from "@/lib/api/client";
import type { ApiError } from "@/lib/api/client";
import type { SessionSummary } from "@/lib/api/types";

type ProjectList = {
  projects: SessionSummary[] | null;
  error: ApiError | null;
  refresh: () => void;
};

const ProjectListContext = createContext<ProjectList | null>(null);

export function ProjectListProvider({ children }: { children: React.ReactNode }) {
  const [version, setVersion] = useState(0);
  const { data, error } = useFetch(() => listDecisions(50), `projects|${version}`);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  const projects = data ? data.sessions.filter((s) => !(s.status === "failed" && !s.project_name)) : null;
  return <ProjectListContext.Provider value={{ projects, error, refresh }}>{children}</ProjectListContext.Provider>;
}

export function useProjectList(): ProjectList {
  const value = useContext(ProjectListContext);
  if (!value) throw new Error("useProjectList must be used inside <ProjectListProvider>");
  return value;
}

/** "untitled project" / missing → the first message; first letter upper case. */
export function projectTitle(project: string | null, question: string | null): string {
  const text = project && project !== "untitled project" ? project : (question ?? "New project");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
