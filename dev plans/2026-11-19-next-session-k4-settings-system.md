# Next session: K4.8, settings and System

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-19-next-session-k4-settings-system.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public, mechframe/mechframe. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **K4's contract is approved** (`dev plans/contracts/k4-web-kernel.md`, decision 0042). A change to a seam goes under "Changes after approval" (the next is change 19) and into the PR body.
- **Pushing and landing:** push once the local suites are green, then batch fixes (wait for CodeRabbit's review before pushing a fix while CI runs). Land by fast-forward once "CI result" is green and no thread is open. Stage files by name; run gitleaks on the staged diff. CI's security gates are the owner's call.
- **Playwright** runs locally before each push; CI runs it only on main's pushes, weekly and by hand.
- **The approved boards are the spec;** a contrast shortfall on them goes to the owner as a question.
- **`AGENTS.md` holds `CLAUDE.md`'s text** under its own first line: change both together.

## 3. State (2026-11-19, evening Eastern; check, don't trust)

- **main** is `41c2879`, #85's head (K4.7, people and roles), landed by fast-forward; its branch deleted here and on GitHub. Check: `git log -1 origin/main`. No PR open. The handoff commit after it is docs only.
- **K4.7 gave:** `kernel/auth/roles.py` (the People list, granting roles, the roles read, role editing), `auth.role.manage` (`kernel_0012`), `kernel/web/src/admin/People.tsx`, `Roles.tsx`, `roleAccess.ts`, decision 0045, contract change 18. `docs/HANDOFF.md` has the rest.
- **Tests on #85's last head:** Vitest 454, Playwright 68, CI green. The ledger's `steps` dataset points at `41c2879`'s rows.

## 4. The job

1. **K4.8, settings and System** (contract §4 item 8; §2 additions 6 to 8), on a new branch, contract tests first: `GET`/`PUT /api/kernel/admin/settings/{id}` and its history (`kernel.settings.manage`, 409 `kernel.settings_conflict` as built), `GET`/`PUT /api/kernel/admin/modules…` (`kernel.module.manage`), and System: `GET /api/kernel/admin/system`, the dead jobs, retry and discard (`kernel.jobs.manage`, already granted by `kernel_0011`). Screens: Site, Features and System to VM Website `design/site/AdminSettings.dc.html` with `AdminPage`, lazy in `app/screens.ts` (they show `Pending` now). The Site tab shows only fields a settings section holds; the board's tagline, address, contact email and time zone have no home: leave them off, not faked. Screenshots beside the board at 1440 and 390 in both themes in `dev plans/`. Add the pages to `admin.spec.ts`'s 390 and axe loops.
2. **Then K4's gate** (contract §7), then K5.

## 5. Ask the owner

- A name for a person (the boards greet "Big Haas"; nothing sets `display_name`; People shows `name` once set)?
- A way for a site to reword the kernel's screens?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps.
- Rename `C:\DEV\AI-DevKit` and the `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?
- The ledger's replaced asset `cd100445…` is unused; delete it?

## 6. Environment and traps

- **Python tests,** in Git Bash, in the background, into a log: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel` (about 13 minutes). Don't regenerate `openapi.json` meanwhile. A route answering through `answer()` still declares `response_model` (`test_openapi.py`).
- **Web:** `npm.cmd run test:coverage`, `lint`, `typecheck`, `build`; then `npx.cmd playwright test` with `TEST_DATABASE_URL` set.
- **Screenshots:** a throwaway spec in `kernel/tests/e2e/` (`makeUser`, `signInTo`, `theme` from `support.ts`), deleted after; never commit it.
- **SQLAlchemy 2.1:** no `Result.tuples()` (warnings are errors) and no `dict(result)`; use a comprehension.
- **The session's cache key** is `["kernel", "session"]`: after a change to the person's own access, call `refreshSession(queryClient)`.
- **A 404 `kernel.not_found`** reads as "not built" in the contract suite: a new route's own 404 needs a code of its own, or `UNCHECKED`.
- **Windows:** two files differing only in case collide (`roles.ts`, `Roles.tsx`).

## 7. Evidence and next IDs

`docs/HANDOFF.md`, the contract's change 18, decision 0045, #85's body, `dev plans/2026-11-19-k47-people-roles/`. Next free: decision 0046, PR #86, migration `kernel_0013`, contract change 19.

## 8. Candidates for `knowledge/`

1. A visually hidden, absolutely placed element inside a scroller makes the page scroll sideways unless the scroller is positioned.
2. SQLAlchemy 2.1: `Result.tuples()` is deprecated, and `dict(result)` misreads a `Result`.
3. A contract suite that reads the router's 404 as "not built" needs its own 404 codes for a route's real misses.
4. A self-demotion race: two actors on disjoint rows meet only on a shared lock (the role row), not their own.
5. React Router 7 draws each move in a transition: `navigate()` settles first.
