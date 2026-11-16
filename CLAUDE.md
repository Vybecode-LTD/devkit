# CLAUDE.md: AI DevKit

The binding directives are in `C:\DEV\CLAUDE.md` and `C:\DEV\DIRECTIVES.md`, which Claude Code loads for every folder under `C:\DEV`. This file is the project map. Where the two differ, this file wins. `AGENTS.md` holds the same text for other agents.

## Identity

- **What:** AI DevKit, a library of reusable website modules (auth, blog, chat, payments, community, media and more) that any AI agent copies into a site's repo and wires together from a short brief.
- **Owner:** VybeCode Software (VybeCod.ing / Vibrant Mindz).
- **Not:** a hosted platform, a WordPress-style CMS, or a package registry. Modules are copied in at build time (decision 0002).
- **Path:** `C:\DEV\AI-DevKit`. **Remote:** `https://github.com/Vybecode-LTD/devkit`, **public** (decision 0011). Never commit secrets, client material or private notes; private notes go in `docs/private/` (gitignored).
- **The contract:** `SPEC.md`. Every module, the kernel and the CLI follow it. Read the sections you touch before every change.

## Current state (2026-11-16)

- Spec v0.1 written, the owner's answers applied.
- **K0 and K1 done and audited** (#1 to #31). **K2 (auth) steps 1 to 8 done** (#32 to #54; decisions 0019 to 0028 and 0030): passwords, sessions, access, sign-in and sign-up, codes and magic links, resets and email change, password change, TOTP and recovery codes, passkeys, and the undo link for an added factor. Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3 has started, in the site's order:** storage (`kernel/storage.py`, #58, decision 0032), email (`kernel/email.py`, `kernel/mail_adapters.py`, #59, decision 0033: SMTP first, Resend only where SMTP is blocked), and the kernel's 19 mails as `kernel.*` templates a site can reword (`kernel/auth/mails.py`, #60). Next: jobs (`docs/HANDOFF.md`).
- **Progress** is one record, `docs/progress.json`, made into `docs/PROGRESS.md` and the owner's visual ledger (#61). v1.0: 33% (19 of 56 steps).
- **The project becomes MechFrame after K3** (decision 0034). Keep the DevKit name until that PR.
- First real site: the new Vibrant Mindz site (`docs/plans/vibrant-mindz-module-plan.md`); its step 0 is done (#55, #56). It doubles as the spec's validation build.
- **After v1.0:** the module roadmap and ten contract hooks are decided (decision 0018, `docs/plans/module-roadmap.md`). The hooks land with `devkit-hook-designer` after the kernel phases and before blog, chat and payments are extracted (SPEC 19, phase 3).

## Last Completed Task

2026-11-16, evening (Claude Code, the owner's machine, mostly over Remote Control): K3 began. Storage (#58, decision 0032; the owner chose two buckets and moto with an opt-in live test), email with templates (#59, decision 0033; the owner chose Resend, then set SMTP first), the kernel's mails as templates (#60), the progress record, document and visual ledger the owner asked for (#61), and the owner's rename to MechFrame after K3 (decision 0034). The review bots found, and the PRs fixed: a fullwidth-quote header injection in download names (#58); unsendable templates, an unchecked worker mailer and a duplicate after a failed SMTP QUIT (#59); dropped HTML in the kernel's mails (#60); three ledger gaps (#61). Then the handoff (#62).

2026-11-16, later (Claude Code, the owner's machine, partly over Remote Control): the owner moved the Vibrant Mindz modules to the front (decision 0029, #53). Step-up by TOTP or password re-checks the session after the lock (#52; Codex found that refreshing the session row lost the token's compare-and-swap, fixed in the PR). The owner chose an undo link for a passkey or TOTP someone else adds (#54, decision 0030). Then the site's step 0: the scaffold of seven waiting modules, the recipe and the backend plan (#55), and `kernel.moderation.act` with a test that a custom role is staff (#56, decision 0031). Then the handoff (#57).

2026-11-16 (Claude Code, the owner's machine): K2 step 8, passkeys (#50, decision 0028), with `webauthn` 3.0.1. The owner chose the shape: a passkey alone signs anyone in, staff included; as a second factor and at step-up it answers options from a start route; removing any passkey is a second-factor reset; passkeys can be listed and renamed. CodeRabbit found three real gaps (the second factor's challenge kept as given and for 10 minutes, and step-up by passkey ignoring a reset that landed meanwhile), fixed in the PR with failing-first tests. Then the handoff (#51).

## Read order

1. `KICKOFF.md` (first sessions) or the newest `dev plans\*-next-session-*.md` (later sessions). It is the job.
2. `docs/HANDOFF.md`: state, next steps, blockers.
3. `SPEC.md`: the sections the job touches.
4. `docs/decisions/`: why things are the way they are.
5. `docs/private/inventory.md` (on the owner's machine only, not in git): where each piece can be lifted from in `C:\DEV`.

## Stack (decision 0001)

Python 3.12+, FastAPI, Pydantic v2 (strict), async SQLAlchemy 2 + asyncpg, Postgres 16+, Alembic with one branch per module; auth by argon2-cffi, pyotp and webauthn (passkeys, decision 0028); React 19, Vite, TypeScript strict, React Router 7 (library mode), TanStack Query; design tokens as CSS custom properties with Tailwind v4 mapped to them; openapi-typescript + openapi-fetch for the typed client; Postgres-backed job queue; S3-compatible storage (Cloudflare R2) through boto3 (decision 0032); Docker on Railway. Tests: pytest (moto for storage), Vitest + React Testing Library, Playwright.

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
| Progress document and ledger rows, after editing `docs/progress.json` | `python -m tools.progress` (`--check` only reports) |
| Brand check, before any PR that lifts code | `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"` |

## Rules

- **The spec is the contract.** A change to it is a decision record in `docs/decisions/` plus a line in its change log, in the same PR. Tell the owner which sections changed. There is no doc to sync: the claude.ai Spec doc is retired (decision 0017).
- **Provenance.** Nothing from the client folder named in `docs/private/README.md` or any client-confidential material ever enters this repo. Code lifted from VybeSite passes VybeSite's brand check before it lands: `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"`. Never copy anything from VybeSite's `dev plans\` or `snapshots\`.
- **Ask first** before anything outward-facing: creating the GitHub repo or changing its settings, Railway projects, DNS, any third-party account, any message sent for the owner.
- **No secrets, ever.** Not in the repo, not in logs, not in chat. Keys go in a host's variables, typed by the owner.
- **Tests first.** A bug fix has a test seen failing before the fix. Auth work starts from the contract tests in spec 14.13.
- **One logical change per PR,** on its own branch, with conventional commits. Read the staged diff for secrets before every commit.
- **Modules never import each other** except through `public.py` / `web/public.ts` when listed in `requires.modules` (spec section 7).
- **Progress is kept in one file,** `docs/progress.json`: every phase and step to v1.0 and after, with its status and PRs. A PR that starts, finishes or adds a step updates it and runs `python -m tools.progress`, which rewrites `docs/PROGRESS.md` and the ledger's rows; `tests/test_progress.py` fails when they're stale. The owner follows the [visual progress ledger](https://claude.ai/artifact/48auLkb7Ajmyn2SNAni9rm), made from the same rows.
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
| `modules/` | One folder per module; `modules/_template/` is the starting point, and the Vibrant Mindz scaffolds wait as `modules/_<id>/` until built |
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
| `docs/progress.json`, `docs/PROGRESS.md` | Progress to v1.0 and after: the data, and the document `tools/progress.py` makes from it |
| `docs/private/` | Not in git (the repo is public): the inventory of `C:\DEV` and the name of the client folder |
| `docs/plans/` | Plans, such as the Vibrant Mindz module plan |
| `docs/plans/module-roadmap.md` | The module roadmap after v1.0: five waves of Musts, after ten contract hooks (decision 0018) |
| `docs/plans/vibrant-mindz-backend/` | The Vibrant Mindz backend plan: its kickoff (steps 0 to 7), specs, admin map, kernel additions and extraction briefs |
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

Every session ends with `docs/HANDOFF.md` overwritten, this file's "Last Completed Task" and "Current state" updated, a starting prompt for the next session (about 4 KB) saved as `dev plans\<date>-next-session-<topic>.md` and offered to the owner, and the progress ledger republished: once `docs/progress.json` is current on `main`, upload `dev plans/progress-ledger/rows.json` to the ledger as an asset and point its `steps` dataset at the new file (`dev plans/progress-ledger/README.md`).
