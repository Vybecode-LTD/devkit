# AGENTS.md: MechFrame (same rules as CLAUDE.md)

The binding directives are in `C:\DEV\CLAUDE.md` and `C:\DEV\DIRECTIVES.md`, which Claude Code loads for every folder under `C:\DEV`. This file is the project map. Where the two differ, this file wins. `AGENTS.md` holds the same text for other agents.

## Identity

- **What:** MechFrame, a library of reusable website modules (auth, blog, chat, payments, community, media and more) that any AI agent copies into a site's repo and wires together from a short brief.
- **Owner:** VybeCode Software (VybeCod.ing / Vibrant Mindz).
- **Not:** a hosted platform, a WordPress-style CMS, or a package registry. Modules are copied in at build time (decision 0002).
- **Path:** `C:\DEV\AI-DevKit`. **Remote:** `https://github.com/mechframe/mechframe` (decision 0034), **public** (decision 0011). Never commit secrets, client material or private notes; private notes go in `docs/private/` (gitignored).
- **The contract:** `SPEC.md`. Every module, the kernel and the CLI follow it. Read the sections you touch before every change.

## Current state (2026-11-21; the kernel closed, #96; hooks 1 to 3 of the ten, #97 to #99)

- Spec v0.1 written, the owner's answers applied.
- **K0 and K1 done and audited** (#1 to #31). **K2 (auth) steps 1 to 8 done** (#32 to #54; decisions 0019 to 0028 and 0030): passwords, sessions, access, sign-in and sign-up, codes and magic links, resets and email change, password change, TOTP and recovery codes, passkeys, and the undo link for an added factor. Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3 is done, in the site's order:** storage (`kernel/storage.py`, #58, decision 0032), email (`kernel/email.py`, `kernel/mail_adapters.py`, #59, decision 0033: SMTP first, Resend only where SMTP is blocked), the kernel's 19 mails as `kernel.*` templates a site can reword (`kernel/auth/mails.py`, #60), jobs (`kernel/jobs.py`, `cron.py`, `worker.py`, #63, decision 0035: a Postgres queue enqueued in the caller's transaction, the worker in the web process by default, mail on the queue sealed, unverified accounts removed 7 days after their address was set), events (`kernel/events.py`, #65, decision 0036: deliveries are jobs written at emit, so the jobs table is the outbox; 8 tries; the kernel emits four events), audit (`kernel/audit.py`, #67, decision 0037: one append-only `kernel_audit_event` for every module, auth's renamed; `audit.record` in the caller's transaction; staff and own-activity reads; pruned after `AUDIT_KEEP_DAYS`), notifications (`kernel/notifications.py`, #69, decision 0038: `notifications.notify` in the caller's transaction, each person's choice per key, one-click unsubscribe), moderation (`kernel/moderation.py`, #71, decision 0039: kinds a module declares in `moderation.py`, one case per thing, filters that hold and never drop, dismiss, hide, delete, time-outs, and bans as suspensions at `POST /api/auth/admin/users/{id}/suspend`), and public rendering (`kernel/server_copy.py`, `shell.py`, #73, decision 0041: a module's `PAGES` answers each public address with its head, words and JSON-LD, the kernel serves `WEB_DIST` with real 404s and writes `sitemap.xml`, `robots.txt` and `llms.txt`, member pages are `noindex`). **K3's gate passed** (#75, `dev plans/2026-11-17-k3-gate-evidence.md`) on the nine services built; retention and the AI client are outside it (the owner). npm audit runs with an expiring allowlist (`tools/npm_audit.py`, decision 0015 amended). The rename to MechFrame landed after it (#76). Next: K4 (`docs/HANDOFF.md`).
- **K4 is done** (`dev plans/contracts/k4-web-kernel.md`, decision 0042, approved 2026-11-18): eight PRs, all eight landed (#78 to #87); #88 adds the role-change event K4.7 missed (decision 0045, amended). #78, the typed client: `Answer` models, `kernel/openapi.json`, `kernel/web/src/api/`. #79, the app shell: the kernel's pages in `kernel.json`, `mountApp`, `useSession`, guards, slots, `<Seo>`, Playwright and axe. #80, the themes: `themes/`, `tools/themes.py`, the colour lint. #82, the UI kit: `kernel/web/src/ui/` (its `README.md`), the admin's focus ring, `color.border-control` and the pill tints, and the kit's page `/kit.html` that `kernel/tests/e2e/kit.spec.ts` checks. #83, the sign-in and account screens (decision 0043): `kernel/web/src/auth/` and `account/`, the sign-in frame, the step-up dialog, the site's look in the kit, the device routes and `GET /api/auth/security`, and `kernel/tests/e2e/sign-in.spec.ts`. #84, the admin shell (decision 0044): `kernel/web/src/admin/` (the frame's sections, breadcrumb, Ctrl K, notices and Menu; `AdminPage`; Dashboard and Activity), `GET /api/kernel/admin/attention`, the staff's log naming its people, `kernel.jobs.manage` (`kernel_0011`), `StatCard` and the info tone, and `kernel/tests/e2e/admin.spec.ts`. #85, people and roles (decision 0045): `kernel/auth/roles.py` (the People list, granting roles, the roles read, role editing, contract tests first), `auth.role.manage` (`kernel_0012`), `People.tsx` and `Roles.tsx`. #87, settings and System (decision 0046, contract change 19): `kernel/admin.py` (each section's form, save and history; the module switches, audited and emitting `kernel.module.*`; System and the failed jobs' retry and discard, contract tests first), the sign-up mode as the section `kernel.auth`, the harness's probe modules (`harness/probe.py`), `useSettings`, and `Site.tsx`, `Features.tsx` and `System.tsx`. **K4's gate passed** (#90, `dev plans/2026-11-20-k4-gate-evidence.md`) once #89 fixed the stale People list it found (a role save landing while a search's first page loads). K5 is next.
- **K5 is done** (`dev plans/contracts/k5-cli-and-site-template.md`, decisions 0047 to 0051, approved 2026-11-20 with the five recommended answers; changes 1 to 9): six PRs from #91. #91, the CLI's core: `cli/mechframe/` (`python -m mechframe`, or `mechframe` and `mf` after `python -m pip install --no-deps --no-build-isolation -e .`), copying from and checking against its own checkout; the lock's hashes (`\r\n` read as `\n`); `mechframe check` (edited, missing and added files, copies behind, open advisories; exits 2, 1 or 0); `mechframe catalog`; `schema/advisories.schema.json`. #92, the site template: `templates/site/` (the harness made into a site; `templates/README.md`), `mechframe new` (kernel only), `kernel.load_module`, the site's own pages (`create_app(site=server_copy.SitePages(...))`, `defineSite` for `mountApp({ site })`: always on, first in a tie, `site` no module's id), `.railway/railway.ts` in place of the deprecated `railway.toml` (the owner's choice, checked live on the throwaway `mechframe-iac-probe`: an apply deletes the service's unlisted variables), `tools/site_template.py` and `tools/site_smoke.py` (E2E's `site-smoke` job). #93, SPEC 10's confirmation before a destructive migration (the owner, 2026-11-20; decision 0049): `kernel.migrate`, the harness's and every site's migrations command; once its branch holds data, an upgrade stops before a revision marked `destructive = True`, naming it, until `--confirm-destructive <revision>` names it back. #94, `add`, `remove` and `new --recipe` (decision 0050), on the fixture modules in `cli/tests/fixtures/`: `requires` ranges (a pre-release counts), both registries and the lock written whole, a module's settings in `.env.example` and `.railway/railway.ts`, whole or not at all; `remove` keeps a module's tables, migrations and `railway.ts` lines. #95, `create-owner` (decision 0051): `kernel.auth.owners.create_owner` gives an address's account the owner role and answers a reset link's token, every way into the account closed first; with an owner already, only an owner's own address gets a new link. **K5's gate passed** (#96, `dev plans/2026-11-20-k5-gate-evidence.md`): `tools.site_smoke` made `test-site`, kernel only and then with the fixture modules, every step green and `mechframe check` exiting 0. The kernel's close (KICKOFF) is in the same file: SPEC 16's rows green in CI, the auth contract tests passing but K2's 9 to 11 (decision 0029), the scans clean, and the spec sections changed since K0. After it: decision 0018's ten contract hooks, then the modules' wave 1.
- **The ten contract hooks** (`dev plans/contracts/hooks.md`, decision 0052, approved 2026-11-20 "as recommended"), one PR each in this order: content lifecycle, taxonomy, search index, seed data, bot check, consent categories, export and erase, dashboard cards, entitlements, profile tabs; entitlements and profile tabs wait until just before Vibrant Mindz's step 5 and wave 2b (the owner, 2026-11-21). **Hook 1, content lifecycle, is #97:** `kernel.lifecycle` (the `Publishable` mixin, `publish`, `schedule`, `unpublish`, `visible`, and the kernel's `kernel.publish_due` job), module.json's `content_types`, and SPEC 7's new index "Hooks every module can fill". **Hook 2, taxonomy, is #98:** `kernel.taxonomy` (`tag`, `terms_for`, `tagged`, `untag_all`), module.json's `vocabularies` and `content_types[].taxonomy`, the tables `kernel_vocabulary`, `kernel_term` and `kernel_term_link` (`kernel_0013`), `GET /api/kernel/terms` and the admin's term routes under `kernel.taxonomy.manage` (admin, editor). **Hook 3, search index, is #99:** `kernel.search` (`search.py`'s `SEARCH`, a tuple of `search.Source`; `index`, `remove`, `find`), module.json's `content_types[].search`, the table `kernel_search_document` (`kernel_0014`, its `tsv` a stored generated column with a GIN index), the kernel hearing `kernel.content.*` (its jobs `kernel.search_published` and `kernel.search_unpublished`), the on-demand `kernel.search_reindex`, `GET /api/kernel/search` (public, 30 a minute) and `SEARCH_LANGUAGE`. The harness's `probe` fills each hook on tables of its own (`harness.probe.TABLES`), and `probe-addon` none. Next: the plan to Vibrant Mindz's step 1, `dev plans/2026-11-21-vibrant-mindz-push-plan.md`, from its session M1 (`dev plans/2026-11-21-next-session-m1-kit-and-hooks-4-to-6.md`): the kit's two fixes, then hooks 4 to 6. A Vibrant Mindz session builds the site's front end alongside. A public name and handle for a person is asked again before hook 10.
- **Progress** is one record, `docs/progress.json`, made into `docs/PROGRESS.md` and the owner's visual ledger (#61). v1.0: 70% (43 of 61 steps).
- **The project is MechFrame** (decision 0034, #76); it was AI DevKit until K3. The repo is `mechframe/mechframe`, the planned CLI `mechframe` (also `mf`), the cookies `__Host-mf_*`, the variables `MECHFRAME_*`; the Python import stays `kernel`. Decision records and other history keep the old name as written.
- **The admin shell** is built in K4 to the Vibrant Mindz canvas Admin design, styled by tokens, for every site: only its generic parts in the kernel, checked in the site's dark theme and Machined Light (decision 0040, amending 0008).
- First real site: the new Vibrant Mindz site (`docs/plans/vibrant-mindz-module-plan.md`); its step 0 is done (#55, #56). It doubles as the spec's validation build.
- **After v1.0:** the module roadmap and ten contract hooks are decided (decision 0018, `docs/plans/module-roadmap.md`). The hooks land with `mechframe-hook-designer` after the kernel phases and before blog, chat and payments are extracted (SPEC 19, phase 3).

## Last Completed Task

2026-11-21, morning Eastern (Claude Code, the owner's machine): #98 landed at `747e5f6` and the ledger was republished. Built #99, hook 3, search index (decision 0052), tests first: `kernel.search`, its start's checks, the kernel's table in `kernel_0014`, the kernel's own listeners to `kernel.content.published` and `.unpublished` (the first kernel listeners: `app.KERNEL_LISTENERS`), the reindex job, `GET /api/kernel/search`, `SEARCH_LANGUAGE` (one of Postgres 16's text search configurations), and the probe's notes searchable with a body. Either listener indexes the thing as it is now, so deliveries in any order leave the index right; advisory locks make one document's changes take turns and a reindex wait for none. Nine mutants were caught. The contract's "Changes after approval" says what moved from §2 (`SEARCH` a tuple, the job `kernel.search_reindex`). SPEC 5, 6, 7, 10 and 14.11 changed. CodeRabbit's three findings were fixed with tests seen failing (the caller's locks before search's; a reindex on one connection; the extractor's step). Then, at the owner's request, wrote the plan to Vibrant Mindz's step 1 (#100, `dev plans/2026-11-21-vibrant-mindz-push-plan.md`): hooks 9 and 10 wait, and a Vibrant Mindz session builds the site's front end alongside (the owner's calls, 2026-11-21).

2026-11-20, night Eastern, later (Claude Code, the owner's machine): #97 landed at `cc3929b` and the ledger was republished. Built #98, hook 2, taxonomy (decision 0052), tests first: `kernel.taxonomy`, the vocabularies and their checks at start, the kernel's term tables in `kernel_0013` with `kernel.taxonomy.manage` seeded for admin and editor, the public terms list, and staff's add, change and delete (audited; the vocabulary's row locked so no two moves make a circle). The probe's notes take `topics` and `tags`. Five mutants were caught. A fixture in `test_lifecycle.py` emptied the kernel's publishable types for the contract suite's long-lived app when it ran first; both hooks' fixtures now use monkeypatch. SPEC 5, 6, 7, 10 and 14.11 changed.

2026-11-20, night Eastern (Claude Code, the owner's machine): #96 landed at `407dadb` and the ledger was republished. Wrote the ten hooks' contract (`dev plans/contracts/hooks.md`); the owner approved it as recommended: the order, `content_types` shared by three hooks, hook 7 building 14.7's export, `CONSENT_MODE=ask`, and a profile handle asked again before hook 10. Built #97, hook 1, content lifecycle (decision 0052), tests first: `kernel.lifecycle`, `content_types`, discovery of `lifecycle.py`'s `PUBLISHABLE`, the start's checks, the probe's publishable notes with a public page, and an HTTP contract test; three mutants caught. SPEC 5, 6, 7 (the hooks index), 10 and 11 changed.

## Read order

1. `KICKOFF.md` (first sessions) or the newest `dev plans\*-next-session-*.md` (later sessions). It is the job.
2. `docs/HANDOFF.md`: state, next steps, blockers.
3. `SPEC.md`: the sections the job touches.
4. `docs/decisions/`: why things are the way they are.
5. `docs/private/inventory.md` (on the owner's machine only, not in git): where each piece can be lifted from in `C:\DEV`.

## Stack (decision 0001)

Python 3.12+, FastAPI, Pydantic v2 (strict), async SQLAlchemy 2 + asyncpg, Postgres 16+, Alembic with one branch per module; auth by argon2-cffi, pyotp and webauthn (passkeys, decision 0028); nh3 for HTML cleaned to an allowlist (decision 0041); React 19, Vite, TypeScript strict, React Router 7 (library mode), TanStack Query; design tokens as CSS custom properties with Tailwind v4 mapped to them; openapi-typescript + openapi-fetch for the typed client, with openapi-react-query for its TanStack Query hooks (decision 0042); uqr for the authenticator app's QR code (decision 0043); Postgres-backed job queue; S3-compatible storage (Cloudflare R2) through boto3 (decision 0032); Docker on Railway. Tests: pytest (moto for storage), Vitest + React Testing Library (jsQR reads a drawn QR code back), Playwright.

## Commands

From the repo root, in PowerShell. Python commands use the `python -m` form.

| What | Command |
| --- | --- |
| Python environment, first time | `py -3.12 -m venv .venv`, then `.venv\Scripts\Activate.ps1` |
| Install Python dependencies | `python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt` |
| Re-pin after editing a `.in` file | `python -m uv pip compile requirements.in --generate-hashes --universal --python-version 3.12 -o requirements.txt`, and the same for `requirements-dev.in` into `requirements-dev.txt` |
| Test Postgres | `docker compose up -d db`; or any local Postgres 16+ with a role that has CREATEDB and `TEST_DATABASE_URL` pointing at it (compose and CI call it `mechframe`; the owner's machine keeps its `devkit` role on port 55432) |
| Python tests | `python -m pytest` (add `-m "not db"` to run without Postgres) |
| Lint, format, types | `python -m ruff check .`, `python -m black .`, `python -m mypy` |
| Manifests against the schemas | `python -m tools.validate_schemas` |
| Migrations | `python -m harness.migrations upgrade` (also `downgrade`, `heads`, `history`, `current`), with `DATABASE_URL` set |
| Jobs worker, a process of its own | `python -m harness.worker`, with `JOBS_IN_WEB=false` on the web app (by default the web app runs one; decision 0035) |
| Audit Python dependencies | `python -m pip_audit --strict --require-hashes --disable-pip -r requirements.txt -r requirements-dev.txt` |
| Audit web dependencies, with the expiring allowlist (`tools/npm_audit_allow.json`, decision 0015) | `python -m tools.npm_audit` |
| Web install | `npm ci` |
| Web tests, lint, types, build | `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` |
| Web coverage (85 % of lines, the contract's floor; CI's Web job runs it) | `npm run test:coverage` |
| End-to-end tests (Playwright 1.64.1, Chromium build 1248, axe), locally before each push | once on a new machine, `npx playwright install chromium` (`npm ci` doesn't fetch the browser); then `npm run build`, and `npm run e2e` with `TEST_DATABASE_URL` set; it starts its own `python -m harness.e2e` on a `mechframe_e2e` database made fresh each run, never one already running, and reads no `.env`. CI runs them on main's pushes, weekly and by hand (`e2e.yml`), never on a PR |
| Link the project skills for Claude Code | `python -m tools.link_skills` |
| Progress document and ledger rows, after editing `docs/progress.json` | `python -m tools.progress` (`--check` only reports) |
| Each theme's `tokens.css` and `tailwind.css`, after editing a `tokens.json` | `python -m tools.themes` (`--check` only reports) |
| Event payloads as JSON Schema, after declaring or changing one | `python -m tools.event_schemas` (`--check` only reports) |
| The committed OpenAPI specs and the web's API types, after changing a route or its answer | `python -m tools.openapi`, then `npm run api:types` (`--check` and `npm run api:check` only report; decision 0042) |
| The CLI: a new site, its modules, its edits, versions and advisories; the catalog (decisions 0047 and 0050) | After the pinned requirements, `python -m pip install --no-deps --no-build-isolation -e .` once, then `mechframe new <dir> [--recipe <id>]`, `mechframe add <id> --site <dir>`, `mechframe remove <id> --site <dir>`, `mechframe check --site <dir>` and `mechframe catalog` (`--check` only reports); or `python -m mechframe` with `$env:PYTHONPATH = "cli"` |
| A new site, kernel only (decision 0048) | `python -m mechframe new <dir> --name "<site name>" [--theme <name>]` with `cli` on the path; the folder must be empty or not there yet |
| The site's first owner, from its server (decision 0051) | `mechframe create-owner <email> --site <dir>`: runs the site's `python -m app.owner <email>` with its `.venv` and prints a one-time link to set the password; with an owner already, only an owner's own address gets one |
| The template's web package and lockfile, after a bump in the root's `package.json` | `python -m tools.site_template` (needs npm and the registry; `--check` only reports) |
| A new site made and run from nothing: venv, pins, lint, migrations, tests, `npm ci`, the build, `railway.ts`'s types, Playwright, `mechframe check` (CI's E2E workflow runs it; never on a PR) | `python -m tools.site_smoke` with `TEST_DATABASE_URL` set and npm on the path (`--keep` keeps the folder); about 5 minutes once pip's cache is warm |
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
| `mechframe-module-extractor` | Lifting a feature from another project into `modules/` |
| `mechframe-site-picker` | Turning a site brief into a module list and build commands |
| `beat-license-generator` | Building the `licensing` module |
| `printful-v2-adapter` | Building the `print-on-demand` module |
| `alembic-multi-module-migrations` | Adding a module's migrations, merging heads, the round-trip tests |
| `module-contract-lint` | Reviewing a module (or the kernel) against the contract before it merges |
| `mechframe-hook-designer` | Adding a cross-module hook to the contract (search index, consent, entitlements and the rest of the 2026-11-13 roadmap hooks) |

## Project map

| Path | What |
| --- | --- |
| `SPEC.md` | The contract (v0.1) |
| `KICKOFF.md` | The first build sessions' prompt: phases K0 to K5 |
| `AGENT-GUIDE.md` | Front door for an agent building a site with MechFrame |
| `schema/` | JSON Schemas: module manifest, recipe, lock file; event payload schemas land in `schema/events/` |
| `kernel/` | The always-installed core: `backend/kernel/` (Python), `migrations/`, `tests/`, `web/`, and `openapi.json` (generated) |
| `modules/` | One folder per module; `modules/_template/` is the starting point, and the Vibrant Mindz scaffolds wait as `modules/_<id>/` until built |
| `recipes/` | Preset module bundles per kind of site |
| `themes/` | Token sets, one folder each: `machined-light` (the default) and `vibrant-mindz`; `README.md` lists the kernel's required tokens |
| `templates/site/` | The empty site `mechframe new` starts every project from (#92; `templates/README.md`): the harness made into a site, its own pages in `backend/app/site/` and `web/src/site/`, Railway as code in `.railway/railway.ts` |
| `cli/` | The `mechframe` CLI: `cli/mechframe/` and its tests in `cli/tests/` (`cli/README.md`; built in K5) |
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
- VybeSite uses JWT sessions and separate staff and member tables. MechFrame uses opaque cookie sessions and one `auth_user` table (spec 14.1 and 14.5, decision 0003). Port the behavior, not the shape.

## Session end

Every session ends with `docs/HANDOFF.md` overwritten, this file's "Last Completed Task" and "Current state" updated, a starting prompt for the next session (about 4 KB) saved as `dev plans\<date>-next-session-<topic>.md` and offered to the owner, and the progress ledger republished: once `docs/progress.json` is current on `main`, upload `dev plans/progress-ledger/rows.json` to the ledger as an asset and point its `steps` dataset at the new file (`dev plans/progress-ledger/README.md`).
