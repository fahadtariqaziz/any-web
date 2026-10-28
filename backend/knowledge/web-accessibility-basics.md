---
title: Web accessibility basics for generated apps (WCAG 2.2)
url: https://www.w3.org/TR/WCAG22/
topic: accessibility, a11y, keyboard, contrast, ui
verified: 2026-10-25
stack: html, react, vue, svelte, frontend, web, next.js

---
WCAG 2.2 is the W3C standard most accessibility requirements refer to (level AA is the usual target).

Basics that cover most small apps: use real HTML controls (button, input, label, select) instead of clickable divs,
so keyboard and screen reader support come for free; every function must work with the keyboard alone (success
criterion 2.1.1) and the keyboard focus must be visible (2.4.7); text needs a contrast ratio of at least 4.5:1 against
its background (3:1 for large text, 1.4.3); every input has a label; information is not given by colour alone (1.4.1);
results that update without a page load (e.g. a calculator display) can be announced with an aria-live region.

Check with the browser's accessibility inspector, a keyboard-only walk through the app, and an automated checker
such as axe; automated tools find only part of the problems.
