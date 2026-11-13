# Next session: a full audit of everything built so far

Paste this as the first message of a new session. Run it from `C:\DEV\AI-DevKit` in Claude Code, or in a remote session with the repo `Vybecode-LTD/devkit` attached.

---

You're auditing AI DevKit before any more gets built. Everything so far was built in one very long remote session (2026-11-12). I want a complete, skeptical audit: check that what was built is accurate (it does what the spec, decisions and docs say, and the docs say what the code does) and efficient (no wasted work, needless complexity or slow paths). Assume nothing was verified just because a summary says so. Prove each thing by reading the code and running it.

**Don't build new features and don't continue K2.** Audit first, report, then fix only what I approve.

## Read first
`CLAUDE.md`, `docs/HANDOFF.md`, `SPEC.md` (all of it), `KICKOFF.md`, `docs/decisions/` (0001 to 0011), `docs/contracts/auth-api.md`, `docs/SKILL-BACKLOG.md`, `NOTICE`, `LICENSE`, and `git log --stat`.

## Setup
1. `git pull`. If `.npmrc` or `.github\` is missing, run `git checkout -- .npmrc .github` before any npm command.
2. Create the venv, then `python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt`.
3. `npm ci`, then `docker compose up -d db`.

## What to audit (every item gets a verdict and evidence)

1. **The full gate, run for real:**
   - `python -m pytest` (expect 167 passed, 42 xfailed), with coverage.
   - ruff, black --check, mypy, `python -m tools.validate_schemas`.
   - `npm test`, lint, typecheck, build.
   - pip-audit, npm audit, gitleaks over the whole history, and the brand check.
   - A migration round trip on a fresh database.
   - A live run of the harness (`python -m uvicorn harness.main:app`), with `curl` checks of the health route, the security headers and a cross-site POST.
2. **Kernel core (K1),** line by line against SPEC.md sections 6, 7, 10, 12 and 15:
   - Files: `config.py`, `db.py`, `crypto.py`, `errors.py`, `security.py`, `ratelimit.py`, `redact.py`, `logs.py`, `error_tracking.py`, `modules.py`, `settings.py`, `access.py`, `app.py`, `routes.py`, `clock.py`.
   - Look for bugs, edge cases, security holes, race conditions, misleading docstrings and anything slower than it needs to be.
   - Suspects to check:
     - the CSP is rendered on every request;
     - `require_module` reads the database on every module request;
     - `on_cached` goes stale across workers;
     - the rate limiter's per-route scope naming, under FastAPI 0.162's included routers;
     - the settings three-way merge, with lists merged whole, plus its advisory-lock and commit behavior, including `commit=False`;
     - `for_saving` under a race;
     - whether the redact patterns really run in linear time;
     - `logs.configure` touching the root and uvicorn loggers;
     - `public` set as a router-level dependency counting for every route.
3. **Auth so far (K2):**
   - `kernel/auth/passwords.py` against SPEC.md 14.2: 12 to 256 characters, NFC, the rules ported from VybeSite, the common list, Pwned Passwords failing open, the Argon2id parameters and floor, rehashing, and the dummy hash for unknown accounts.
   - `kernel/auth/models.py` and migration `kernel_0002` against 14.11: every table, column, constraint, index, foreign key and ON DELETE rule, plus the seeded roles and permissions.
   - Run the `auth-threat-model-checklist` skill over the design as it stands.
4. **The contract suite** (`kernel/tests/contract/`) against SPEC.md 14.13 and `docs/contracts/auth-api.md`:
   - Does each 14.13 line have a test that would truly prove it?
   - Is any test wrong, flaky (the timing test), or able to pass for the wrong reason?
   - Does any test conflict with VybeSite's known-device cookie, which the next K2 step ports?
   - Is the design sound: HTTP only, the harness's test-support routes behind `HARNESS_TEST_SUPPORT=1`, strict xfail?
5. **Migrations and the harness:** per-module branches, `version_locations`, `env.py`, the round-trip and drift tests, `harness/registry.py`'s discovery names (decision 0009), and the test support never being mounted by `harness.main`.
6. **Tooling and CI:**
   - `.github/workflows/ci.yml` has never run, because no PR exists yet. Check that the action versions (`checkout@v7`, `setup-python@v7`, `setup-node@v7`) exist, that `go install …gitleaks/v8@v8.28.0` and `gitleaks git` work, that the path filters are right, and that `--only-binary=:all:` installs.
   - The first real proof is opening a PR. Do that with the first fix, so CI runs.
7. **Dependencies:** every pin and why it's there:
   - FastAPI 0.162, SQLAlchemy 2.1, TypeScript 6.0.3, React Router 7.18.5 (8.x exists).
   - The `minimatch` override.
   - What's unused or heavier than needed (`uvicorn[standard]`, for example).
8. **The common-password list:**
   - Its sources and licenses: does SecLists' MIT license really cover the NCSC, xato and Pwdb lists, and are `NOTICE` and `licenses/` accurate?
   - That `tools/build_common_passwords.py` rebuilds it byte for byte.
   - Memory and load time.
9. **Public-repo hygiene** (the repo is public, decision 0011):
   - Every commit's author and committer.
   - No client terms, no `docs/private` content, no inventory and no secrets anywhere in history.
   - `.gitignore`, `LICENSE` wording, and anything else that shouldn't be public.
10. **Docs, accuracy and consistency:**
    - `SPEC.md` is internally consistent, and its change log and sections match decisions 0009 to 0011.
    - The `CLAUDE.md` and `AGENTS.md` bodies are identical.
    - `HANDOFF.md`, `KICKOFF.md`, the K2 next-session prompt and `docs/SKILL-BACKLOG.md` match reality.
    - `docs/contracts/auth-api.md` matches the claude.ai doc "AI DevKit: Auth HTTP API contract". Also compare against the claude.ai docs "AI DevKit Spec v0.1" and "Vibrant Mindz on DevKit: module plan", and the Project docs, if you can reach them; otherwise mark them not checked.
11. **Skills:**
    - The four in `skills/` plus `alembic-multi-module-migrations` and `module-contract-lint`: does every command, path and claim in them match the code? Note any that name tools not built yet, such as `devkit check`.
    - Note anything wrong in the account copies of the other skills built that day.
12. **Efficiency overall:** duplicated logic, over-engineering, dead code, slow tests (Argon2 cost in tests), and anything simpler that does the same job.

## How to work
- Read-only until the report is approved.
- Where you can, use separate reviewers for security, tests and docs (subagents such as a security auditor, a code reviewer and a test engineer), so nothing grades its own work.
- Write the report to `docs/private/audit-2026-11-<day>.md`. It's gitignored: security findings stay out of the public repo until they're fixed.
- One row per finding:
  - severity: critical, high, medium, low or nit;
  - area;
  - evidence: file:line, command and its output;
  - why it matters;
  - the fix you propose.
- End the report with a short list of what's verified correct.
- Then give me a one-screen summary and the proposed fix batches. After I approve, fix them one logical change per branch and PR: tests first for any bug (seen failing), the brand check and gitleaks before each commit, conventional commits.
- Ask before any GitHub setting change, such as a ruleset.

## Rules
Never commit secrets, client material or anything from `docs/private/`. Python commands use the `python -m` form, and my terminal is PowerShell. At the session's end, follow CLAUDE.md "Session end".
