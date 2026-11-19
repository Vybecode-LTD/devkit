# Next session: land #83, then K4.6, the admin shell

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-19-next-session-k4-admin-shell.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public, mechframe/mechframe. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **K4's contract is approved** (`dev plans/contracts/k4-web-kernel.md`, decision 0042). A change to a seam goes under "Changes after approval" (the next is change 17) and into the PR body.
- **Pushing and landing:** push once the local suites are green, then batch fixes. Land by fast-forward once "CI result" is green and no thread is open. Stage files by name; run gitleaks first. CI's security gates are the owner's call.
- **Playwright** runs locally before each push; CI runs it only on main's pushes, weekly and by hand.
- **The approved boards are the spec;** a contrast shortfall on them goes to the owner as a question.

## 3. State (2026-11-19, late morning Eastern; check, don't trust)

- **main** is `540056a` (#82).
- **#83, K4.5, the sign-in and account screens,** is branch `k4-auth-screens`: device routes and `GET /api/auth/security` (contract tests first), `kernel/web/src/auth/` and `account/`, the step-up dialog, the site's look in the kit, `kernel/tests/e2e/sign-in.spec.ts`. Its handoff is `docs/HANDOFF.md`. Check whether it's open or landed: `git log -1 origin/main`, `mcp__ccd_pr__get_status`.
- **Run locally on #83's first head:** Vitest 369 passed at 98.2 % of lines; Playwright 56 passed; the Python suite's result is in #83's body.
- `C:\DEV\knowledge\owner.md` is uncommitted; the owner's to commit.

## 4. The job

1. **If #83 is still open, land it.** Answer the bots' threads, with a failing test first wherever a fix touches code. Then delete the branch, here and on GitHub, and republish the ledger (`dev plans/progress-ledger/README.md`).
2. **K4.6, the admin shell** (contract §4 item 6), on a new branch: the sidebar, the top bar (Ctrl K jumps to any admin page the person can see; notices; View site), the page header, Dashboard and Activity, and `GET /api/kernel/admin/attention` (contract §2 addition 9, contract tests first). Built to VM Website `design/site/AdminDashboard.dc.html` and `AdminActivity.dc.html` in the admin's look (decision 0040; `design/specs/admin-look.md`; shell-slots.md). Screens load lazily (`app/screens.ts`). Screenshots beside the boards at 1440 and 390 in both themes go in `dev plans/`.
3. **Then K4.7** (people and roles, with role editing; the auth threat checklist applies) **and K4.8** (settings and System).

## 5. Ask the owner

- A way for a site to reword the kernel's screens (the board's "Join the vibe")?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps.
- Rename `C:\DEV\AI-DevKit` and the `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website (that project's session)?

## 6. Environment and traps

- **Python tests,** in Git Bash, in the background: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`. Don't regenerate `openapi.json` meanwhile. Another project's renders can slow it well past 13 minutes.
- **Web:** `npm.cmd run test:coverage`, `lint`, `typecheck`, `build`; then `npx.cmd playwright test` with `TEST_DATABASE_URL` set. Pick one test by `file:line`.
- **A look in a browser:** `E2E_PORT=8770 ... python -m harness.e2e` serves the build; screenshot with Playwright (the hidden pane's time out). Stop it before a Playwright run: both use `mechframe_e2e`.
- **React Router draws a move in a transition;** code that reads the drawn page after `navigate()` asks for `flushSync: true` (`drawNow`). Don't import `react-router/dom`: under Vitest it's a second copy.
- **A theme switch in a test** waits for `document.getAnimations()` before measuring.
- **jsdom** has no WebAuthn: stub `PublicKeyCredential` and `navigator.credentials`.

## 7. Evidence and next IDs

`docs/HANDOFF.md`, the contract's change 16, decision 0043, #83's body, `dev plans/2026-11-19-k45-screens/`. Next free: decision 0044, PR #84, migration `kernel_0011`.

## 8. Candidates for `knowledge/`

1. React Router 7 draws each move in a transition: `navigate()` settles first.
2. A test that switches theme waits for transitions, or measures mid-fade.
3. A CJS-and-ESM package can load twice under Vitest.
4. An e2e server must answer at the browser's address, or writes fail the origin check.
