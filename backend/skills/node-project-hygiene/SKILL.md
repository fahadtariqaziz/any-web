---
name: node-project-hygiene
audience: agent
applies_to: node, npm, javascript, typescript, vite, react, next, vue, svelte, express
description: package.json, scripts, ports and files of a Node project.
---
- package.json scripts match the plan's commands exactly (install / test / build / dev); keep package-lock.json.
- The dev server must accept the port it is given (Vite: `vite --port <n> --strictPort` via `npm run dev -- --port
  {port} --strictPort`; a Node server reads process.env.PORT) and listen on localhost.
- Use one module system consistently ("type": "module" with import/export, or CommonJS).
- .gitignore contains node_modules/ and dist/; no global installs; dependencies are added with npm install so they
  land in package.json.
- Secrets come from environment variables; ship a .env.example with variable names only (never VITE_ variables for
  secrets: they end up in the browser bundle).
