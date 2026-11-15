# Handoff

Overwritten every session. 2026-11-14 (Claude Code, the owner's machine, mostly over Remote Control): the local teardown fix, then K2 steps 5 and 6 and password change, #41 to #46. `main` is at a60f87f (#45); **#46 holds password change and this handoff.**

## State

- **K0 and K1 done and audited** (2026-11-12; 55 findings fixed in #1 to #24, the report in `docs/private/`). The owner's follow-ups: #25 to #31.
- **K2 so far** (each PR body has its threat-model table and mutant checks):
  - Passwords, keyed hashes, every auth table, sessions, access dependencies, the mail interface, sign-in and sign-up (#32 to #39; decisions 0012, 0013, 0019, 0020).
  - **Sign-in codes and magic links** (#42, `kernel/auth/codes.py`, decision 0021). Members only; one live mail per account; a member with a second factor still gives it; answers no sooner than 0.2 s (`kernel/auth/floor.py`).
  - **Password resets** (#43, `resets.py`, decision 0022). They mark the address verified (the owner's answer) and end every way in. Sign-in gives way to a reset in flight.
  - **A new verification link** (#44, `sign_up.py`, decision 0023): `POST /api/auth/verify-email/resend`, the shape the owner approved.
  - **Email change** (#45, `email_change.py`, decision 0024): change (step-up), confirm and undo, the shape the owner approved. Earlier undo links always survive; a change link is bound to the session epoch.
  - **Password change** (#46, `password_change.py`, decision 0025). It keeps its own session with a fresh device cookie; a wrong current password counts as a failed step-up; it gives way to a reset.
- **One lock order everywhere:** a route that touches an account's token or session rows locks the account row first (`accounts.lock`, decision 0021). Every deadlock the bots found was a route that took them the other way.
- **Tests:** 681 Python tests pass on Windows (1 skipped; 682 on Linux CI) and 41 strict expected failures; coverage 96.8% (CI fails under 85%). The contract suite: 60 passed, 41 not built. The step-up contract tests are marked per action (`_step_up(..., built=True)`).
- **GitHub:** public `Vybecode-LTD/devkit`. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green, only with the owner's OK for that PR. The ruleset requires "CI result" and blocks force pushes. Codex reviews a PR's first push only; CodeRabbit is on its free tier and hits its limit.

## Next

1. If #46 is still open, ask the owner to land it once "CI result" is green.
2. **KICKOFF K2 step 7, second factors:** `POST /api/auth/totp/setup` (step-up; 403 `auth.email_unverified` until verified), `/totp/confirm` (10 recovery codes), `DELETE /api/auth/totp` (step-up), `POST /api/auth/recovery-codes` (step-up; 409 `auth.no_second_factor`). The contract rows exist. Flip each route's `_step_up(..., built=True)` and unmark `test_an_unverified_account_adds_no_second_factor` and `test_an_unconfirmed_totp_is_no_second_factor` as they pass.
3. Then step 8 (passkeys), 9 (OAuth), 10 (API keys and invites), 11 (lifecycle: deletion, export).
4. A PR of its own: the race tests in `test_sessions.py`, `test_sign_in.py`, `test_sign_up.py`, `test_db.py` and `test_settings.py` may never overlap (a cold pool, one browser). Apply the memory note `race-tests-that-really-race` and rerun their mutants.

After K2 and the kernel phases: the ten contract hooks of decision 0018 (`skills/devkit-hook-designer`), before blog, chat and payments are extracted.

## Open questions for the owner

- Does removing a TOTP (`DELETE /api/auth/totp`) count as the "second-factor reset" that 14.5 says raises the session epoch, ending every other session?
- Five throwaway test databases left by killed runs are still on the local Postgres (`devkit_test_*`, `devkit_empty_*`). Drop them?
- Desk steps: reset the Postgres `postgres` password (the owner types it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if wanted.

## Notes

- **Race and lock-order tests must really race:** a warm pool, separate browsers, or hold the row and probe with `FOR UPDATE NOWAIT` (memory note; `test_resets.py:_with_the_account_held`). Run each new guard's mutant; four survived for want of that.
- **A unique index only answers 400 if the write is flushed inside the handler** (`email_change._write_address`). Left to a later query's autoflush, the violation becomes a 500.
- **A timing test must take the expensive path every round:** the code test passed hollowly until each round moved the clock past the resend wait and checked that mail went out.
- **Mail goes out after the answer and isn't retried** until K3's job queue. The contract suite's mail reads wait up to 5 s (`Api.mail(at_least=)`, `Api.new_token`) for a running server.
- **Every request body is strict** (`test_app.py::test_every_request_body_is_strict`).
- **`conftest._drop`** falls back to ending its own sessions when `WITH (FORCE)` is refused during autovacuum (#41).
- **Unverified accounts are removed after 7 days,** and `auth.user.verified` is emitted, once K3's jobs and events exist.
- **`require_owner_or` gives a guard; the route must call `await guard.check(owner_id)`.**
- **TOTP runs on real time,** not `kernel.clock`.
- **React Router stays on 7; TypeScript stays on 6.0.x.** FastAPI 0.162: walk routes with `fastapi.routing.iter_route_contexts`.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
- On this machine, Git Bash's `sed -i` strips CRLF and backticks inside double quotes run as commands: edit with scripts written by the Write tool, and write PR bodies to a file.
