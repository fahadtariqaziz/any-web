---
name: web-ui-basics
audience: agent
applies_to: html, css, browser, frontend, web, vite, react, vue, svelte, javascript, typescript
description: Accessible, responsive browser UI for generated apps.
---
- Use real HTML controls (button, input, label, select), not clickable divs. Every action works with the keyboard;
  the focus is visible.
- Text contrast at least 4.5:1 (3:1 for large text); never convey state by colour alone.
- Results that change without a page load (a calculator display, a list) are in an aria-live region.
- Layout works from 360 px wide (phone) to desktop; no horizontal scrolling of the page.
- No external CDN script or font links: install packages with npm so the app works offline and builds reproducibly.
- Keep logic out of the DOM code (pure functions that tests can import), the UI only renders and wires events.
