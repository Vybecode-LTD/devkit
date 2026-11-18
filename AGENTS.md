# AGENTS.md: AI DevKit (same rules as CLAUDE.md)

The binding directives are in `C:\DEV\CLAUDE.md` and `C:\DEV\DIRECTIVES.md`, which Claude Code loads for every folder under `C:\DEV`. This file is the project map. Where the two differ, this file wins. `AGENTS.md` holds the same text for other agents.

## Identity

- **What:** AI DevKit, a library of reusable website modules (auth, blog, chat, payments, community, media and more) that any AI agent copies into a site's repo and wires together from a short brief.
- **Owner:** VybeCode Software (VybeCod.ing / Vibrant Mindz).
- **Not:** a hosted platform, a WordPress-style CMS, or a package registry. Modules are copied in at build time (decision 0002).
- **Path:** `C:\DEV\AI-DevKit`. **Remote:** `https://github.com/Vybecode-LTD/devkit`, **public** (decision 0011). Never commit secrets, client material or private notes; private notes go in `docs/private/` (gitignored).
- **The contract:** `SPEC.md`. Every module, the kernel and the CLI follow it. Read the sections you touch before every change.

## Current state (2026-11-17, after #73)

- Spec v0.1 written, the owner's answers applied.
- **K0 and K1 done and audited** (#1 to #31). **K2 (auth) steps 1 to 8 done** (#32 to #54; decisions 0019 to 0028 and 0030): passwords, sessions, access, sign-in and sign-up, codes and magic links, resets and email change, password change, TOTP and recovery codes, passkeys, and the undo link for an added factor. Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3 is under way, in the site's order:** storage (`kernel/storage.py`, #58, decision 0032), email (`kernel/email.py`, `kernel/mail_adapters.py`, #59, decision 0033: SMTP first, Resend only where SMTP is blocked), the kernel's 19 mails as `kernel.*` templates a site can reword (`kernel/auth/mails.py`, #60), jobs (`kernel/jobs.py`, `cron.py`, `worker.py`, #63, decision 0035: a Postgres queue enqueued in the caller's transaction, the worker in the web process by default, mail on the queue sealed, unverified accounts removed 7 days after their address was set), events (`kernel/events.py`, #65, decision 0036: deliveries are jobs written at emit, so the jobs table is the outbox; 8 tries; the kernel emits four events), audit (`kernel/audit.py`, #67, decision 0037: one append-only `kernel_audit_event` for every module, auth's renamed; `audit.record` in the caller's transaction; staff and own-activity reads; pruned after `AUDIT_KEEP_DAYS`), notifications (`kernel/notifications.py`, #69, decision 0038: `notifications.notify` in the caller's transaction, each person's choice per key, one-click unsubscribe), moderation (`kernel/moderation.py`, #71, decision 0039: kinds a module declares in `moderation.py`, one case per thing, filters that hold and never drop, dismiss, hide, delete, time-outs, and bans as suspensions at `POST /api/auth/admin/users/{id}/suspend`), and public rendering (`kernel/server_copy.py`, `shell.py`, #73, decision 0041: a module's `PAGES` answers each public address with its head, words and JSON-LD, the kernel serves `WEB_DIST` with real 404s and writes `sitemap.xml`, `robots.txt` and `llms.txt`, member pages are `noindex`). **K3's gate passed** (#75, `dev plans/2026-11-17-k3-gate-evidence.md`) on the nine services built; retention and the AI client are outside it (the owner). npm audit runs with an expiring allowlist (`tools/npm_audit.py`, decision 0015 amended). Next: the rename to MechFrame (`docs/HANDOFF.md`).
- **Progress** is one record, `docs/progress.json`, made into `docs/PROGRESS.md` and the owner's visual ledger (#61). v1.0: 44% (25 of 56 steps).
- **The project becomes MechFrame after K3** (decision 0034). Keep the DevKit name until that PR.
- **The admin shell** is built in K4 to the Vibrant Mindz canvas Admin design, styled by tokens, for every site: only its generic parts in the kernel, checked in the site's dark theme and Machined Light (decision 0040, amending 0008).
- First real site: the new Vibrant Mindz site (`docs/plans/vibrant-mindz-module-plan.md`); its step 0 is done (#55, #56). It doubles as the spec's validation build.
- **After v1.0:** the module roadmap and ten contract hooks are decided (decision 0018, `docs/plans/module-roadmap.md`). The hooks land with `devkit-hook-designer` after the kernel phases and before blog, chat and payments are extracted (SPEC 19, phase 3).

## Last Completed Task

2026-11-17, night Eastern (Claude Code, the owner's machine): K3 public rendering (#73, decision 0041), contract first; the owner approved it with the five answers recommended. `kernel.server_copy` and `kernel.shell`: a module's `PAGES` answers `page(db, path, params)` for each address its `routes.public` patterns match (the most fixed segments win, among the modules on), the kernel serves `WEB_DIST` or a minimal shell with real 404s and 503s, and writes `sitemap.xml`, `robots.txt` and `llms.txt`; nh3 is a new hash-pinned dependency. Codex found a redirect's query landing inside its fragment; CodeRabbit found four (matching must use the modules on, a failed switch read aborting the page's transaction, and two robots.txt member-rule findings, which the owner settled by keeping member pages `noindex` rather than disallowed). All fixed with failing-first tests; 35 mutants, all killed. main's push runs are red on a picomatch advisory with no fix; an allowlist is parked in `dev plans/npm-audit-allowlist/` for the owner. The session landed #73 itself. Then the handoff (#74).

2026-11-17, evening Eastern (Claude Code, the owner's machine, mostly over Remote Control): K3 moderation (#71, decision 0039), contract first; the owner approved it with the five answers recommended. Suspension follows the routes and codes `docs/contracts/auth-api.md` already had. Building found that an `ON CONFLICT` partial-index predicate sent as a bound value stops matching once a prepared statement turns generic (the sixth run). Codex and CodeRabbit found, and the PR fixed with failing-first tests: kinds the harness never discovered, NUL characters as 500s, a dismissed hold with no way back into view (`Kind.dismissed`), two owners able to suspend each other at once (the actor's row locked too), and a queue ban without step-up. 21 mutants, all killed. The owner's admin-shell decision was recorded (0040), and the public rendering contract written and approved. Then the handoff (#72).

2026-11-17, afternoon Eastern (Claude Code, the owner's machine, part over Remote Control): K3 notifications (#69, decision 0038), contract first. The owner approved it with the four answers recommended: kept 90 days after read and a year at most, choices per key only, the one-click link for that key alone, digests later. Codex found nothing; CodeRabbit found a long `List-Unsubscribe` folded into encoded words over SMTP, a notice added before its email's checks, and an unsubscribe that could undo a concurrent choice; all fixed in the PR with failing-first tests, one a real race. 40 mutants, all killed. The session landed #68 and #69 itself. Then the handoff (#70).

2026-11-17, morning Eastern (Claude Code, the owner's machine): K3 audit (#67, decision 0037), contract first. The owner approved it with the four answers recommended: one table (auth's renamed `kernel_audit_event`), admins read everything and each person their own security activity, a year by default (`AUDIT_KEEP_DAYS`), and an append-only trigger. The staff's reader moved under `/api/kernel/admin` for the admin gate. Codex found an overflowing cursor; CodeRabbit found SPEC 7's list names (`cursor`, `next_cursor`), NUL characters, an address as a details key and TRUNCATE; all fixed in the PR with failing-first tests. 39 mutants, all killed. The session landed #67 itself. Then the handoff (#68).

## Read order

1. `KICKOFF.md` (first sessions) or the newest `dev plans\*-next-session-*.md` (later sessions). It is the job.
2. `docs/HANDOFF.md`: state, next steps, blockers.
3. `SPEC.md`: the sections the job touches.
4. `docs/decisions/`: why things are the way they are.
5. `docs/private/inventory.md` (on the owner's machine only, not in git): where each piece can be lifted from in `C:\DEV`.

## Stack (decision 0001)

Python 3.12+, FastAPI, Pydantic v2 (strict), async SQLAlchemy 2 + asyncpg, Postgres 16+, Alembic with one branch per module; auth by argon2-cffi, pyotp and webauthn (passkeys, decision 0028); nh3 for HTML cleaned to an allowlist (decision 0041); React 19, Vite, TypeScript strict, React Router 7 (library mode), TanStack Query; design tokens as CSS custom properties with Tailwind v4 mapped to them; openapi-typescript + openapi-fetch for the typed client; Postgres-backed job queue; S3-compatible storage (Cloudflare R2) through boto3 (decision 0032); Docker on Railway. Tests: pytest (moto for storage), Vitest + React Testing Library, Playwright.

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
| Jobs worker, a process of its own | `python -m harness.worker`, with `JOBS_IN_WEB=false` on the web app (by default the web app runs one; decision 0035) |
| Audit Python dependencies | `python -m pip_audit --strict --require-hashes --disable-pip -r requirements.txt -r requirements-dev.txt` |
| Audit web dependencies, with the expiring allowlist (`tools/npm_audit_allow.json`, decision 0015) | `python -m tools.npm_audit` |
| Web install | `npm ci` |
| Web tests, lint, types, build | `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` |
| Link the project skills for Claude Code | `python -m tools.link_skills` |
| Progress document and ledger rows, after editing `docs/progress.json` | `python -m tools.progress` (`--check` only reports) |
| Event payloads as JSON Schema, after declaring or changing one | `python -m tools.event_schemas` (`--check` only reports) |
| Brand check, before any PR that lifts code | `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"` |

## Rules

- **The spec is the contract.** A change to it is a decision record in `docs/decisions/` plus a line in its change log, in the same PR. Tell the owner which sections changed. There is no doc to sync: the claude.ai Spec doc is retired (decision 0017).
- **Provenance.** Nothing from the client folder named in `docs/private/README.md` or any client-confidential material ever enters this repo. Code lifted from VybeSite passes VybeSite's brand check before it lands: `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"`. Never copy anything from VybeSite's `dev plans\` or `snapshots\`.
- **Ask first** before anything outward-facing: creating the GitHub repo or changing its settings, Railway projects, DNS, any third-party account, any message sent for the owner.
- **No secrets, ever.** Not in the repo, not in logs, not in chat. Keys go in a host's variables, typed by the owner.
- **Tests first.** A bug fix has a test seen failing before the fix. Auth work starts from the contract tests in spec 14.13.
- **One logical change per PR,** on its own branch, with conventional commits. Read the staged diff for secrets before every commit.
- **Pushing and merging are the agent's call in this project:** the owner stated it explicitly on 2026-11-17 ("use your best judgement on pushing and merging"), under the rule in `C:\DEV\knowledge\owner.md` (Git, PRs and CI). Push a PR branch once its local suites are green; land the PR once "CI result" is green on its head and the review bots have no open findings. Land by fast-forward (`git merge-base --is-ancestor origin/main <sha>`, then `git push origin <sha>:refs/heads/main`), never `gh pr merge`, then delete the branch here and on GitHub. Everything else outward-facing still asks first.
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
