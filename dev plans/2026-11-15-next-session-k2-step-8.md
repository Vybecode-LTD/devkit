# Next session: K2 step 8, passkeys

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-15-next-session-k2-step-8.md and follow it, starting with section 4."

## 1. The project

AI DevKit: website modules an agent copies into a site, around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`. Nothing is deployed.

## 2. Rules that aren't in a CLAUDE.md

- **Landing needs the owner's OK for each PR:** once "CI result" is green and the bots have no open findings, `git push origin <sha>:refs/heads/main`, then delete the branch locally and on GitHub. If CodeRabbit is rate-limited, green CI plus Codex is enough.
- Commit with the no-reply address on `main` (`git log -1 --format=%ae`). Stage files by name, and run `gitleaks git --pre-commit --staged` first.
- Auth PRs: tests first, the `auth-threat-model-checklist` table and mutant checks in the PR body. **A route with no contract row needs the owner's answer on its shape**, a decision record and a change-log line.
- Only the owner touches the Postgres superuser, `pg_hba.conf` (never `trust`) or the execution policy.

## 3. State (verified 2026-11-15, end of session)

- `main` is at 134061f (#48). #47 and #48 (K2 step 7, second factors) are merged; their branches are deleted.
- **#49** (`docs/k2-step-7-handoff`) holds `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md` and this file, and is the only open PR.
- Tests on the owner's machine: 735 passed, 1 skipped, 32 xfailed, coverage 96.8%; CI passed on 134061f. Nothing is half-done.

## 4. The job, in order (one PR each, tests first)

1. If #49 is open, ask the owner whether to land it once "CI result" is green; then `git switch main` and `git pull --ff-only`.
2. **Ask the owner for the shape of passkey sign-in** first. The contract has only registration and `DELETE /passkeys/{id}`: nothing for a passkey as the only factor (SPEC 14.2) or as a second factor (`methods` already lists `passkey`). Propose routes and answers; they choose.
3. **KICKOFF K2 step 8, passkeys** (`webauthn`, discoverable credentials, named passkeys; SPEC 14.2, 14.4, 14.11). A new dependency: `requirements.in`, re-pin with hashes, `pip-audit`, the Stack line. Unmark the passkey case of `test_an_unverified_account_adds_no_second_factor` as it passes. Lock the account before the passkey row (decision 0027).
4. Then KICKOFF K2 steps 9 to 11. A cleanup PR can go anywhere: the five older race tests (`docs/HANDOFF.md`, Next, item 4).

## 5. Questions for the owner (ask; don't decide)

- The shape of passkey sign-in (item 2); whether removing the last passkey ends other sessions, as removing a TOTP does.
- A TOTP a thief adds outlives the owner's reset. An undo link in the "added" mail, or leave it to staff?
- Keep decisions 0026 and 0027's calls (`docs/HANDOFF.md`, Open questions)?
- Six leftover test databases on the local Postgres: drop them?
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest`. The full run takes about 6 minutes: run it in the background, logging to the scratchpad.
- Git Bash collapses `\\`, runs backticks inside double quotes, and `sed -i` strips CRLF. Write edit scripts and PR bodies with the Write tool and run them with `.venv/Scripts/python.exe -I`.
- Mutants: a scratchpad script that swaps one string, runs the named tests and restores the file (the interpreter's full path). Don't edit those files while it runs.
- Reuse `test_totp.py:_with_the_account_held` and `totp._held`. Never hand an ORM row to middleware or a background task (memory note).

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decisions 0026 and 0027; the threat tables in #47 and #48.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\` (`race-tests-that-really-race`, `rollback-expires-orm-rows`).
- Next free IDs: decision 0028 and PR #50.

## 8. Candidates for `knowledge/`

1. Never hand an ORM row past the route; a rollback test must query first (a SQLAlchemy skill).
2. Race tests: hold the row until every request waits, probe with NOWAIT (`verify-real-pass`).
3. Check which test kills each mutant: a contract test can pass by another path (`verify-real-pass`).
4. One lock order, the account first, sign-in's code checks included (`auth-threat-model-checklist`).
5. Git Bash: `sed -i` strips CRLF; backticks in double quotes run (`windows-shell-and-tool-traps`).
