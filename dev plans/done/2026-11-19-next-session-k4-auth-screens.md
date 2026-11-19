# Next session: K4.5, the auth and account screens

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-19-next-session-k4-auth-screens.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public, mechframe/mechframe. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **K4's contract is approved** (`dev plans/contracts/k4-web-kernel.md`, decision 0042). A change to a seam goes under its "Changes after approval" (the next is change 16) and into the PR body.
- **Pushing and landing:**
  - Push once the local suites are green, then batch fixes.
  - Land by fast-forward once "CI result" is green and no thread is open.
  - Stage files by name and run gitleaks first.
  - CI's security gates are the owner's call.
- **Playwright** runs locally before each push. CI runs it only on main's pushes, weekly and by hand.
- **The approved boards are the spec,** but a contrast shortfall on them goes to the owner as a question, as the control edges did in #82.

## 3. State (2026-11-19, early morning; check, don't trust)

- **#82, the UI kit,** is branch `k4-ui-kit`, carrying the handoff. Check whether it's open or landed: `git log -1 origin/main` and `mcp__ccd_pr__get_status`.
- **main** is at `ce677e6` (#81) until #82 lands.
- **On #82's first head, run locally:** 1,994 Python tests passed at 98.53 %; Vitest 249 passed at 98.22 %; Playwright 38 passed. Codex's first two findings were fixed with failing-first tests. CodeRabbit and cubic were still reviewing.
- **K4.1 to K4.4** are #78, #79, #80 and #82. v1.0 is at 52 % once #82 lands.
- `C:\DEV\knowledge\owner.md` is uncommitted. It's the owner's to commit.

## 4. The job

1. **If #82 is still open, land it.** Answer the bots' threads, with a failing test first wherever a fix touches code. Then delete the branch, here and on GitHub, and republish the ledger (`dev plans/progress-ledger/README.md`).
2. **K4.5** (contract §4 item 5), on a new branch. `docs/HANDOFF.md`, Next 2, has the details. Its order:
   1. Write the device routes' contract tests from `docs/contracts/auth-api.md` and see them fail.
   2. Build the routes.
   3. Build the screens to VM Website `design/site/Auth.dc.html` and `Account.dc.html`, using the kit's parts. Add site-look sizes to `Button` and `Field` rather than a second kit.
   4. Write `kernel/tests/e2e/sign-in.spec.ts`. The sign-in and account pages join the axe run.

   Use the auth threat checklist skill: this is auth work.
3. **Then K4.6,** the admin shell.

## 5. Ask the owner

- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps.
- Rename `C:\DEV\AI-DevKit` and the `devkit-*` skills?
- Carry `line-3` and the four tint aliases back to VM Website's `tokens.json`? That's VM Website's session.

## 6. Environment and traps

- **Python tests,** in Git Bash: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`. It takes about 13 minutes, so run it in the background.
- **Web:** `npm.cmd run test:coverage`, `lint`, `typecheck` and `build`. Then run `npx.cmd playwright test` with `TEST_DATABASE_URL` set.
- **Picking one Playwright test:** use `file:line`. `-g "..."` with a space breaks `npx.cmd`'s quoting.
- **jsdom** lacks `showModal`, `scrollIntoView` and `scrollTo`. `vitest.setup.ts` supplies them.
- **A pinned count** in `tests/test_theme_vibrant_mindz.py` moves with each alias added.
- **cubic** resolves its own threads. Reply anyway.

## 7. Evidence and next IDs

The evidence is `docs/HANDOFF.md`, the contract's change 15, and #82's body. The next free IDs are decision 0043, PR #83 and migration `kernel_0011`.

## 8. Candidates for `knowledge/`

1. Measure a control's boundary as drawn, composited over what's behind it. Token pairs can't see a fill over a fill, and axe doesn't check WCAG 1.4.11.
2. A tint mixed at one ratio won't hold AA in both a dark theme and a light one. Give each theme its own tint token.
3. A flaky navigation test can be a real race. Make the slow side slow on purpose, and it fails every time.
4. Prove a Playwright check with a mutant: remove what it guards, and see it fail.
