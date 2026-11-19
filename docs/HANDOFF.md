# Handoff

Overwritten every session. This one: 2026-11-18, late afternoon to night Eastern (Claude Code, the owner's machine). K4.1 to K4.3 landed: #78 (the typed client), #79 (the app shell) and #80 (the themes). This page rides in #81.

## State

- **K0 to K3 are done.** K3's gate passed (#75), and K2 steps 9 to 11 wait (decision 0029). The device list's three routes (K2 step 4) were never built and have no contract tests. K4.5 writes those tests first.
- **K4:** contract `dev plans/contracts/k4-web-kernel.md`, decision 0042. Three of its eight PRs have landed:
  - **#78, the typed client** (92fd8fb): `Answer` models, `kernel/openapi.json`, `kernel/web/src/api/`.
  - **#79, the app shell** (0a6fd1b):
    - The kernel's pages: listed in `kernel.json` and held in code by `server_copy.KERNEL_PAGES` and `kernel/web/src/app/pages.ts`. Each shows its heading and "This page isn't ready yet." until its screen is built.
    - `GET /api/kernel/site`.
    - `mountApp`, which returns a promise and builds its routes from the modules that are on.
    - `useSession`, which re-reads the session on a 401 and forgets it only if it's gone.
    - The guards, the slots, `<Seo>`, `RouteFocus` and `ErrorBoundary` (in `app/`), and `testing.ts`.
    - Playwright with axe: `npm run e2e` against `python -m harness.e2e`, and `.github/workflows/e2e.yml`.
  - **#80, the themes** (a123043):
    - `themes/README.md` lists the 34 required tokens and the contrast rules.
    - Two themes: `machined-light` (its role shades kept by the owner) and `vibrant-mindz`.
    - `tools/themes.py`, plus the colour lint: ESLint for TypeScript, `tests/test_themes.py` for CSS.
    - axe runs on every public page in both themes.
- **Contract changes 9 to 14** were added this session; they're listed in the contract. Change 14 covers the themes.
- **Tests:** CI on a123043 passed.
  - Python: 1,961 passed, 5 skipped, 27 xfailed, coverage 98.14 %.
  - Vitest: 159 tests in 9 files, 98.37 % of lines.
  - Playwright runs on main's pushes.
- **Other:**
  - The npm audit allowlist is empty.
  - v1.0 is at 50 % (30 of 60 steps).

## Next

1. **Land #81** (this page) if it's still open, then republish the ledger.
2. **K4.4, the UI kit** (contract §4 item 4), in `kernel/web/src/ui/`.
   - **What to build:** port the parts from VybeSite and VM Website's `design/generators/admin_kit.py` to React 19 and the tokens. Run the brand check before the PR.
   - **What exists already:** `RouteFocus` and `ErrorBoundary` are in `app/`. Move them; don't copy them.
   - **Icons:** `IconName` becomes the kit's icon set (change 10).
   - **Control edges:** each control's whole boundary must reach 3:1 in both themes (WCAG 1.4.11; change 14). axe doesn't check this, so the kit's tests do.
   - **Admin focus** (the owner, 2026-11-18):
     - An accent ring: 1px `#FF7A1F` with a 4px glow of it at 28%.
     - A 2px page-colour gap comes before the ring on a filled control (the primary button, a switch that's on) and on a pressed chip or tile. These carry `aria-pressed`.
     - Rows in a clipped list, and the sideways table scroller, draw the ring inset. The current nav item and tab keep their 2px edge under the ring.
     - The sign-in and account screens keep the site's 2px `#36B4FF` outline, 3px off.
     - The tokens (`shadow.focus-ring`, `-gap`, `-inset`, `nav-current-focus`, `tab-current-focus`) join `REQUIRED` with the kit.
   - **The Table:**
     - Give the scroller `scroll-padding-inline: 10px`.
     - Add a `focusin` handler that calls `scrollIntoView({block: 'nearest', inline: 'nearest'})`, because Chrome leaves a control cut off when 20px of it already shows.
     - Test the handler with real Tab presses in Playwright, not only in jsdom.
   - **The SaveBar:** sets `scroll-padding-bottom` to its height while it shows (WCAG 2.4.11).
   - **Sources in VM Website:**
     - `design/specs/admin-look.md`, "Keyboard focus";
     - `design/theme/vibrant-mindz/shell-slots.md`, finding 9 and the `.a-scroll` rules;
     - the HELMET CSS in `admin_kit.py`.
3. **K4.5 to K4.8.** The member and admin pages join the axe run as they're built.
4. **After K4:** K5, the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Decisions 0032 to 0039's own calls, each listed in its record: keep them?
- When to make the R2 test buckets. Also the desk steps: the `postgres` password, and `Set-ExecutionPolicy` if wanted.
- Rename `C:\DEV\AI-DevKit` (Claude Code's memory moves with it) and the account's `devkit-*` skills?
- `C:\DEV\knowledge\owner.md` is uncommitted; the owner commits it.

## Notes

- **Review volume:** #79 drew 49 review threads and #80 drew 21. All were fixed, with a failing test first wherever the fix touched code, or answered with reasons. Expect three or four rounds per PR.
- **cubic resolves its own thread when it sees the fix,** sometimes before the reply is posted. Post the reply anyway.
- **Put a theme's body type on `body`, never `html`,** so the root stays 16px and every rem token keeps its size (Codex on #80). Playwright checks this.
- **Theme CSS line endings:** a Windows checkout wrote the generated theme CSS as CRLF, so `tools.themes --check` failed locally while CI on Linux passed. `.gitattributes` now keeps those files LF, as it already did `openapi.json`, and a test checks it (#81).
- **Pointing VM Website's census at the copy in this repo is VM Website's work.**
- **Traps:**
  - `npx.cmd playwright test -g "..."` with spaces breaks its quoting: pick the test by `file:line` instead.
  - Give a subprocess that reads output `encoding="utf-8"`, or Windows decodes it as cp1252.
  - GitHub can answer 502 on `gh pr edit`: check whether the edit happened, then retry.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first.
