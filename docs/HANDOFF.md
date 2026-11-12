# Handoff

Overwritten every session. 2026-11-12, remote session (claude.ai, working in a cloud container, synced to `C:\DEV\AI-DevKit`).

## State

- **K0 done:** hash-pinned Python tooling (uv), ruff, Black, mypy strict, pytest with a throwaway Postgres, one Alembic environment with per-module branches, the schema checker, npm workspaces (TypeScript strict, ESLint, Vitest), the CI workflow, `tools/link_skills.py`.
- **K1 done:** config with secret refusal, database layer, MultiFernet crypto, RFC 9457 errors, CSP and security middleware, rate limiting, redacted JSON logs, Sentry, module registry and switches, versioned settings with three-way merge, the route access audit, `create_app`, the harness app, migration `kernel_0001`.
- 137 Python tests and 7 web tests pass; 92% line coverage; mypy, ruff, Black, ESLint, tsc clean; pip-audit, npm audit, gitleaks and the brand check clean.
- Git: `main` has three commits (scaffold, K0, K1). The history is in `.history/devkit.bundle` (see below). No GitHub remote yet.

## Next

1. **K2, auth** (KICKOFF.md): contract tests from SPEC.md 14.13 first, seen failing; then accounts and roles, passwords, sessions, codes and links, reset, TOTP and step-up, passkeys, OAuth, API keys, abuse limits, lifecycle and audit. K2's first migration adds the `auth_user` foreign keys to `kernel_module_state.updated_by_id`, `kernel_setting.updated_by_id` and `kernel_setting_version.saved_by_id` (ON DELETE SET NULL).
2. The owner's go-ahead to create `Vybecode-LTD/devkit` and push, so CI runs for real.
3. K3 hooks are marked `K3:` in `kernel/modules.py` and `kernel/settings.py` (events and audit on switch and save).

## Adopting the history on the owner's machine

The files in `C:\DEV\AI-DevKit` match `main`. To get the commits too, from that folder in PowerShell:

```powershell
git init -b main
git fetch .history\devkit.bundle main
git reset --mixed FETCH_HEAD
git checkout -- .npmrc .github   # the remote tools can't write these two; the history holds them
git status   # only kernel\tests\.gitkeep and kernel\migrations\.gitkeep, left from the scaffold: delete them
```

**Restore `.npmrc` before any `npm` command:** it holds `ignore-scripts=true` (SPEC.md section 15). Then `py -3.12 -m venv .venv`, install with the commands in CLAUDE.md, `npm ci`, `python -m tools.link_skills`, and `docker compose up -d db` for the database tests.

## Notes

- **React Router 8 is out** (8.5.1). The spec says 7; the repo pins 7.18.5, past every advisory. Moving to 8 is a decision record of its own.
- **TypeScript is pinned to 6.0.3:** typescript-eslint 8 supports TypeScript below 6.1, and TypeScript 7 is the native port. `minimatch` is overridden to 11.0.8 for a dev-only advisory (note in `package.json`).
- **FastAPI 0.162** keeps included routers whole in `app.routes`; walk them with `fastapi.routing.iter_route_contexts` (as `kernel/access.py` does).
- **pytest runs with `--import-mode=importlib`,** which names `kernel/tests/*` as `kernel.tests.*`. The root `conftest.py` imports the real `kernel` package first so pytest never stands one in.
- **Playwright** isn't installed yet: it arrives with K4's end-to-end tests.
- **gitleaks** in CI is installed with `go install …@v8.28.0`, so Go's checksum database vouches for it. Bump it on purpose.
- The brand check was run from a copy of VybeSite's `scripts/brand_check.py` and its hashed denylist: clean.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions (JWT) and account tables (staff and members split) differ from the spec. Port the behavior, not the shape.
