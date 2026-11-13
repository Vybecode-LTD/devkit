# AGENTS.md: AI DevKit (same rules as CLAUDE.md)

The binding directives are in `C:\DEV\CLAUDE.md` and `C:\DEV\DIRECTIVES.md`, which Claude Code loads for every folder under `C:\DEV`. This file is the project map. Where the two differ, this file wins. `AGENTS.md` holds the same text for other agents.

## Identity

- **What:** AI DevKit, a library of reusable website modules (auth, blog, chat, payments, community, media and more) that any AI agent copies into a site's repo and wires together from a short brief.
- **Owner:** VybeCode Software (VybeCod.ing / Vibrant Mindz).
- **Not:** a hosted platform, a WordPress-style CMS, or a package registry. Modules are copied in at build time (decision 0002).
- **Path:** `C:\DEV\AI-DevKit`. **Remote:** `https://github.com/Vybecode-LTD/devkit`, **public** (decision 0011). Never commit secrets, client material or private notes; private notes go in `docs/private/` (gitignored).
- **The contract:** `SPEC.md`. Every module, the kernel and the CLI follow it. Read the sections you touch before every change.

## Current state (2026-11-13)

- Spec v0.1 written, the owner's answers applied.
- **K0 (repo foundation) and K1 (kernel core) are done and audited:** the audit's fixes and the review bots' follow-ups are merged (PRs #1 to #24), and the owner's follow-ups too (#25 to #31): history rewritten once, a ruleset on `main`, actions pinned, the claude.ai Spec doc retired, the Windows set-up. K2 (auth) has started: the contract suite is written as strict expected failures, and passwords, keyed hashes, every auth table and the sessions service (`kernel/auth/sessions.py`, #32) are in place. See `docs/HANDOFF.md`.
- **Next:** K2's access dependencies, the mail interface and the first auth routes (`dev plans\2026-11-13-next-session-k2-in-claude-code.md`, from step 2).
- First real site: the new Vibrant Mindz site (`docs/plans/vibrant-mindz-module-plan.md`). It doubles as the spec's validation build.

## Last Completed Task

2026-11-13 (remote session): the owner's answers to the audit's questions. `main` rewritten once to take the API token's address off two commits, then protected by a ruleset ("CI result" required, no force push, no deletion); merged branches deleted; actions pinned to SHAs with Dependabot (#26); the claude.ai Spec doc retired (decision 0017, #29); `repo-hygiene-sweep` added to the skill backlog (#28).

2026-11-12 (remote session): the full audit of K0, K1 and K2-so-far (55 findings, report in `docs/private/`), then every fix batch as its own PR, tests first, plus eight follow-ups from the review bots. Decisions 0012 to 0016. CI now runs on pushes to `main` and weekly, with an 85% coverage floor.

## Read order

1. `KICKOFF.md` (first sessions) or the newest `dev plans\*-next-session-*.md` (later sessions). It is the job.
2. `docs/HANDOFF.md`: state, next steps, blockers.
3. `SPEC.md`: the sections the job touches.
4. `docs/decisions/`: why things are the way they are.
5. `docs/private/inventory.md` (on the owner's machine only, not in git): where each piece can be lifted from in `C:\DEV`.

## Stack (decision 0001)

Python 3.12+, FastAPI, Pydantic v2 (strict), async SQLAlchemy 2 + asyncpg, Postgres 16+, Alembic with one branch per module; React 19, Vite, TypeScript strict, React Router 7 (library mode), TanStack Query; design tokens as CSS custom properties with Tailwind v4 mapped to them; openapi-typescript + openapi-fetch for the typed client; Postgres-backed job queue; S3-compatible storage (Cloudflare R2); Docker on Railway. Tests: pytest, Vitest + React Testing Library, Playwright.

## Commands

From the repo root, in PowerShell. Python commands use the `python -m` form.

| What | Command |
| --- | --- |
| Python environment, first time | `py -3.12 -m venv .venv`, then `.venv\Scripts\Activate.ps1` |
| Install Python dependencies | `python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt` |
| Re-pin after editing a `.in` file | `python -m uv pip compile requirements.in --generate-hashes --universal --python-version 3.12 -o requirements.txt`, and the same for `requirements-dev.in` into `requirements-dev.txt` |
| Test Postgres | `docker compose up -d db`; or any local Postgres 16+ with a `devkit` role (CREATEDB) and `TEST_DATABASE_URL` pointing at it, as on the owner's machine |
| Python tests | `python -m pytest` (add `-m "not db"` to run without Postgres) |
| Lint, format, types | `python -m ruff check .`, `python -m black .`, `python -m mypy` |
| Manifests against the schemas | `python -m tools.validate_schemas` |
| Migrations | `python -m harness.migrations upgrade` (also `downgrade`, `heads`, `history`, `current`), with `DATABASE_URL` set |
| Audit Python dependencies | `python -m pip_audit --strict --require-hashes --disable-pip -r requirements.txt -r requirements-dev.txt` |
| Web install | `npm ci` |
| Web tests, lint, types, build | `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` |
| Link the project skills for Claude Code | `python -m tools.link_skills` |
| Brand check, before any PR that lifts code | `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"` |

## Rules

- **The spec is the contract.** A change to it is a decision record in `docs/decisions/` plus a line in its change log, in the same PR. Tell the owner which sections changed. There is no doc to sync: the claude.ai Spec doc is retired (decision 0017).
- **Provenance.** Nothing from the client folder named in `docs/private/README.md` or any client-confidential material ever enters this repo. Code lifted from VybeSite passes VybeSite's brand check before it lands: `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"`. Never copy anything from VybeSite's `dev plans\` or `snapshots\`.
- **Ask first** before anything outward-facing: creating the GitHub repo or changing its settings, Railway projects, DNS, any third-party account, any message sent for the owner.
- **No secrets, ever.** Not in the repo, not in logs, not in chat. Keys go in a host's variables, typed by the owner.
- **Tests first.** A bug fix has a test seen failing before the fix. Auth work starts from the contract tests in spec 14.13.
- **One logical change per PR,** on its own branch, with conventional commits. Read the staged diff for secrets before every commit.
- **Modules never import each other** except through `public.py` / `web/public.ts` when listed in `requires.modules` (spec section 7).
- **Skills:** don't build new skills as you go. Add every idea to `docs/SKILL-BACKLOG.md`; the owner builds them all in one batch later. Build one early only if the work can't continue without it, and say so.

## Project skills (`skills/`, linked into `.claude/skills/` by `python -m tools.link_skills`)

| Skill | Use it when |
| --- | --- |
| `devkit-module-extractor` | Lifting a feature from another project into `modules/` |
| `devkit-site-picker` | Turning a site brief into a module list and build commands |
| `beat-license-generator` | Building the `licensing` module |
| `printful-v2-adapter` | Building the `print-on-demand` module |
| `alembic-multi-module-migrations` | Adding a module's migrations, merging heads, the round-trip tests |
| `module-contract-lint` | Reviewing a module (or the kernel) against the contract before it merges |
| `devkit-hook-designer` | Adding a cross-module hook to the contract (search index, consent, entitlements and the rest of the 2026-11-13 roadmap hooks) |

## Project map

| Path | What |
| --- | --- |
| `SPEC.md` | The contract (v0.1) |
| `KICKOFF.md` | The first build sessions' prompt: phases K0 to K5 |
| `AGENT-GUIDE.md` | Front door for an agent building a site with DevKit |
| `schema/` | JSON Schemas: module manifest, recipe, lock file; event payload schemas land in `schema/events/` |
| `kernel/` | The always-installed core: `backend/kernel/` (Python), `migrations/`, `tests/`, `web/` |
| `modules/` | One folder per module; `modules/_template/` is the starting point |
| `recipes/` | Preset module bundles per kind of site |
| `themes/` | Token sets; Machined Light and Depth arrive in K4 (only the README so far) |
| `templates/site/` | The empty site every project starts from (built in K5) |
| `cli/` | The `devkit` CLI (built in K5) |
| `harness/` | Dev app that mounts the kernel and modules for tests and local runs; `harness/alembic/` is the one Alembic environment, `harness/migrations.py` drives it |
| `tools/` | Repo tooling: `validate_schemas.py`, `link_skills.py`, `build_common_passwords.py` (rebuilds the bundled list; steps in NOTICE) |
| `tests/` | Repo-level tests: schemas, migrations round trip, tools |
| `conftest.py` | The test run's made-up secrets and the throwaway Postgres fixtures |
| `catalog.json` | Generated index of every module (empty until the first module) |
| `docs/decisions/` | Decision records |
| `docs/HANDOFF.md` | One page, overwritten each session |
| `docs/private/` | Not in git (the repo is public): the inventory of `C:\DEV` and the name of the client folder |
| `docs/plans/` | Plans, such as the Vibrant Mindz module plan |
| `docs/contracts/` | HTTP contracts the contract suites check, starting with `auth-api.md` |
| `docs/SKILL-BACKLOG.md` | Skill ideas waiting to be built |
| `skills/` | Project skills, the source copies; K0 links them into `.claude/skills/` |
| `dev plans\` | Session prompts and working plans (the owner's convention) |

## Gotchas

- Windows: the owner's terminal is PowerShell. Python commands use the `python -m` form (`python -m pip`, `python -m pytest`). PowerShell blocks scripts by default, `Activate.ps1` and `npm.ps1` included: use `.venv\Scripts\python.exe -m ...` and `npm.cmd`, unless the owner has run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- FastAPI 0.16x keeps included routers whole in `app.routes`: walk routes with `fastapi.routing.iter_route_contexts`.
- pytest runs with `--import-mode=importlib`; the root `conftest.py` imports the real `kernel` package before collection so `kernel/tests/*` can't shadow it.
- React Router stays on 7.x (the spec) though 8.x is out; TypeScript stays on 6.0.x for typescript-eslint.
- VybeSite's code is React 18.3; lifted components move to React 19 (ref as a prop, no `forwardRef`).
- VybeSite uses JWT sessions and separate staff and member tables. DevKit uses opaque cookie sessions and one `auth_user` table (spec 14.1 and 14.5, decision 0003). Port the behavior, not the shape.

## Session end

Every session ends with `docs/HANDOFF.md` overwritten, this file's "Last Completed Task" and "Current state" updated, and a starting prompt for the next session (about 4 KB) saved as `dev plans\<date>-next-session-<topic>.md` and offered to the owner.
