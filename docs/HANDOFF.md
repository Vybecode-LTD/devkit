# Handoff

Overwritten every session. 2026-11-16, later (Claude Code, the owner's machine, partly over Remote Control): the step-up fixes (#52), the Vibrant Mindz modules moved to the front (decision 0029, #53), the undo link for an added passkey or TOTP (#54, decision 0030), and the site's step 0 (#55, #56, decision 0031). Then this page (#57).

## State

- **K0 and K1 done and audited** (2026-11-12; 55 findings fixed in #1 to #24, the report in `docs/private/`). The owner's follow-ups: #25 to #31.
- **K2 so far** (each PR body has its threat-model table and mutant checks):
  - Passwords, keyed hashes, every auth table, sessions, access dependencies, the mail interface, sign-in and sign-up (#32 to #39; decisions 0012, 0013, 0019, 0020).
  - Sign-in codes and magic links, resets, a new verification link, email change, password change (#42 to #46; 0021 to 0025).
  - TOTP and recovery codes (#47, #48; 0026, 0027); passkeys (#50, 0028; `passkeys.py`, `ceremonies.py`, `webauthn` 3.0.1).
  - Step-up by TOTP or password locks the account and re-checks the session (`accounts.held`, #52); `held` reads the session's epoch only, so the token's compare-and-swap keeps the hash it started with.
  - **An added passkey or TOTP is undone from its mail** (#54, decision 0030; `kernel/auth/factor_undo.py`, migration `kernel_0004`): a 7-day link removes that factor, ends every session, voids open codes and links, and outlives resets.
- **The site's step 0 is done.** The scaffold (#55): seven modules waiting as `modules/_<id>/`, the recipe `recipes/collective-with-store.json`, the backend plan in `docs/plans/vibrant-mindz-backend/` (this repo's copy is the one kept current). Then `kernel.moderation.act`, granted to admin and editor (migration `kernel_0005`), and a test pinning that a custom role is staff (#56, decision 0031). Items 3 to 6 of `kernel-additions.md` come with K3 and the modules.
- **One lock order everywhere:** the account row first (`accounts.lock`); `accounts.held` locks it and re-checks the user and the session, so a reset that lands while a route waits wins with 401.
- **Tests:** 823 Python tests pass on Windows (1 skipped) and 27 strict expected failures; coverage 97.0% (CI fails under 85%). CI passed on b9a6939. The contract suite on `main`: 128 passed, 27 not built (OAuth and the rest of K2).
- **GitHub:** public `Vybecode-LTD/devkit`. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green, only with the owner's OK for that PR. Codex reviews a PR's first push only. CodeRabbit is on its free tier and skips a PR of more than 100 files; a PR stacked on another counts both.

## Next

The order is decision 0029's; the site's own sessions wait on it.

1. **K3, the kernel services**, in the order the site's modules use them (`KICKOFF.md`, K3; SPEC 6, 9, 11 and 15). One PR per service, tests first.
   - **Storage first:** `storage.put / get / signed_url` (SPEC 6), boto3 against an S3-compatible store (SPEC 2, Cloudflare R2). Private files only through short-lived signed links; a file a provider must fetch gets an unguessable link that expires with its job (SPEC 15); the site's public and private keys (`kernel-additions.md`, item 3). How it's tested is the owner's call (Open questions).
   - Then **email** (the real adapter behind `kernel/email.py`'s `Mailer`: SMTP, Mailgun, Resend), **jobs** (the Postgres queue; mail moves onto it and gains retries; unverified accounts are removed after 7 days; ffmpeg in the worker image, item 4), **events** (the outbox, dispatcher and dead letters, SPEC 11), **audit** (widened from `kernel/auth/audit.py`), **notifications**, **moderation** (the permission exists), **public rendering** (SPEC 9; the CSP additions, item 6). The outbound guard for oEmbed (item 5) comes with the first service that fetches a URL. Retention and the AI client later.
   - Gate: tests for each service, an event delivered once to a handler that's safe to run twice, and a job that survives a worker restart.
2. **K4**, the web kernel, with the site's theme; then **K5**, the CLI and the site template.
3. **The ten hooks of decision 0018** (`skills/devkit-hook-designer`), before blog is extracted.
4. **The site's steps 1 to 7** (`docs/plans/vibrant-mindz-backend/KICKOFF.md`): each builds a waiting `modules/_<id>/` and renames it.
5. **K2's last steps, where the site needs them:** step 10's invites before the site's step 4; steps 9 (OAuth, SPEC 14.3; its contract tests are written as expected failures) and 11 (deletion, export, abuse protection) before the launch at the site's step 5. API keys after. `test_an_unconfirmed_totp_is_no_second_factor` waits for the admin routes.
6. Any time, a PR of its own: the race tests in `test_sessions.py`, `test_sign_in.py`, `test_sign_up.py`, `test_db.py` and `test_settings.py` may never overlap (a cold pool, one browser). Apply the memory note `race-tests-that-really-race` and rerun their mutants.

## Open questions for the owner

- **Storage tests:** an in-process fake of S3 (moto: a new dev dependency, nothing to run) or a local MinIO (a service on their machine and in CI)?
- Decision 0030's own calls: the undo link lives 7 days, ends every session even when its factor is already gone, binds a TOTP link to that TOTP's confirm time, and doesn't change the password. Keep them?
- Decision 0028's own calls (20 passkeys at most, names of 1 to 80 characters, user verification preferred for a passkey as the second factor, 5-minute challenges, 10 passkey sign-ins per IP per minute) and 0026 and 0027's (409 `auth.totp_exists` and `auth.no_pending_totp`, a wrong confirm code as a failed step-up, new recovery codes mailed, staff may remove their TOTP). Keep them?
- Eight throwaway test databases left by killed runs are on the local Postgres (`devkit_test_*`, `devkit_empty_*`). Drop them?
- Desk steps: reset the Postgres `postgres` password (the owner types it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if wanted.

## Notes

- **A waiting module is skipped by the harness only** (`harness/layout.py`), so its `requires` and models can't break the app or the migrations until its step renames it. mypy, ESLint and `tsc` still check its code (they exclude only `_template`), so it has to keep passing them.
- **Race and lock-order tests must really race:** hold the account row until every request waits on it, and probe with `FOR UPDATE NOWAIT` (`test_passkeys.py:_with_the_account_held`). Run each new guard's mutant.
- **Never hand an ORM row past the route** (middleware, background tasks): a rollback expires it (memory note `rollback-expires-orm-rows`).
- **Write and Edit decode `\u` escapes** into the real character (memory note `tool-params-decode-unicode-escapes`).
- **A contract test can pass by another path:** check which test kills each mutant.
- **Mail goes out after the answer and isn't retried** until K3's job queue.
- **Every request body is strict** (`test_app.py::test_every_request_body_is_strict`). TOTP runs on real time, not `kernel.clock`.
- **React Router stays on 7; TypeScript stays on 6.0.x.** FastAPI 0.162: walk routes with `fastapi.routing.iter_route_contexts`. `--cov=kernel` works; `--cov=kernel.auth` breaks setup.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
- On this machine, Git Bash's `sed -i` strips CRLF, backticks inside double quotes run as commands, and `\\` collapses: edit with scripts written by the Write tool, and write PR bodies to a file.
