---
name: web-ui-design
audience: agent
applies_to: html, css, browser, frontend, web, vite, react, vue, svelte, next.js, nextjs, tailwind
description: Make generated web apps look like a finished product, not browser defaults.
---
The user judges the app by how it looks in the preview. Unstyled browser defaults (inline forms, Times-like headings,
grey system buttons, bare tables) read as broken, even when every test passes.

- Use the project's design foundation (the shared components / styles the first task set up). Never leave a screen
  with raw, unstyled `<button>`, `<input>`, `<select>` or `<table>`: use the shared Button, Input, Card, Table... or
  their classes. If the foundation lacks something you need, add it there, not inline in one page.
- Page layout: an app shell with a top bar or sidebar (app name, navigation with the current page highlighted, the
  user menu on the right), and a content column with a max width (about 960-1200 px) and generous padding.
- Every page starts with a clear title (and a one-line description when helpful), with the main action as one primary
  button aligned to the right of the title. One primary button per screen; others are secondary or subtle.
- Group related content in cards (white surface, subtle border or shadow, rounded corners, padding 16-24 px).
- Forms: each field is a label above its input, stacked (or a 2-column grid on wide screens), consistent widths,
  help or error text right under the field; submit buttons at the bottom of the form, never squeezed into a line
  of fields. Inputs have a visible border, padding and a focus ring.
- Lists of records are tables with a header row, row separators, right-aligned numbers / money, and row actions as
  small subtle buttons or a menu; on phones they become stacked cards. Never a bullet list of records with buttons.
- Consistent spacing scale (4 / 8 / 12 / 16 / 24 / 32 px) and type scale (page title ~24-28 px, section ~18 px,
  body 14-16 px); a neutral palette plus ONE accent colour for primary actions and links; status colours (green ok,
  amber warning, red error) always with a text label.
- Every list and dashboard has an empty state (short text + the action that fills it), a loading state and an error
  state shown in a styled alert, not raw error text at the top of the page.
- Numbers: money and percentages formatted (e.g. $1,234.56, 80 %), dates in a readable format.
- Check the result like a user would: no element overflows, nothing is crammed on one line, the page is readable at
  360 px and at desktop width.
