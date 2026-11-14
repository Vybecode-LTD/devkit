# Handoff

Overwritten every session. 2026-11-13 to 14: a remote session (claude.ai in a cloud container), then the first session in Claude Code on the owner's machine, from sessions (#32) to sign-up (#39), all merged: `main` is at a753cf1. This handoff is #40.

## State

- **K0 and K1 done**, and **audited** (2026-11-12). The audit found 55 issues, none of them a leak; the report is private (`docs/private/`). It and the review bots' follow-ups landed as 24 pull requests, #1 to #24, each with its tests seen failing first and CI green.
- **K2 started:**
  1. The contract suite (`kernel/tests/contract/`) speaks HTTP only, against `docs/contracts/auth-api.md`. Each of its 83 tests is a strict expected failure that fails only with "not built", so it can't pass by accident or fail for the wrong reason.
  2. `kernel/auth/passwords.py` is done: a bounded Argon2id pool (503 `kernel.busy` when full), parameters from the config (`Passwords.from_config`), the rules, the bundled list and Pwned Passwords.
  3. Every auth table is in place (`kernel/auth/models.py`, migration `kernel_0002`, amended in place by the audit with an index on every foreign key). Its six permissions are declared in `kernel/kernel.json`.
  4. One-time secrets are kept as keyed hashes (`kernel/auth/hashing.py`, decision 0012).
  5. Test support: `reset` (with `{"accounts": true}`), `clock`, `routes`, `breached`, `mail`, `users`.
  6. Sessions (`kernel/auth/sessions.py`, #32): opaque tokens kept as SHA-256, member and staff limits (`Lifetimes`), the session epoch, a new token after a role change and at step-up (one per race, #33), `last_seen_at` at most hourly (or every eighth of a shorter idle limit), the `__Host-` cookie helpers and the signed known-device cookie. 49 tests, 100% of the module.
  7. Access dependencies (`kernel/auth/dependencies.py` and `permissions.py`, #36): `current_user`, `optional_user`, `require_permission`, `require_owner_or` and `require_recent_auth`, in the public surface with their access marks. Owners hold every permission; on a resource a person's own overrides decide before their roles', and a denial beats a grant. `require_owner_or` lets through the owner, or staff holding the permission (14.8): a member's personal grant never opens someone else's thing. The admin gate (`/api/<id>/admin`: staff, then a confirmed TOTP or a passkey) reads the route's path by Starlette's own rule, so a proxy's `root_path` can't shift it. A token replaced mid-request reaches the browser on any answer, errors included (`SessionCookies`). 36 tests, 15 mutant checks, 100% of both modules.
  8. The mail interface (`kernel/email.py`, #37): the `Mailer` protocol beneath K3's `email.send` (decision 0013), installed by `create_app(mailer=)` behind `Checked`. Every adapter gets one bare recipient, no line break in the address or the subject (CR, LF, NUL, NEL and Unicode's separators), and bounded sizes; a refusal is a ValueError naming the field, never its value. The default, `LogMailer`, sends nothing and logs a warning that holds nothing of the message. The harness keeps mail in a `CapturingMailer` behind the same checks, for `GET /api/_test/mail?to=`, and `reset` empties it. 43 tests, 14 mutant checks, 100% of the module.
  9. Sign-in (`kernel/auth/routes.py`, `accounts.py`, `second_factor.py`, `audit.py`, #38): `POST /api/auth/sign-in`, `/sign-in/second-factor`, `/sign-out`, `/step-up` and `GET /api/auth/session`.
     - An unknown, suspended or password-less account costs the same Argon2 verify, counts against the same limit and gets the same answer.
     - Failed passwords wait in tiers (5 in 15 minutes, 10 in an hour, 20 in a day), except on a known device. Second-factor failures are limited per sign-in (5) and per account (10 an hour), decision 0019. The fifth failed step-up ends the session.
     - TOTP with one step of drift, no replay, on real time; recovery codes; a 10-minute challenge that counts each try before checking it.
     - A new device is mailed a notice in the background, and every step writes an audit row with nothing secret or typed in it.
     - 17 contract tests now pass. 43 kernel tests, 19 mutant checks (18 caught, 1 equivalent), the threat-model checklist in the PR body. Codex's two findings fixed: second-factor tries reserve their place in the account's budget first, and an owner holds the kernel's permissions (`KERNEL_PERMISSIONS`, held equal to `kernel.json` by a test).
  10. Sign-up and verification (`kernel/auth/sign_up.py`, `tokens.py`, #39): `POST /api/auth/sign-up` and `/verify-email`.
     - `SIGN_UP_MODE` is open, invite or closed, **closed by default**; invite-only takes no sign-ups until invites exist (decision 0020). The harness is open, and its breach lookup answers the range API from `/api/_test/breached` (`create_app(breach_lookup=)`).
     - The password is judged first (rules, list, breach lookup), then one Argon2 hash is spent either way. A new address gets an unverified member account and a 24-hour link; a taken one gets a notice and its account is left alone. Sign-ups at once for one address make one account.
     - 5 sign-ups per IP an hour; past 3 mails to one address in 15 minutes, no more notices, though a new account's one link always goes (Codex on #39). The mail goes out after the answer.
     - The link works once, only for the address it was sent to, and signs nobody in.
     - 4 more contract tests pass (21 in all), and the timing test now signs up a new address each round. 31 kernel tests, 14 mutant checks, all caught, and the threat-model checklist in the PR body.
- **Kernel changes from the audit:**
  - 500s keep their security headers, and request bodies have a limit (`MAX_BODY_BYTES`);
  - rate-limit keys can't collide, and each route has its own budget;
  - the module switches are cached per process for `MODULES_CACHE_SECONDS`;
  - settings keep typed secrets and work with strict models;
  - logs keep a traceback's end, scrub in linear time and write one access line per request;
  - the start-up checks are stricter (SECRET_KEY 43+ characters, an https SITE_URL outside DEBUG);
  - HSTS goes out behind a TLS edge.
- **Tests:** 496 Python tests pass on Linux CI (on Windows, 495 and a skipped symlink test) with 63 strict expected failures, and coverage is about 95% (CI fails under 85%). Coverage now follows SQLAlchemy's greenlets (`concurrency` in `pyproject.toml`); before #36, lines after a database await inside a request went unmeasured. There are 7 web tests. The migration tests compare the full Postgres catalog, run a seeded round trip and a stairway, and include 11 mutant controls.
- **CI** runs on every PR, every push to `main`, weekly and by hand (decision 0015). Its first run was #1.
- **GitHub:** `https://github.com/Vybecode-LTD/devkit`, public (decision 0011). Commits use the owner's no-reply address. PRs land by fast-forwarding `main` to the PR's head once "CI result" is green; an API squash or rebase would stamp the token's address instead.
- **Common-password list:** NOTICE gives each source's own terms, and the tool's docstring has the exact rebuild.
- **Decisions:** 0012 to 0016 came from the audit, 0017 retired the Spec doc, and 0018 records the module roadmap after v1.0 and its ten contract hooks (none in SPEC.md yet). SPEC 4 to 7, 14 (14.1 to 14.13 in places), 15 and 16 changed in the audit.

## Next

The job is `dev plans\2026-11-14-next-session-k2-step-5.md`: the local teardown fix (Notes), then K2 step 5, sign-in codes and magic links (`POST /api/auth/code`, `/code/verify`, `/link/confirm`), then resets, and a new verification link for a signed-in account (no contract row yet). The owner's machine is set up. The suite should show 496 passed (Windows: 495 and 1 skipped) and 63 xfailed with Postgres up.

After K2 and the kernel phases, and before blog, chat and payments are extracted (SPEC 19, phase 3): the ten contract hooks of decision 0018, one PR per hook with `skills/devkit-hook-designer`. Start with export and erase, which the spec nearly has already (it needs an export contract test). The modules that follow v1.0 are in `docs/plans/module-roadmap.md`.

## The owner's answers (2026-11-13)

- **History rewritten:** `main` from #1 on was rewritten so no commit carries the API token's address. Trees, messages and dates are unchanged; everything before #1 keeps its hashes. **A clone made before 2026-11-13 must reset:** `git fetch origin`, then `git reset --hard origin/main` (with nothing of its own to keep).
- **Ruleset `main`:** on the default branch, it requires "CI result" to have passed on the exact commit (and the branch to be up to date for PR merges), and blocks force pushes and deletion (decision 0015). It has no "require a pull request" rule: that rule would force merges through GitHub's merge button, which stamps the API token's address on every merge. The check rule gives the same guarantee, since a commit only has a green "CI result" if it ran CI on a branch first.
- **Merged branches deleted;** finished PR branches are deleted after landing from now on.
- **Actions pinned** to commit SHAs, and Dependabot proposes the bumps weekly (#26).
- **The claude.ai Spec doc is retired** (decision 0017): titled "(retired)", with a notice that it's frozen as of 2026-11-12. `SPEC.md` is the only copy.
- **Review bots:** CodeRabbit stays on its free tier. When it's rate-limited, a PR lands on a green "CI result" and Codex's review.
- **Security pass:** the `auth-threat-model-checklist` skill runs on K2's high-risk PRs (sign-in, reset, magic links, OAuth, step-up, API keys), not on the plumbing.
- **Account skills:** the owner's claude.ai skills reach Claude Code through the account sync, so they aren't copied anywhere.
- **Vibrant Mindz:** Q1 to Q6 are answered (`docs/plans/vibrant-mindz-module-plan.md`, section 12); comments take guests, with approval. The SMS provider is chosen at roadmap wave 3b.

## Notes

- **Session lifetimes are a parameter:** the dependencies read `app.state.session_lifetimes`, else the spec's defaults. Reading them from the site's settings (Q6) comes with their admin page, cached the way the module switches are, so `current_user` adds no query.
- **`require_owner_or` gives a guard, and the route must call `await guard.check(owner_id)`** before touching the thing; a route that forgets lets any member through. `module-contract-lint` should gain a row for it when the first module uses it.
- **Parallel password guesses can pass one tier by their own number:** sign-in checks the wait before verifying and counts a failure after, so requests in flight at once all get their verify (bounded by 10 a minute per address). Reserving first would count the owner's own sign-ins too. Second-factor tries do reserve first (Codex on #38).
- **TOTP runs on real time,** not `kernel.clock`: codes come from the person's app. A test that moves the clock still gets codes from `pyotp`'s `now()`.
- **`supersede(request)`** drops the token `SessionCookies` was going to set: any route that sets the session cookie itself after `signed_in` must call it, as step-up does (a role change and a step-up in one request left two cookies, the dead one last).
- **The new-device mail is a background task.** Against a remote harness it can land after the suite reads `/api/_test/mail`.
- **Mail goes out after the answer** (a background task until K3's `jobs`), as sign-up's does: a code or reset mailed only to a known address would leak it through timing otherwise, and a failing adapter mustn't change the answer either. Against a remote harness (`CONTRACT_BASE_URL`) a background send can land after the suite reads `/api/_test/mail`, so that read may need to wait for the message.
- **Someone else's address can be signed up first** (an unverified account with their password). The real owner's way back is a reset: when step 5 builds it, a reset should end every session (the epoch) and may mark the address verified, since it proves the inbox. The 7-day removal of unverified accounts and the `auth.user.verified` event wait for K3's `jobs` and `events`.
- **`SIGN_UP_MODE` is closed by default:** a site's brief must say open or invite, and the site template (K5) should ask. The site settings (Q6) take it over with their page.
- **How a site picks its adapter is K3's call:** from the config or through `create_app(mailer=)` (which SPEC 6 doesn't list yet, like `database=`), and whether a start outside DEBUG without one is refused.
- **List the access dependency before `rate_limit(key="account")`:** FastAPI runs them in order, and the limit falls back to the address when no one is signed in yet.
- **A replaced token is dead at once** (14.5): a request still carrying it after a role change or a step-up gets 401. The web kernel's session hook (K4) should retry once on a 401 that follows a new cookie.
- **The device cookie is signed over the session epoch,** so a reset or a password change makes every browser a stranger. A route that raises the epoch on a browser that stays signed in (a password change) should set a fresh one.
- **React Router stays on 7** (8 is out; moving needs a decision record). TypeScript stays on 6.0.x for typescript-eslint.
- **FastAPI 0.162** keeps included routers whole in `app.routes`: walk them with `fastapi.routing.iter_route_contexts`, as `kernel.ratelimit.route_name` does.
- **A local-only teardown flake:** `conftest._drop` runs `DROP DATABASE … WITH (FORCE)`, which a role without superuser can't use while an autovacuum worker is in that database (`InsufficientPrivilegeError: permission denied to terminate process`). On the owner's machine `devkit` isn't a superuser (by design), so roughly one migration test per full run errors at teardown. CI's `devkit` is the container's superuser and never sees it. The fix: on that error, end the run's own sessions and use a plain `DROP DATABASE`, which stops autovacuum by itself.
- **Codex reviewed only #39's first push.** Its later commits got no Codex review, so a fix to a Codex finding is checked by its tests and CI, not by Codex.
- **pytest runs with `--import-mode=importlib`.** Close any pool a test app opens: under coverage, an unclosed connection fails the next test.
- **gitleaks in CI** is the release binary checked against a pinned SHA-256. Bump both together.
- **The remote tools can't write `.npmrc` or `.github\`.** After a remote sync, run `git checkout -- .npmrc .github` before any `npm` command.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions (JWT for staff, cookies for members) and its split account tables differ from the spec. Port the behavior, not the shape.
