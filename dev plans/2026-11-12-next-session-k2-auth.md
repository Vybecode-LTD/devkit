# Next session: K2, auth (sessions, dependencies, first routes)

Run from `C:\DEV\AI-DevKit` in Claude Code. Say: "Read dev plans\2026-11-12-next-session-k2-auth.md and continue K2."

## Where things stand

K0 and K1 are done (the tooling, CI workflow, harness and kernel core). K2 has started:
- `kernel/tests/contract/` holds the auth contract suite, one or more tests per line of SPEC.md 14.13. The tests speak HTTP only, against `docs/contracts/auth-api.md`, and all 42 are strict expected failures.
- `kernel/auth/passwords.py` is done, with the bundled common-password list.
- Every auth table exists (`kernel/auth/models.py`, migration `kernel_0002`).
- `kernel/clock.py` is the clock every expiry reads.
- `harness/testing.py` holds the first test-support routes.

## First, set up the machine (once)

1. `git status` must be clean. If `.npmrc` or `.github\` is missing, run `git checkout -- .npmrc .github` before any `npm` command.
2. `py -3.12 -m venv .venv`, `.venv\Scripts\Activate.ps1`, then `python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt`.
3. `npm ci`, `python -m tools.link_skills`, `docker compose up -d db`.
4. `python -m pytest`: 167 passed, 42 xfailed. `npm test`: 7 passed.

## Read first

`CLAUDE.md`, `docs/HANDOFF.md`, SPEC.md section 14 in full, `docs/contracts/auth-api.md`, decisions 0009 and 0010, and the contract suite itself.

## The job, in order (one PR each, tests first)

1. **Sessions:** `kernel/auth/sessions.py`, from VybeSite `backend\app\services\sessions.py`.
   - Read VybeSite's `members.py` and its tests for the member side.
   - The cookie is `__Host-dk_session`: HttpOnly, Secure, SameSite=Lax, Path=/. A row keeps only the token's SHA-256.
   - Lifetimes: members 14 days idle and 30 days absolute; staff 8 hours and 7 days. Both are site settings, so give them a kernel settings model.
   - `session_epoch` ends older sessions. `role_version` re-issues the token on the person's next request, and the old token stops working.
   - Write `last_seen_at` at most hourly. Keep the device label.
   - Port VybeSite's known-device cookie (F-63): over the failure limit, the right password still signs in on a browser that has signed in before. Add it to the contract doc and the suite first.
2. **Dependencies and permissions:**
   - `current_user`, `optional_user`, `require_permission(key)`, `require_recent_auth(minutes=10)`. Each sets an access mark (`kernel/access.py`), so the route audit counts member and permission routes.
   - Roles: owner holds every permission. Per-resource overrides: a denial beats a grant.
   - The staff gate goes on every `/api/*/admin` route: no second factor on the account means 403 `auth.second_factor_required`.
   - `request.state.user_id` is what `rate_limit(key="account")` reads.
3. **Mail interface:** `kernel/email.py`, a `Mailer` protocol with `send(to, subject, text, html=None)`.
   - A capturing mailer that the harness's test support reads.
   - A default that logs "would send" without the body.
   - SMTP, Mailgun and Resend adapters come in K3.
4. **Routes:** sign-up (open, invite-only or closed), sign-in, sign-in/second-factor, sign-out, session and step-up, with the limits in 14.6. Sign-up, sign-in and reset requests answer the same whether or not the email has an account.
   - Test support adds `POST /api/_test/users` and `GET /api/_test/mail`.
   - Remove each contract test's xfail mark as it passes; a strict xfail that passes fails the run.
5. If time allows: sign-in codes and magic links (VybeSite `sign_in_codes.py`), then reset and verification (`password_reset.py`).

## Rules that bite here

- Port behavior, not shape: VybeSite uses separate staff and member tables. DevKit has one `auth_user` table and roles.
- Every token check uses `hmac.compare_digest`, and every random value comes from `secrets`.
- No secret goes in logs. `kernel.redact` cleans log lines, but don't lean on it.
- Run the brand check on lifted code: `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"`.
- Auth PRs get the full review: tests, a migration round trip, a live check in the harness (`python -m uvicorn harness.main:app`), then a self-review against SPEC.md section 14.
- Don't build skills. Add ideas to `docs/SKILL-BACKLOG.md`.
- Session end: overwrite `docs/HANDOFF.md`, update "Current state" and "Last Completed Task" in CLAUDE.md and AGENTS.md, and write the next prompt in `dev plans\`.

## Git

The repo is public at `https://github.com/Vybecode-LTD/devkit`. Work on a branch per PR, push it, and open the PR so CI runs (CI runs on pull requests). Never commit secrets, client material or anything for `docs/private/`.
