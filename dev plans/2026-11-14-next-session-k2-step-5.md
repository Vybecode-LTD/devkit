# Next session: K2 step 5, sign-in codes, magic links and resets

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-14-next-session-k2-step-5.md and follow it, starting with section 4."

## 1. The project

AI DevKit: website modules an agent copies into a site, around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`. Nothing is deployed.

## 2. Rules that aren't in a CLAUDE.md

- **Landing needs the owner's OK for that PR:** once "CI result" is green, `git push origin <sha>:refs/heads/main`, then delete the branch locally and on GitHub. Never push to `main` any other way.
- Commit with the no-reply address on `main` (`git log -1 --format=%ae`). Stage files by name, and run `gitleaks git --pre-commit --staged` first.
- Codes, links and resets are high-risk. Each PR body gets the `auth-threat-model-checklist` table and mutant checks.
- Only the owner touches the Postgres superuser, `pg_hba.conf` (never `trust`) or the execution policy.

## 3. State (verified 2026-11-14)

- `main` is at a753cf1. Sign-up (#39) is the last feature merged.
- **#40** (`docs/handoff-2026-11-14`) holds this file and the handoff, and is the only open PR. If the checkout is still on that branch, ask the owner whether to land #40 once its CI is green, then `git switch main` and `git pull --ff-only`.
- Tests: 496 passed on Linux CI (on Windows, 495 passed and 1 skipped), and 63 xfailed. Nothing is half-done.

## 4. The job, in order (one PR each, tests first)

1. **The local teardown fix** (HANDOFF, Notes). When `WITH (FORCE)` is refused, `conftest._drop` should end its own sessions and run a plain `DROP DATABASE`. It goes first so full runs are reliable here.
2. **Codes and magic links:** `POST /api/auth/code`, `/code/verify` and `/link/confirm` (`docs/contracts/auth-api.md`; SPEC 14.6 and 14.12). Reuse `kernel/auth/tokens.py`. Codes keep their owner in the hash (decision 0012, amended). Staff are sent no code, and get the same answer. Mail goes out after the answer, as in `kernel/auth/sign_up.py`. Unmark each contract test about codes, links and their limits as it passes (`@not_built` in `kernel/tests/contract/test_auth_contract.py`).
3. **Resets:** `password/reset-request` and `password/reset`. A reset token lasts 30 minutes, and a reset ends every session through the epoch. This also lets the real owner of a pre-claimed address back in. Unmark the reset tests.
4. **Resending the verification link** to a signed-in account. It has no contract row, so it needs a decision record, a change-log line, and the owner told which spec sections changed.

## 5. Questions for the owner (ask; don't decide)

- Should a reset mark the address verified, since it proves the inbox?
- What shape should the resend route take (step 4)?
- Desk steps for when the owner is home: reset the Postgres `postgres` password (they type it), and set `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest`. The full suite takes about 6 minutes: run it in the background and log its output to the scratchpad.
- The Bash tool turns `\\` into `\`. Write edit scripts with the Write tool, run them with `.venv/Scripts/python.exe -I`, and keep files' CRLF line endings.
- Codex reviewed only #39's first push. CodeRabbit is on its free tier (memory notes).

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decisions 0012, 0019 and 0020; the threat tables in the bodies of #38 and #39.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0021 and PR #41.

## 8. Candidates for `knowledge/`

1. The Bash tool's `\\` collapse, and edit scripts that keep CRLF (`windows-shell-and-tool-traps`).
2. A role without superuser can't run `DROP DATABASE … WITH (FORCE)` during autovacuum (`pytest-throwaway-postgres`).
3. A per-address mail budget must never block the one message an account needs (`auth-threat-model-checklist`).
4. A timing test's "unknown" input must stay unknown every round (`verify-real-pass`).
5. Codex reviews only a PR's first push (`git-and-ci-traps`).
