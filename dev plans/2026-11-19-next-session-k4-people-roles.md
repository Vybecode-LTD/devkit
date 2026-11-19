# Next session: K4.7, people and roles

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-19-next-session-k4-people-roles.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public, mechframe/mechframe. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **K4's contract is approved** (`dev plans/contracts/k4-web-kernel.md`, decision 0042). A change to a seam goes under "Changes after approval" (the next is change 18) and into the PR body.
- **Pushing and landing:** push once the local suites are green, then batch fixes. Land by fast-forward once "CI result" is green and no thread is open. Stage files by name; run gitleaks on the diff first. CI's security gates are the owner's call.
- **Playwright** runs locally before each push; CI runs it only on main's pushes, weekly and by hand.
- **The approved boards are the spec;** a contrast shortfall on them goes to the owner as a question.
- **Role editing is auth work:** run the auth threat checklist (`anthropic-skills:auth-threat-model-checklist`) before pushing.

## 3. State (2026-11-19, afternoon Eastern; check, don't trust)

- **main** is #84's head (K4.6, the admin shell), landed by fast-forward; its branch deleted here and on GitHub. Check: `git log -1 origin/main`. No PR open.
- **K4.6 gave:** `kernel/web/src/admin/` (frame, `AdminPage`, Dashboard, Activity, `JumpTo`, `Notices`), `GET /api/kernel/admin/attention`, the staff log's `people`/`kept_days`/several `action`s, `kernel.jobs.manage` (`kernel_0011`), `StatCard`, the info tone, `kernel/tests/e2e/admin.spec.ts`. `docs/HANDOFF.md` has the rest.
- **Tests on #84's last head:** see #84's body; the ledger is republished.

## 4. The job

1. **K4.7, people and roles** (contract §4 item 7; §2 additions 4 and 5), on a new branch, contract tests first (auth-api.md's routes; the contract suite in `kernel/tests/contract/`): `GET /api/auth/admin/users`, `PUT .../roles`, `GET /api/auth/admin/roles`, and role editing (`POST`/`PUT`/`DELETE /api/auth/admin/roles…`) with every refusal tested and a holder's next request carrying a new token. `auth.role.manage` in `kernel.json` with its grant migration (`kernel_0012`). Screens to VM Website `design/site/AdminPeople.dc.html` and `AdminRoles.dc.html` with `AdminPage` (`kernel/web/src/admin/`), loaded lazily (`app/screens.ts`). Then the sidebar's person card and Activity can show role names from the roles read. Screenshots beside the boards at 1440 and 390 in both themes in `dev plans/`.
2. **Then K4.8** (Site, Features, System; additions 6 to 8).

## 5. Ask the owner

- A name for a person (the boards greet "Big Haas"; nothing sets `display_name`)?
- A way for a site to reword the kernel's screens?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps.
- Rename `C:\DEV\AI-DevKit` and the `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?

## 6. Environment and traps

- **Python tests,** in Git Bash, in the background: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`. Don't regenerate `openapi.json` meanwhile.
- **Web:** `npm.cmd run test:coverage`, `lint`, `typecheck`, `build`; then `npx.cmd playwright test` with `TEST_DATABASE_URL` set.
- **A look in a browser:** `E2E_PORT=8770 ... python -m harness.e2e` binds 127.0.0.1; make setup calls from inside the page (`page.evaluate(fetch)`), since Node's requests to `localhost` try IPv6 first. Stop it before Playwright.
- **React Router draws a move in a transition;** read the drawn page after `navigate()` with `flushSync: true`. **A theme switch in a test** waits for `document.getAnimations()`.
- **Edits to `docs/progress.json`** go line by line: re-dumping it reformats every line.

## 7. Evidence and next IDs

`docs/HANDOFF.md`, the contract's change 17, decision 0044, #84's body, `dev plans/2026-11-19-k46-admin/`. Next free: decision 0045, PR #85, migration `kernel_0012`.

## 8. Candidates for `knowledge/`

1. React Router 7 draws each move in a transition: `navigate()` settles first.
2. A test that switches theme waits for transitions, or measures mid-fade.
3. An e2e server must answer at the browser's address, or writes fail the origin check.
4. A uvicorn bound to 127.0.0.1 refuses Node's `localhost` (IPv6 first); browsers fall back.
