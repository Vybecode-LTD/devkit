# Next session: K2, auth (sessions, dependencies, first routes)

Run from `C:\DEV\AI-DevKit` in Claude Code. Say: "Read dev plans\2026-11-13-next-session-k2-in-claude-code.md and continue K2."

## Where things stand

K0 and K1 are done and audited: PRs #1 to #30 are merged, and the audit's notes are in `docs/private/`. This is the first session in Claude Code on the owner's machine; the earlier ones ran remotely. K2 has started:
- **The contract suite:** `kernel/tests/contract/`, 83 strict expected failures over HTTP, against `docs/contracts/auth-api.md`. Each fails only with "not built".
- **Passwords:** `kernel/auth/passwords.py` (`Passwords.from_config`, a bounded Argon2 pool, 503 `kernel.busy`).
- **Tables and keys:** every auth table, plus `kernel/auth/hashing.py` (keyed hashes, decision 0012).
- **Test support:** `harness/testing.py`, with reset (`{"accounts": true}` too), clock, routes and breached.

## Set up the machine (once)

1. `git status` must be clean, on `main`, level with `origin/main`. A clone from before 2026-11-13 must first run `git fetch origin` and `git reset --hard origin/main` (history was rewritten once). If `.npmrc` or `.github\` is missing, run `git checkout -- .npmrc .github`.
2. `py -3.12 -m venv .venv`, `.venv\Scripts\Activate.ps1`, `python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt`.
3. `npm ci`, `python -m tools.link_skills`, Docker Desktop running, then `docker compose up -d db`. `gitleaks` must be on PATH for the pre-commit check.
4. `python -m pytest --cov --cov-fail-under=85`: 271 passed, 83 xfailed, coverage about 94%. `npm test`: 7 passed. If those numbers differ, stop and find out why before writing code.

## Read first

- `CLAUDE.md` and `docs/HANDOFF.md`;
- SPEC.md 14 in full, and `docs/contracts/auth-api.md`;
- decisions 0010, 0012, 0013 and 0014;
- the contract suite.

## The job, in order (one PR each, tests first)

1. **Sessions:** `kernel/auth/sessions.py`, from VybeSite `backend\app\services\sessions.py` and `members.py`.
   - The cookie is `__Host-dk_session`, and a row keeps the token's SHA-256.
   - Lifetimes: members 14 days idle and 30 total, staff 8 hours and 7 days.
   - `session_epoch`; `role_version`, which re-issues the token on the next request and kills the old one; `last_seen_at` at most hourly; the device label.
   - The known-device cookie `__Host-dk_device` (14.5): over the failure limit, the right password still works on a browser that signed in before.
2. **Dependencies:** `current_user`, `optional_user`, `require_permission`, `require_owner_or`, `require_recent_auth`. Each sets an access mark (`kernel/access.py`, `STEP_UP_MARK` for step-up).
   - The owner holds every permission.
   - Overrides: a denial beats a grant, and a person's own beats their role's.
   - The admin gate on `/api/*/admin` checks for a staff role and a second factor.
   - `request.state.user_id` feeds `rate_limit(key="account")`.
3. **Mail interface:** `kernel/email.py`, a `Mailer` protocol beneath `email.send` (decision 0013). Add a capturing mailer for `/api/_test/mail`, and a default that logs without the body.
4. **Routes:**
   - sign-up, sign-in, the second factor, sign-out, session and step-up, with the 14.6 limits and normalized email keys;
   - sign-up with an existing address sends a notice and answers as for a new one;
   - test support adds `users` and `mail`;
   - drop each test's `@not_built` as it passes: a strict xfail that passes fails the run.
5. If time allows: sign-in codes and links, then reset and verification.

## Rules that bite here

- **One `auth_user` table and roles.** Port VybeSite's behaviour, not its shape.
- **Secrets:** `hmac.compare_digest` and `secrets` everywhere. Tokens and codes are stored via `keyed_hash`, never plain.
- **Hashing:** go through `Passwords`, never argon2 directly, so the pool bounds the load.
- **Nothing secret in logs.** `kernel.redact` is a backstop, not a licence.
- **The brand check** on lifted code: `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"`.
- **Before every commit:** ruff, black, mypy, `python -m tools.validate_schemas`, pytest with `--cov`, the brand check, and `gitleaks git --pre-commit --staged`.
- **Spec changes:** a spec change needs a decision record and a change-log line in the same PR.
- **After each merge:** read the review bots' comments. All eight real ones this session became follow-up PRs.
- **Skills:** don't build them; add ideas to `docs/SKILL-BACKLOG.md`.
- **Spec doc:** there is none to sync. The claude.ai Spec doc is retired (decision 0017); `SPEC.md` is the only copy.
- **Session end:** overwrite HANDOFF, update CLAUDE.md and AGENTS.md, and write the next prompt here (move this one to `dev plans\done\`).

## Git

`https://github.com/Vybecode-LTD/devkit` is public. Use a branch per PR and open the PR so CI runs. Land it by fast-forwarding `main` to the PR head once "CI result" is green (`git push origin <sha>:refs/heads/main`), then delete the branch. A ruleset on `main` (since 2026-11-13) rejects any commit without a passing "CI result" from a branch, any force push and deletion, so never push straight to `main`. Fast-forwarding keeps the owner's no-reply address on every commit. Never commit secrets, client material or anything in `docs/private/`.
