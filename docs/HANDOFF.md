# Handoff

Overwritten every session. 2026-11-12, remote session (claude.ai in a cloud container, synced to `C:\DEV\AI-DevKit`).

## State

- **K0 done:** hash-pinned Python tooling (uv), ruff, Black, mypy strict, pytest with a throwaway Postgres, one Alembic environment with per-module branches, the schema checker, npm workspaces (TypeScript strict, ESLint, Vitest), the CI workflow, `tools/link_skills.py`.
- **K1 done:** config with secret refusal, database layer, MultiFernet crypto, RFC 9457 errors, CSP and security middleware, rate limiting, redacted JSON logs, Sentry, module registry and switches, versioned settings with three-way merge, the route access audit, `create_app`, the harness app, migration `kernel_0001`.
- **K2 started:**
  1. The contract suite (`kernel/tests/contract/`, one or more tests per line of SPEC.md 14.13) is written against `docs/contracts/auth-api.md`. 42 tests are strict expected failures until their code lands; the route audit passes.
  2. `kernel/auth/passwords.py` is done and tested.
  3. Every auth table is in place (`kernel/auth/models.py`, migration `kernel_0002`, built-in roles seeded).
  4. `kernel/clock.py` and the first test-support routes are in place (`harness/testing.py`: reset, clock, routes).
- 167 Python tests pass, 42 expected failures; 7 web tests. mypy, ruff, Black, ESLint, tsc, gitleaks and the brand check are clean.
- **GitHub:** `https://github.com/Vybecode-LTD/devkit`, public (decision 0011), with `LICENSE` keeping every right. Commits use the owner's no-reply address (`10875133+color8@users.noreply.github.com`). The history was rewritten before the first push to drop the personal address and the inventory.
- **Private notes** live in `docs/private/` (gitignored): the inventory of `C:\DEV` and the client folder's name.
- **Common-password list** bundled: 72,969 entries of 12+ characters from SecLists (MIT) and Django (BSD-3), see `NOTICE`. `tools/build_common_passwords.py --brand-check` rebuilds it.
- **Skills:** the backlog is built (11 proposed to the owner's account; `alembic-multi-module-migrations` and `module-contract-lint` also in `skills/`). Only `devkit-auth-contract-tests` waits, for K2.
- `C:\DEV\AI-DevKit` matches `main`, with `origin` set to GitHub.

## Next

**First, the full audit:** `dev plans\2026-11-12-next-session-audit.md`. K2 continues after its fixes land.

Then K2, in order:

1. **Sessions** (`kernel/auth/sessions.py`, from VybeSite `services/sessions.py`): `__Host-dk_session`, SHA-256 rows, member 14 d idle / 30 d absolute, staff 8 h / 7 d, `session_epoch` and `role_version` checks (a role change re-issues the token on the next request), the device label, last-seen at most hourly. Port VybeSite's known-device cookie (F-63) too: over an account's failure limit the right password still signs in on a browser that signed in before, so nobody can lock an owner out. Add it to `docs/contracts/auth-api.md` and the suite.
2. **Dependencies:** `current_user`, `optional_user`, `require_permission`, `require_recent_auth`, with access marks for the route audit, and the staff gate on every `/api/*/admin` route (a staff role and a second factor, else `auth.second_factor_required`). Role and permission resolution, owner holding all, per-resource overrides.
3. **A mail interface** (`kernel/email.py`): a protocol, a capturing adapter the harness uses for `/api/_test/mail`, and a logging default. SMTP, Mailgun and Resend come in K3.
4. **Routes:** sign-up, sign-in (with the 14.6 limits), sign-out, session and step-up. Test support adds `users` and `mail`. Remove each contract test's expected-failure mark as it passes.
5. Then codes and links, reset and verification, TOTP and recovery codes, passkeys, OAuth with the fake `test` provider, API keys, lifecycle (deletion with its 14-day grace, run by `/api/_test/jobs/run` until K3's worker), audit.

## Questions for the owner

- **A ruleset for `main`** (require a PR and the "CI result" check, block force pushes). It's a repo setting, so it waits for the owner's go-ahead.

## Notes

- **React Router 8 is out** (8.5.1). The spec says 7, so the repo pins 7.18.5, which is past every advisory. Moving to 8 needs its own decision record.
- **TypeScript is pinned to 6.0.3:** typescript-eslint 8 supports TypeScript below 6.1, and TypeScript 7 is the native port. `minimatch` is overridden to 11.0.8 for a dev-only advisory (see the note in `package.json`).
- **FastAPI 0.162** keeps included routers whole in `app.routes`; walk them with `fastapi.routing.iter_route_contexts`.
- **pytest runs with `--import-mode=importlib`.** The root `conftest.py` imports the real `kernel` package first, so pytest never puts a stand-in in its place.
- **Playwright** comes with K4's end-to-end tests.
- **gitleaks** in CI is installed with `go install …@v8.28.0`, so Go's checksum database vouches for it. Bump the version on purpose.
- **CI runs on pull requests** (and manual runs), not on pushes to `main`. Open a PR to see it run.
- **The remote tools can't write `.npmrc` or `.github\`.** After a remote sync, restore them from git (`git checkout -- .npmrc .github`) before any `npm` command, since `.npmrc` holds `ignore-scripts=true`.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions (JWT for staff, cookies for members) and its split account tables differ from the spec. Port the behavior, not the shape.
