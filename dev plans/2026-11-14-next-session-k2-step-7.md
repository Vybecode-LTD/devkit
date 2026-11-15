# Next session: K2 step 7, second factors

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-14-next-session-k2-step-7.md and follow it, starting with section 4."

## 1. The project

AI DevKit: website modules an agent copies into a site, around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`. Nothing is deployed.

## 2. Rules that aren't in a CLAUDE.md

- **Landing needs the owner's OK for each PR:** once "CI result" is green and the bots have no open findings, `git push origin <sha>:refs/heads/main`, then delete the branch locally and on GitHub.
- Commit with the no-reply address on `main` (`git log -1 --format=%ae`). Stage files by name, and run `gitleaks git --pre-commit --staged` first.
- Auth PRs: tests first, the `auth-threat-model-checklist` table and mutant checks in the PR body. A route with no contract row needs the owner's answer on its shape, a decision record and a change-log line.
- Only the owner touches the Postgres superuser, `pg_hba.conf` (never `trust`) or the execution policy.

## 3. State (verified 2026-11-14, evening)

- `main` is at a60f87f (#45, email change). #41 to #45 are merged.
- **#46** (`feat/k2-password-change`) holds password change, this file and the handoff, and is the only open PR. Its CI hadn't reported when this was written.
- Tests on the owner's machine: 681 passed, 1 skipped, 41 xfailed. Nothing is half-done.

## 4. The job, in order (one PR each, tests first)

1. If #46 is open, ask the owner whether to land it once "CI result" is green; then `git switch main` and `git pull --ff-only`.
2. **TOTP setup and confirm:** `POST /api/auth/totp/setup` (step-up; 403 `auth.email_unverified` until verified) and `/totp/confirm` (10 recovery codes). The contract rows exist (`docs/contracts/auth-api.md`). Flip the routes' `_step_up(..., built=True)` in `kernel/tests/contract/test_auth_contract.py`, and unmark `test_an_unverified_account_adds_no_second_factor` and `test_an_unconfirmed_totp_is_no_second_factor` as they pass.
3. **`DELETE /api/auth/totp`** and **`POST /api/auth/recovery-codes`** (both step-up; 409 `auth.no_second_factor`).
4. Then KICKOFF K2 steps 8 to 11. A cleanup PR can go anywhere: the five older race tests (`docs/HANDOFF.md`, Next, item 4).

## 5. Questions for the owner (ask; don't decide)

- Does removing a TOTP count as the "second-factor reset" that SPEC 14.5 says raises the session epoch, ending every other session?
- Five leftover test databases on the local Postgres: drop them?
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest`. The full run takes about 6 minutes: run it in the background, logging to the scratchpad.
- Git Bash collapses `\\`, runs backticks inside double quotes, and `sed -i` strips CRLF. Write edit scripts and PR bodies with the Write tool, run them with `.venv/Scripts/python.exe -I`, and keep files' CRLF.
- A mutant runner needs the interpreter's full path (Windows `CreateProcess`).
- Patterns to reuse: `accounts.lock` before token or session rows, `tokens.void`, `floor.wait_out`, `_with_the_account_held` (`kernel/tests/auth/test_resets.py`).
- Codex reviews a PR's first push only; CodeRabbit's free tier runs out.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decisions 0021 to 0025; the threat tables in the bodies of #42 to #46.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\` (`race-tests-that-really-race`).
- Next free IDs: decision 0026 and PR #47.

## 8. Candidates for `knowledge/`

1. Race tests that really race: a warm pool, separate browsers, or hold the row and probe with NOWAIT (`verify-real-pass`).
2. A timing test must take the expensive path every round (`verify-real-pass`).
3. One lock order, the account row before its token and session rows, or the bots find deadlocks (`auth-threat-model-checklist`).
4. Flush a write a unique index guards inside its handler, or the race is a 500 (`supabase-auth-and-rls-traps` or a Postgres skill).
5. Git Bash: `sed -i` strips CRLF, and backticks in double quotes run (`windows-shell-and-tool-traps`).
