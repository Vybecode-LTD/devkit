# Handoff

Overwritten every session. 2026-11-16 (Claude Code, the owner's machine): K2 step 8, passkeys, in #50, landed, then this page in #51. Later that day: the step-up fix (#52), and the Vibrant Mindz modules moved to the front (decision 0029, #53).

## State

- **K0 and K1 done and audited** (2026-11-12; 55 findings fixed in #1 to #24, the report in `docs/private/`). The owner's follow-ups: #25 to #31.
- **K2 so far** (each PR body has its threat-model table and mutant checks):
  - Passwords, keyed hashes, every auth table, sessions, access dependencies, the mail interface, sign-in and sign-up (#32 to #39; decisions 0012, 0013, 0019, 0020).
  - Sign-in codes and magic links (#42, 0021); password resets (#43, 0022); a new verification link (#44, 0023); email change (#45, 0024); password change (#46, 0025).
  - TOTP setup and confirm (#47, 0026); TOTP removal and new recovery codes (#48, 0027).
  - **Passkeys** (#50, decision 0028; `kernel/auth/passkeys.py`, `ceremonies.py`; `webauthn` 3.0.1). The owner's answers: a passkey alone signs anyone in, staff included, with user verification required; as a second factor (`/sign-in/second-factor/passkey` gives the options) and at step-up (`/step-up/passkey`) it answers options from a start route; **removing any passkey is a second-factor reset**; `GET /passkeys` and `PATCH /passkeys/{id}` (step-up) list and rename. Up to 20 passkeys. Challenges are keyed hashes in `auth_token` (migration `kernel_0003`), live 5 minutes, used once; registration and step-up challenges are bound to the session. Sign counts catch a cloned key; the user handle must be the account's.
- **One lock order everywhere:** the account row first (`accounts.lock`). `accounts.held` (moved from `totp._held`) locks it and re-reads the user and session, so a reset that lands while a route waits wins with 401.
- **Tests:** 806 Python tests pass on Windows (1 skipped) and 27 strict expected failures; coverage 97.9% (CI fails under 85%). CI passed on 3933d67. The contract suite on `main`: 123 passed, 27 not built. The tests' authenticator is `kernel/tests/contract/authenticator.py` (ES256, `none` attestation), checked against `webauthn`'s own verifier.
- **GitHub:** public `Vybecode-LTD/devkit`. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green, only with the owner's OK for that PR. Codex reviews a PR's first push only; CodeRabbit's free tier ran out on #50's fix commit.

## Next

**The order changed on 2026-11-16: the Vibrant Mindz site's modules come first (decision 0029).** The site's own sessions are waiting on them.

1. #52 (the step-up fixes) and #53 (this order) landed on 2026-11-16.
2. **The passkey reset gap is closed by #54** (landed; the owner's answer, decision 0030): the mail for an added passkey or TOTP carries a 7-day undo link that removes it, ends every session and outlives resets.
3. **The site's step 0:** the scaffold is in **#55** (7 modules waiting as `modules/_<id>/`, the recipe, `docs/plans/vibrant-mindz-backend/`); this repo's copy is the one kept up to date from now on. Items 1 and 2 of its `kernel-additions.md` are in **#56** (decision 0031): `kernel.moderation.act` declared and granted to admin and editor (migration `kernel_0005`), and a test pinning that a custom role is staff. Items 3 to 6 (storage keys, ffmpeg jobs, the oEmbed guard, CSP) come with K3 and the modules.
4. **K3**, the kernel services, in the order the site's modules use them: storage, email, jobs, events, audit, notifications, moderation, public rendering (`KICKOFF.md`, K3). Retention and the AI client later.
5. **K4**, the web kernel, with the site's theme; then **K5**, the CLI and the site template (`devkit new`, `devkit check`).
6. **The ten hooks of decision 0018** (`skills/devkit-hook-designer`), before blog is extracted.
7. **The site's steps 1 to 7** (`docs/plans/vibrant-mindz-backend/KICKOFF.md` once step 0 lands): content modules, players, comments and roster, community, then payments, shop and downloads (the launch), licensing, print on demand.
8. **K2's last steps, where the site needs them:** step 10's invites before the site's step 4; steps 9 (OAuth: Authlib, PKCE, state, nonce, SPEC 14.3; its contract tests are written as expected failures) and 11 (deletion, export, abuse protection) before the launch at the site's step 5. API keys after. `test_an_unconfirmed_totp_is_no_second_factor` waits for the admin routes.
9. Any time, a PR of its own: the race tests in `test_sessions.py`, `test_sign_in.py`, `test_sign_up.py`, `test_db.py` and `test_settings.py` may never overlap (a cold pool, one browser). Apply the memory note `race-tests-that-really-race` and rerun their mutants.

## Open questions for the owner

- Answered 2026-11-16: a passkey or TOTP a thief adds is undone by a link in its mail (decision 0030, #54). Decision 0030's own calls: the link lives 7 days, ends every session even when its factor is already gone, binds a TOTP link to that TOTP's confirm time, and doesn't change the password. Keep them?
- Decision 0028 settled what the owner's answers left open: 20 passkeys at most (409 `auth.too_many_passkeys`), names of 1 to 80 characters with no control characters, user verification preferred (not required) for a passkey as the second factor, 5-minute challenges, 10 passkey sign-ins per IP per minute. Keep them? And 0026 and 0027's calls (409 `auth.totp_exists`, 409 `auth.no_pending_totp`, a wrong confirm code as a failed step-up, new recovery codes mailed, staff may remove their TOTP)?
- Eight throwaway test databases left by killed runs are on the local Postgres (`devkit_test_*`, `devkit_empty_*`; six before this session). Drop them?
- Desk steps: reset the Postgres `postgres` password (the owner types it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if wanted.

## Notes

- **Race and lock-order tests must really race:** hold the account row until every request waits on it, and probe with `FOR UPDATE NOWAIT` (`test_passkeys.py:_with_the_account_held` takes `probe_row`, `meanwhile` and `waiting`, for when only some requests reach the lock). Run each new guard's mutant.
- **Never hand an ORM row past the route** (middleware, background tasks): a rollback expires it (memory note `rollback-expires-orm-rows`).
- **Passkey contract tests:** once an account has a passkey, a password sign-in asks for a second factor, so a second browser signs in with the passkey (`_sign_in_by_passkey`). A route's path parameter named `id` is `Path(alias="id")`, so the route template matches the contract.
- **Write and Edit decode `\u` escapes** into the real character (memory note `tool-params-decode-unicode-escapes`): write such escapes from a script with `chr(92)`.
- **A contract test can pass by another path:** check which test kills each mutant.
- **Mail goes out after the answer and isn't retried** until K3's job queue. Unverified accounts are removed after 7 days once K3's jobs exist.
- **Every request body is strict** (`test_app.py::test_every_request_body_is_strict`). TOTP runs on real time, not `kernel.clock`.
- **React Router stays on 7; TypeScript stays on 6.0.x.** FastAPI 0.162: walk routes with `fastapi.routing.iter_route_contexts`. `--cov=kernel` works; `--cov=kernel.auth` breaks setup.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
- On this machine, Git Bash's `sed -i` strips CRLF, backticks inside double quotes run as commands, and `\\` collapses: edit with scripts written by the Write tool, and write PR bodies to a file.
