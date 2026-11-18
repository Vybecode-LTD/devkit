# Handoff

Overwritten every session. This one: 2026-11-18, afternoon Eastern (Claude Code, the owner's machine). K4's contract was written and approved. #78, K4's typed client, went through four review rounds, and this page rides in it. The next session lands #78.

## State

- **K0 to K3 are done.** K3's gate passed (#75). K2 steps 9 to 11 wait (decision 0029). The device list's three routes, part of K2 step 4, were never built and have no contract tests. They moved to K4's account PR.
- **K4's contract is approved**: `dev plans/contracts/k4-web-kernel.md` and decision 0042. It covers eight PRs: typed client, app shell, themes, UI kit, auth and account screens, admin shell, people and roles, settings and System.
  - **The owner's answers (2026-11-18):** the admin includes role editing, New role and Settings › System; the server's words are hidden by `@media (scripting: enabled)` with a 3 s reveal; Playwright runs locally before each push and in CI on main's pushes, weekly and by hand; Depth waits.
  - **My calls in it:** only custom roles can be edited; fields on the Site board with no settings home are left off.
  - **Contract changes:** eight so far, in its list. `Contract change: the kernel's pages are listed in kernel.json and kept in code by shell.py and the router, held equal by tests` (change 8: a site never receives `kernel.json`).
- **#78 is open: K4.1, the typed client.** Every fix is pushed. CI was green on `1acb8f0` and runs again on the head, which carries cubic's last fix and this page.
  - Every API route's JSON answer is an `Answer` model that refuses unnamed keys, checked on the way out; a 204 has no body. A route that sets a cookie or header builds its JSON through `answer()`, and a syntax-tree guard refuses any other `JSONResponse`.
  - `kernel/openapi.json` is committed, made by `python -m tools.openapi`, with errors documented as problems. The module ids `auth` and `kernel` are reserved.
  - `kernel/web/src/api/` holds the client:
    - openapi-fetch, plus openapi-react-query's hooks, with their types restated so the error is an `ApiProblem` and a query reads only;
    - types from `npm run api:types` (`api:check` in CI);
    - a query doesn't retry a 4xx;
    - a 401 signs the session out; a write refused for a step-up asks once and resends once.
- **npm audit allowlist is empty.** GitHub withdrew the picomatch advisory on 2026-11-18, so the December recheck is gone.
- **Tests:**
  - The last full run was on `23f3c14`'s tree: 1,728 passed, 8 skipped, 27 xfailed, coverage 98.53 %.
  - Since then: `tests/test_openapi.py` (23 tests), `test_modules` and the 22 web tests all pass.
  - The web has 22 Vitest tests in the client file and 29 in all.

## Next

1. **Land #78**: fast-forward, once "CI result" is green on its head and no thread is open. Then republish the progress ledger.
2. **K4.2, the app shell.** The starting prompt is `dev plans/2026-11-18-next-session-k4-app-shell.md`.
3. **Then K4.3 to K4.8, with these notes:**
   - **Themes (K4.3):**
     - `border` is the edges of cards and rows, `border-strong` the edges of controls; Machined Light's `--color-border` maps to `border-strong`.
     - `font.mono` is the code face: Vibrant Mindz's `typography.fontFamily.code`, not its `mono` (Doto).
     - Details: contract change 5; VM Website `design/theme/vibrant-mindz/shell-slots.md`.
   - **Admin focus (the owner, 2026-11-18, 15:40 Eastern, through the VM Website session):**
     - Keyboard focus in the admin is an accent ring drawn like Machined Light's `--shadow-focus`: a 1px `#FF7A1F` line and a 4px glow of it at 28%.
     - On a filled control (the primary button, a switch that's on), a 2px gap of the page colour comes first.
     - In a list that clips its rows, the ring is drawn inside the row.
     - The current nav item and tab keep their 2px edge under the ring.
     - The sign-in and account screens keep the site's 2px `#36B4FF` outline, 3px off, so the kit draws focus two ways.
     - Tokens: `shadow.focus-ring`, `focus-ring-gap`, `focus-ring-inset`, `nav-current-focus`, `tab-current-focus`. Brief: VM Website `design/specs/admin-look.md`, "Keyboard focus" (canvas version 70).
   - **Kit findings from the same session:**
     - A sticky save bar can hide the focused control (WCAG 2.4.11), so the kit sets `scroll-padding-bottom` to the bar's height while it shows.
     - Chrome makes a sideways-scrolling table a Tab stop, so give the scroller a visible focus style.
4. Then K5, the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Decisions 0032 to 0039's own calls, each listed in its record: keep them?
- When to make the R2 test buckets. The desk steps: the `postgres` password, and `Set-ExecutionPolicy` if wanted.
- Rename the folder `C:\DEV\AI-DevKit` (Claude Code's memory moves with it) and the account's `devkit-*` skills?
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner commits it.

## Notes

- **#78 drew 25 findings:** Codex 1, CodeRabbit 14, cubic 11. All were real, and all were fixed with a test that failed first where they touched code. Expect several rounds.
- **A helper agent claimed the device routes had strict-xfail tests. None existed.** Grep before writing a claim into docs.
- **The Bash tool turns `\n` inside a heredoc's Python strings into real newlines.** Edit test strings that hold escapes with the Edit tool.
- **openapi-typescript asks for TypeScript `^5` as a peer;** a `package.json` override holds it on 6.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first.
