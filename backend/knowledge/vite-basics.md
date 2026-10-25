---
title: Vite basics for small web apps (dev server, build, env variables)
url: https://vite.dev/guide/
topic: vite, frontend tooling, dev server, build
---
Vite is a frontend build tool with a fast dev server. A project usually has the scripts `dev` (`vite`: the dev
server), `build` (`vite build`: a production bundle in dist/) and `preview` (`vite preview`: serves the built dist/
locally). The dev server port is set with `--port`; with `--strictPort` Vite exits instead of trying the next port
when the port is taken (the builder starts previews with `--port {port} --strictPort`).

Environment variables (https://vite.dev/guide/env-and-mode): only variables prefixed with VITE_ are exposed to the
client code as import.meta.env.VITE_*. Everything exposed this way ends up in the browser bundle, so secrets (API keys,
tokens) must never be put in VITE_ variables; they belong on a server.
