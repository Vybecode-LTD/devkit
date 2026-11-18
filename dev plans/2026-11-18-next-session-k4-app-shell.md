# Next session: land #78, then K4's app shell

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-18-next-session-k4-app-shell.md and follow it, starting with section 4."

## 1. The project

MechFrame: website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo mechframe/mechframe; nothing deployed.

## 2. Rules not in a CLAUDE.md

- K4's contract is approved (`dev plans/contracts/k4-web-kernel.md`, decision 0042). A change to a seam goes under its "Changes after approval" and into the handoff as `Contract change:`.
- Push once local suites are green, then batch fixes. Land by fast-forward on a green "CI result" with no open thread. Stage by name, gitleaks first. CI's security gates are the owner's call.
- Playwright runs locally before each push. CI runs it on main's pushes, weekly and by hand, never on a PR (the owner).

## 3. State (end of 2026-11-18)

- `main` is at `a240ae8`.
- **#78 is open**, branch `k4-typed-client`. Its head is the commit fixing cubic's review of the handoff, after `25400be` (the handoff) and `1c206a1`. Every thread was resolved at close. CI passed on `1acb8f0`; the head's run had just started.
- The last full run: 1,728 passed, 98.53 %. The npm audit allowlist is empty: picomatch's advisory was withdrawn.
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner's.

## 4. The job

1. **Land #78.** Read `mcp__ccd_pr__get_status` and the bots' reviews of the head; fix any new finding with a failing test first. Then `git merge-base --is-ancestor origin/main <sha>` and `git push origin <sha>:refs/heads/main`. Delete the branch, and republish the ledger (`dev plans/progress-ledger/README.md`).
2. **K4.2, the app shell** (contract §2, and §4 item 2), on a new branch.
   - **Backend:** the kernel's pages go in `kernel.json` and its schema. `shell.py` and the router each keep the list in code, held to the manifest by tests (contract change 8; a site doesn't copy `kernel.json`). Refuse a module pattern that matches one. Add `GET /api/kernel/site`.
   - **Web:**
     - `mountApp` (data router); `useSession` wired to `setApiHandlers`; the guards.
     - Typed slots, `useSlot`, `SlotOutlet`; `useModuleEnabled`, `useSite`, `<Seo>`, RouteFocus, ErrorBoundary.
     - The home, 404 and no-access pages.
     - The `[data-server-copy]` CSS.
     - The harness `index.html` with the markers; `testing.ts`.
   - **E2E:** Playwright and axe; the harness with `HARNESS_TEST_SUPPORT=1` and `WEB_DIST`; `kernel/tests/e2e/parity.spec.ts`; the CI job.
3. Then K4.3 to K4.8. Notes for them are in `docs/HANDOFF.md`, Next.

## 5. Ask the owner

- Decisions 0032 to 0039's calls; the R2 test buckets; the desk steps.
- Rename `C:\DEV\AI-DevKit` and the `devkit-*` skills?

## 6. Environment and traps

- **Tests:** `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, in the background. 11 min alone; 19 alongside other database tests.
- After a change to a route or answer: `python -m tools.openapi`, then `npm.cmd run api:types`.
- Bash heredocs turn `\n` in Python strings into newlines: edit escapes with the Edit tool.
- Tools import `harness` first; the root `kernel/` folder is a namespace package.
- Vite's dev proxy sends `Origin: localhost:5173`: writes need DEBUG and `CORS_ORIGINS`.
- cubic reviews every push; Codex reviews when a PR opens (`@codex review` asks again); CodeRabbit skips a PR over 100 files. #78 took 25 findings over four rounds.

## 7. Evidence and next IDs

`docs/HANDOFF.md`, the contract, decision 0042. Next free IDs: decision 0043, PR #79, migration `kernel_0011`.

## 8. Candidates for `knowledge/`

1. `extra="forbid"` answer models as `response_model` catch drift; a hand-built JSONResponse escapes them unless it goes through a checked helper, and a syntax-tree guard catches the aliases.
2. In openapi-fetch, a resend from `onResponse` skips `onError`: use `options.fetch`, catch failures, and key state by `id`.
3. An interface without its own index signature (as openapi-typescript's `paths`) satisfies `Record<string, X>` only when X is `any`.
4. Grep a subagent's claims, such as "tests exist", before writing them into docs.
5. A withdrawn advisory vanishes from npm audit; an allowlist that fails on stale entries catches it the same day.
