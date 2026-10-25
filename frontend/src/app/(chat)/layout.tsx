import { BuilderShell } from "@/components/builder/BuilderShell";

// The builder (Lovable style, full screen): home at "/", one project at "/c/<id>" (chat left, preview right).
// The admin view with every agent step is at /admin.
export default function BuilderLayout({ children }: { children: React.ReactNode }) {
  return <BuilderShell>{children}</BuilderShell>;
}
