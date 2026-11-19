# Next session: K4.4, the UI kit

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-18-next-session-k4-ui-kit.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public, mechframe/mechframe. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **K4's contract is approved** (`dev plans/contracts/k4-web-kernel.md`, decision 0042). A change to a seam goes under the contract's "Changes after approval" (the next is change 15) and into the PR body.
- **Pushing and landing:**
  - Push once the local suites are green, then batch fixes.
  - Land by fast-forward once "CI result" is green and no thread is open.
  - Stage files by name and run gitleaks first.
  - CI's security gates are the owner's call.
- **Playwright** runs locally before each push. CI runs it only on main's pushes, weekly and by hand.

## 3. State (end of 2026-11-18, verified at close)

- **main** is at `a123043` (#80, the themes), or at #81 if this handoff has landed: check with `git log -1 origin/main`.
- **#81** is this handoff, on branch `handoff-k4-themes`. No other PR is open.
- **CI on `a123043`:** 1,961 Python tests passed at 98.14 % coverage, and 159 Vitest tests. main's E2E run was in progress at close.
- **K4.1 to K4.3 are done** (#78, #79, #80). v1.0 is at 50 %.
- `C:\DEV\knowledge\owner.md` is uncommitted. It's the owner's to commit.

## 4. The job

1. **If #81 is still open, land it.** Check `mcp__ccd_pr__get_status` and the bots' reviews of its head. Run `git merge-base --is-ancestor origin/main <sha>`, then `git push origin <sha>:refs/heads/main`. Delete the branch, then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **K4.4, the UI kit**, on a new branch: contract §4 item 4, plus `docs/HANDOFF.md`, Next 2, which holds the owner's focus rules and the Table and SaveBar notes.
   - **Where it goes:** `kernel/web/src/ui/`. Port the parts from VybeSite, moving them to React 19 (ref as a prop) and the tokens. Draw them from VM Website's `design/generators/admin_kit.py`.
   - **Move, don't copy:** `RouteFocus` and `ErrorBoundary` already exist in `app/`.
   - **What to test:**
     - Each control's whole boundary reaches 3:1 in both themes (change 14).
     - The Table's `focusin` handler, with real Tab presses in Playwright.
     - The kit page's axe run in both themes.
   - **Icons:** `IconName` becomes the kit's icon set (change 10). The admin focus-ring tokens join `REQUIRED` in `tools/themes.py` and `themes/README.md`.
   - **Before the PR:** run VybeSite's brand check. Expect three or four review rounds.
3. **Then K4.5:** the auth and account screens. It writes the device routes' contract tests first.

## 5. Ask the owner

- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps.
- Rename `C:\DEV\AI-DevKit` and the `devkit-*` skills?

## 6. Environment and traps

- **Python tests**, in Git Bash (the Bash tool): `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`. In PowerShell, set both with `$env:NAME = "..."` first. Run it in the background; it takes about 11 minutes.
- **Web:** `npm.cmd run test:coverage`, `lint`, `typecheck`, `build`. Then `npm.cmd run e2e` with `TEST_DATABASE_URL` set.
- **Themes:** after editing a `tokens.json`, run `python -m tools.themes`.
- **Picking one test:** `npx.cmd playwright test -g "..."` with spaces breaks its quoting, so use `file:line`.
- **Escapes:** Bash heredocs turn `\n` in Python strings into newlines, so edit escapes with the Edit tool.
- **cubic** resolves its own threads when it sees a fix. Reply anyway.

## 7. Evidence and next IDs

The evidence is `docs/HANDOFF.md`, the contract's changes 9 to 14, and the PR bodies of #79 and #80. The next free IDs are decision 0043, PR #82 and migration `kernel_0011`.

## 8. Candidates for `knowledge/`

1. A theme's type on `html` shrinks the root, and with it every rem token. Put it on `body`, and have a browser test check that the root is 16px.
2. A token-against-token contrast test catches a role shade's AA failure before axe does. axe still misses control boundaries (WCAG 1.4.11).
3. Build React routes only from the modules that are on, matching case-sensitively, or the client's routing disagrees with the server's.
4. A focus manager must stop all pending work the moment the person moves focus.
