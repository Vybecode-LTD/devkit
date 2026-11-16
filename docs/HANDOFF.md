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
- **K3 has started: storage** (#58, decision 0032; `kernel/storage.py`, contract `dev plans/contracts/k3-storage.md`). A private bucket reached only through signed links, an optional public one at `STORAGE_PUBLIC_URL`, unguessable keys for a provider's files, inline only for five raster types whose bytes match. Tested with moto; `kernel/tests/test_storage_live.py` runs against a real store when `TEST_STORAGE_*` is set, and is skipped until the owner makes test buckets. Contract change: `check_key` is public, and `signed_url` always signs `attachment` (the contract's dated lines).
- **Email** (#59, decision 0033; `kernel/email.py`, `kernel/mail_adapters.py`, contract `dev plans/contracts/k3-email.md`). `email.send(template, to, context)` renders a module's template (`emails.py`'s `EMAILS`, named `<id>.<name>`), which a site may reword through `create_app(emails=...)`; SMTP comes first (`SMTP_HOST` set); Resend, the owner's choice of HTTPS API, is used only where the host blocks SMTP (`RESEND_API_KEY` without `SMTP_HOST`), the owner's rule. Failures are `MailError` with `retryable`, for K3's jobs. Contract changes: templates live in `emails.py`'s `EMAILS`, a fixed name the harness finds; `MAIL_ADAPTER` is gone (SMTP first).
- **One lock order everywhere:** the account row first (`accounts.lock`); `accounts.held` locks it and re-checks the user and the session, so a reset that lands while a route waits wins with 401.
- **Tests:** 823 Python tests pass on Windows (1 skipped) and 27 strict expected failures; coverage 97.0% (CI fails under 85%). CI passed on b9a6939. The contract suite on `main`: 128 passed, 27 not built (OAuth and the rest of K2).
- **GitHub:** public `Vybecode-LTD/devkit`. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green, only with the owner's OK for that PR. Codex reviews a PR's first push only. CodeRabbit is on its free tier and skips a PR of more than 100 files; a PR stacked on another counts both.

## Next

The order is decision 0029's; the site's own sessions wait on it.

1. **K3, the kernel services**, in the order the site's modules use them (`KICKOFF.md`, K3; SPEC 6, 9, 11 and 15). One PR per service, tests first.
   - **Storage is done** (#58). Uploads straight from the browser (a signed PUT: R2 has no POST policy), type detection and Pillow re-encoding come with discography and the first module that takes images (the contract's non-goals).
   - **Email is done** (#59). Next, in its own PR: K2's nine auth mails move onto `kernel.*` templates, so a site can reword them.
   - Then **jobs** (the Postgres queue; mail moves onto it and gains retries; unverified accounts are removed after 7 days; ffmpeg in the worker image, item 4), **events** (the outbox, dispatcher and dead letters, SPEC 11), **audit** (widened from `kernel/auth/audit.py`), **notifications**, **moderation** (the permission exists), **public rendering** (SPEC 9; the CSP additions, item 6). The outbound guard for oEmbed (item 5) comes with the first service that fetches a URL. Retention and the AI client later.
   - Gate: tests for each service, an event delivered once to a handler that's safe to run twice, and a job that survives a worker restart.
2. **K4**, the web kernel, with the site's theme; then **K5**, the CLI and the site template.
3. **The ten hooks of decision 0018** (`skills/devkit-hook-designer`), before blog is extracted.
4. **The site's steps 1 to 7** (`docs/plans/vibrant-mindz-backend/KICKOFF.md`): each builds a waiting `modules/_<id>/` and renames it.
5. **K2's last steps, where the site needs them:** step 10's invites before the site's step 4; steps 9 (OAuth, SPEC 14.3; its contract tests are written as expected failures) and 11 (deletion, export, abuse protection) before the launch at the site's step 5. API keys after. `test_an_unconfirmed_totp_is_no_second_factor` waits for the admin routes.
6. Any time, a PR of its own: the race tests in `test_sessions.py`, `test_sign_in.py`, `test_sign_up.py`, `test_db.py` and `test_settings.py` may never overlap (a cold pool, one browser). Apply the memory note `race-tests-that-really-race` and rerun their mutants.

## Open questions for the owner

- Decision 0032's own calls: signed links of 5 minutes unless asked and 6 hours at most, `get`'s 32 MiB default, a 2 GiB `STORAGE_MAX_BYTES` default, three tries per call. Keep them?
- Decision 0033's own calls: `string.Template` rather than a template engine, a site's rewording limited to the original's placeholders, Resend's 10-second and SMTP's 15-second timeouts, TLS always for SMTP. Keep them?
- When to make R2 test buckets (one private, one public with a custom domain) so `test_storage_live.py` runs: before the site's step 2 uploads its first master.
- Desk steps: reset the Postgres `postgres` password (the owner types it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if wanted.

## Notes

- **A waiting module is skipped by the harness only** (`harness/layout.py`), so its `requires` and models can't break the app or the migrations until its step renames it. mypy (`modules/*/backend`, every folder, `_template` too), ESLint and `tsc` (those two exclude only `_template`) still check its code, so it has to keep passing them.
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
