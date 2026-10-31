---
name: browser-e2e-testing
audience: agent
phases: e2e
description: Write and fix Playwright browser tests that click through the app's user flows like a real user.
---
These tests are the builder's proof that the app WORKS for its user, not only that it compiles. The builder runs
`npx playwright test` after every build and change: Playwright starts the dev server itself (own port, no .env) and
drives the installed Chrome. playwright.config.mjs belongs to the builder; never edit it.

- Files: `e2e/<flow>.e2e.mjs`, ES modules: `import { test, expect } from '@playwright/test';`. Never `.spec` /
  `.test` names or a `test/` folder (the unit test runner would pick them up). Install with
  `npm install -D @playwright/test`; never run `npx playwright install` (no browser download is needed or allowed).
- One test per user flow of the MVP features, named for what the user achieves ("adds an expense and sees the new
  total"). A flow: `await page.goto('/')`, then real interactions, then assertions on what the user sees.
- Select like a user: `page.getByRole('button', { name: 'Add' })`, `getByLabel('Amount')`, `getByText(...)`,
  `getByPlaceholder(...)`. Use `getByTestId` only when nothing visible identifies the element (then add the
  `data-testid` to the component). Never CSS chains like `div > div:nth-child(3)`.
- Assert with web-first assertions that wait: `await expect(locator).toHaveText(...)`, `toBeVisible()`,
  `toHaveValue()`, `toHaveCount()`, `await expect(page).toHaveURL(/settings/)`. Never `waitForTimeout` / sleeps.
- Cover each form's happy path AND one validation error (empty or invalid input shows the message, nothing saved).
- Each test starts from a clean app: no order between tests. Data the app keeps in localStorage starts empty in a
  new browser context; when the app needs data, the test creates it through the UI first.
- Flows behind an external service the tests cannot reach (sign-in, a hosted database, a paid API): test what works
  without it, e.g. the setup screen names the missing settings, the sign-in form validates its fields. No real
  credentials, no network calls to real services from tests.
- Keep it fast: about 3-8 tests for a small app, each well under the 20 s test timeout.
- When a browser test fails: read the error and the call log (which locator, expected vs received). Decide against
  the brief whether the app or the test is wrong. Fix the app when it misbehaves; fix the test only when it asserts
  something the brief does not ask for or uses a selector that does not exist. Never delete, `.skip` or weaken a test.
