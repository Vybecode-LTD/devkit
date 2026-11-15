# Handoff

Overwritten every session. 2026-11-15 (Claude Code, the owner's machine): K2 step 7, second factors, in #47 and #48, both landed. `main` is at 134061f (#48). **#49 holds this page and the next starting prompt.**

## State

- **K0 and K1 done and audited** (2026-11-12; 55 findings fixed in #1 to #24, the report in `docs/private/`). The owner's follow-ups: #25 to #31.
- **K2 so far** (each PR body has its threat-model table and mutant checks):
  - Passwords, keyed hashes, every auth table, sessions, access dependencies, the mail interface, sign-in and sign-up (#32 to #39; decisions 0012, 0013, 0019, 0020).
  - Sign-in codes and magic links (#42, 0021); password resets (#43, 0022); a new verification link (#44, 0023); email change (#45, 0024); password change (#46, 0025).
  - **TOTP setup and confirm** (#47, `kernel/auth/totp.py`, decision 0026). Setup: step-up, a verified address, 409 `auth.totp_exists` over a confirmed TOTP. Confirm: the code's step is used up, 10 new recovery codes (`xxxxx-xxxxx`, keyed hashes), a wrong code counts as a failed step-up, 409 `auth.no_pending_totp`.
  - **TOTP removal and new recovery codes** (#48, decision 0027). Removing a confirmed TOTP is the second-factor reset (the owner's answer): its codes go, every other session ends, this one keeps a fresh device cookie, live ways in are voided. New codes need a confirmed TOTP and are mailed. Every TOTP route gives way to a reset that lands while it waits.
- **One lock order everywhere:** a route that touches an account's token, session, TOTP or recovery-code rows locks the account row first (`accounts.lock`, decisions 0021 and 0027). Sign-in's second-factor step and step-up by TOTP now take it before checking the code.
- **A replaced session's cookie** (after a role change) waits for `SessionCookies` as plain values, not the session row, so a route's rollback can't break it (#48, Codex).
- **Tests:** 735 Python tests pass on Windows (1 skipped; 736 on Linux CI) and 32 strict expected failures; coverage 96.8% (CI fails under 85%); CI passed on 134061f. The contract suite: 85 passed, 32 not built; the step-up cases are marked per action (`_step_up(..., built=True)`).
- **GitHub:** public `Vybecode-LTD/devkit`. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green, only with the owner's OK for that PR. The ruleset requires "CI result" and blocks force pushes. Codex reviews a PR's first push only; CodeRabbit's free tier runs out (it did on #48).

## Next

1. If #49 is still open, ask the owner to land it once "CI result" is green.
2. **KICKOFF K2 step 8, passkeys** (the `webauthn` library, discoverable credentials, user verification when it's the only factor; SPEC 14.2 and 14.4, `auth_passkey` in 14.11). The contract has registration (`/passkeys/register/start`, `/finish`) and `DELETE /passkeys/{id}`, but **no row for signing in with a passkey**, neither alone nor as a second factor: ask the owner for that shape first (a decision record and a change-log line). `webauthn` is a new dependency: add it to `requirements.in`, re-pin with hashes, run `pip-audit`, and list it in the Stack. Unmark the passkey case of `test_an_unverified_account_adds_no_second_factor` as it passes. Take the account lock before the passkey row.
3. Then step 9 (OAuth), 10 (API keys and invites), 11 (lifecycle: deletion, export). `test_an_unconfirmed_totp_is_no_second_factor` waits for the admin routes.
4. A PR of its own: the race tests in `test_sessions.py`, `test_sign_in.py`, `test_sign_up.py`, `test_db.py` and `test_settings.py` may never overlap (a cold pool, one browser). Apply the memory note `race-tests-that-really-race` and rerun their mutants.

After K2 and the kernel phases: the ten contract hooks of decision 0018 (`skills/devkit-hook-designer`), before blog, chat and payments are extracted.

## Open questions for the owner

- A TOTP added by whoever stole the password outlives the owner's reset (14.7 leaves the second factor in place), so the owner is then asked for the thief's codes. The "added" mail says to reset and ask the site to remove it. Add an undo link to that mail, as email change has, or leave it to staff?
- Decisions 0026 and 0027 settled what the contract rows left open (409 `auth.totp_exists`, 409 `auth.no_pending_totp`, a wrong confirm code as a failed step-up, new recovery codes mailed, staff may remove their TOTP): keep them?
- The shape of passkey sign-in (Next, item 2).
- Six throwaway test databases left by killed runs are on the local Postgres (`devkit_test_*`, `devkit_empty_*`; five before this session). Drop them?
- Desk steps: reset the Postgres `postgres` password (the owner types it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if wanted.

## Notes

- **Race and lock-order tests must really race:** hold the account row until every request waits on it, and probe with `FOR UPDATE NOWAIT` (`test_totp.py:_with_the_account_held`, which also takes several requests and a `meanwhile` change). Run each new guard's mutant.
- **Never hand an ORM row past the route** (middleware, background tasks): a rollback expires it. A test of a rollback path must query first, since a rollback with nothing begun expires nothing (memory note `rollback-expires-orm-rows`).
- **A contract test can pass by another path:** with removal keeping the recovery codes, the contract test still passed, because confirming the next TOTP replaced them; only the kernel test saw it. Check which test kills each mutant.
- **TOTP tests:** read the clock once for a code and its step; a second sign-in in the same step needs the next step's code (`_next_step`), or it's a replay.
- **A unique index only answers 400 if the write is flushed inside the handler** (`email_change._write_address`).
- **Mail goes out after the answer and isn't retried** until K3's job queue. Unverified accounts are removed after 7 days once K3's jobs exist.
- **Every request body is strict** (`test_app.py::test_every_request_body_is_strict`). `require_owner_or` gives a guard; the route must call `await guard.check(owner_id)`. TOTP runs on real time, not `kernel.clock`.
- **React Router stays on 7; TypeScript stays on 6.0.x.** FastAPI 0.162: walk routes with `fastapi.routing.iter_route_contexts`.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
- On this machine, Git Bash's `sed -i` strips CRLF and backticks inside double quotes run as commands: edit with scripts written by the Write tool, and write PR bodies to a file.
