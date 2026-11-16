# Next session: the passkey reset gap, a step-up fix, then K2 step 9 (OAuth)

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-16-next-session-k2-step-9.md and follow it, starting with section 4."

## 1. The project

AI DevKit: website modules an agent copies into a site, around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`. Nothing is deployed.

## 2. Rules that aren't in a CLAUDE.md

- **Landing needs the owner's OK for each PR:** once "CI result" is green and the bots have no open findings, `git push origin <sha>:refs/heads/main`, then delete the branch locally and on GitHub. If CodeRabbit is rate-limited, green CI plus Codex's first-push review is enough.
- Commit with the no-reply address on `main` (`git log -1 --format=%ae`). Stage by name; run `gitleaks git --pre-commit --staged` first.
- Auth PRs: tests first, the `auth-threat-model-checklist` table and mutant checks in the PR body. **A route with no contract row needs the owner's answer**, a decision record and a change-log line.
- Only the owner touches the Postgres superuser, `pg_hba.conf` (never `trust`) or the execution policy.

## 3. State (verified 2026-11-16, end of session)

- `main` is at 3933d67 (#50, K2 step 8, passkeys, decision 0028); its branch is deleted.
- **#51** (`docs/k2-step-8-handoff`: the handoff, `CLAUDE.md`/`AGENTS.md`, 0028's index row, this file) is the only open PR.
- Owner's machine: 806 passed, 1 skipped, 27 xfailed, coverage 97.9%; contract suite 123 passed, 27 not built. CI passed on 3933d67. Nothing is half-done.

## 4. The job, in order (one PR each, tests first)

1. If #51 is open, ask the owner whether to land it once "CI result" is green; then `git switch main` and `git pull --ff-only`.
2. **Ask the owner about the reset gap** (`docs/HANDOFF.md`, Open questions, first item): a passkey a thief adds outlives the owner's password reset. If they choose a fix, it's its own PR.
3. **Step-up by TOTP and by password re-check the session after the lock** (`docs/HANDOFF.md`, Next, item 3): `accounts.held` in `routes.py:step_up`, a failing-first test and its mutant.
4. **KICKOFF K2 step 9, OAuth and OpenID Connect** (Authlib, a new dependency: `requirements.in`, re-pin with hashes, `pip-audit`, the Stack line; providers from Basefra.me; PKCE S256, state, nonce; SPEC 14.3). Its contract rows and tests exist (sections 8 and 9); unmark them as they pass.
5. Then steps 10 and 11. A cleanup PR can go anywhere: the five older race tests (`docs/HANDOFF.md`, Next, item 6).

## 5. Questions for the owner (ask; don't decide)

- The reset gap (item 2), and the same for a TOTP a thief adds.
- Keep decision 0028's own calls (20 passkeys, names, user verification preferred as the second factor, limits) and 0026/0027's?
- Eight leftover test databases on the local Postgres: drop them?
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, about 6 to 7 minutes: in the background, logged to the scratchpad. The contract suite alone: 1 minute.
- Git Bash collapses `\\`, runs backticks in double quotes, and `sed -i` strips CRLF: write scripts and PR bodies with the Write tool, run with `.venv/Scripts/python.exe -I`. Write and Edit turn a typed `\u` escape into the real character.
- Mutants: a scratchpad script swaps one string, runs the named tests and restores the file.
- Reuse `accounts.held`, `test_passkeys.py:_with_the_account_held` and the fake authenticator (`kernel/tests/contract/authenticator.py`).

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decision 0028; #50's body (threat table, 23 mutants) and its review replies (3 more).
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0029 and PR #52.

## 8. Candidates for `knowledge/`

1. Write and Edit decode `\u` escapes; build them with `chr(92)` (`windows-shell-and-tool-traps`).
2. A route that waits on a lock re-checks its session after it (`auth-threat-model-checklist`).
3. Race tests: hold the row until the requests that reach the lock wait; probe with NOWAIT (`verify-real-pass`).
4. A fake WebAuthn authenticator, checked against the library's verifier, for HTTP-level passkey tests.
