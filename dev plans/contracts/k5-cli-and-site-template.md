---
feature: K5 CLI and site template (the mechframe commands, the lock file, templates/site, the start command, the catalog)
status: approved
approved: 2026-11-20 (the owner: "Approve as recommended", the five answers in §8)
plan: KICKOFF.md K5; SPEC 4, 12, 13, 16 and 17; cli/README.md; docs/progress.json's K5
pr: 91 first (predicted; #90 is the last); the order in §4
---

# Contract: K5 CLI and site template

## 1. Goal

An agent turns a brief into a running site with one command. `mechframe new` writes a site that builds, migrates, passes its own tests and deploys to Railway with a real client address. `mechframe add` and `remove` change its modules, and `mechframe check` says what the site has edited, what is behind, and which advisories it must patch.

## 2. Interfaces

**The CLI** is `cli/mechframe/`: Python 3.12, the standard library plus `jsonschema`. From a MechFrame checkout it runs as `python -m mechframe` (`cli` on the path). After the pinned requirements, `python -m pip install --no-deps --no-build-isolation -e .` makes it also answer to `mechframe` and `mf` (`[project.scripts]` in `pyproject.toml`). It copies from, and checks against, **the checkout its own code sits in** (`mechframe.source.ROOT`). It never fetches anything.

| Command | Does | Exits |
| --- | --- | --- |
| `new <dir> [--name "<site name>"] [--recipe <id>] [--theme <name>]` | Copies `templates/site/` and the kernel. Writes `SITE_NAME` into `.env.example`, the theme's `tokens.css`, the registries and the lock. Then runs `add` for each of the recipe's modules. Refuses a `<dir>` that isn't empty, and a recipe naming a module not built yet (it lists them). The theme defaults to the recipe's, else `machined-light`. Prints the next commands | 0; 2 when refused |
| `add <id> [--site <dir>]` | SPEC 12 steps 1 to 5: requires and conflicts against the lock, copy, both registries, env vars appended to `.env.example`, version and hashes into the lock. Prints steps 6 and 7 (migrations, tests) for the site's own Python to run | 0; 2 |
| `remove <id> [--site <dir>]` | Refuses while another module requires `<id>`. Removes its files, registry entries and lock entry, and comments out its env vars. Keeps its tables | 0; 2 |
| `check [--site <dir>] [--json]` | The lock validates against `schema/lock.schema.json`, and `kernel.json` and each copied `module.json` against theirs. Every recorded file: edited, missing, or added in a copied folder. Each copy's version against the checkout's. Open advisories in `advisories.json` for the site's versions. Edits and versions behind are reported, not failures | 1 on an open high or critical advisory; 2 on an invalid lock or copied manifest (change 2); else 0 |
| `catalog [--check]` | Writes `catalog.json` from every built module's manifest: `_` folders and `planned` ones left out; SPEC 17's fields plus `name`, `version` and `category`; sorted by id; `generated_at` stays null, so the file only changes when a manifest does | `--check`: 1 when stale |
| `create-owner <email> [--site <dir>]` | Runs the site's `python -m app.owner <email>` with the site's own `.venv` Python | as `app.owner` |

`--site` defaults to the current folder.

**The lock file** keeps its schema. Paths are relative to the site, with `/`. Each hash is `sha256:` of the file's bytes with `\r\n` read as `\n`, so line endings that Git rewrites in a checkout don't count as edits. `recipe` is null for a kernel-only site.

**The site**, copied from `templates/site/` (SPEC 4 gains these exact paths):

| Path in the site | Holds |
| --- | --- |
| `backend/app/main.py` | `app = create_app(modules=installed(MODULE_IDS), config=KernelConfig())` |
| `backend/app/modules.py` | `MODULE_IDS: tuple[str, ...]`, written by `add` and `remove` ("Don't edit by hand") |
| `backend/app/__init__.py` | Puts `backend/modules` on `sys.path`, as `harness/__init__.py` does for the repo |
| `backend/app/migrations.py`, `worker.py`, `owner.py` | `python -m app.migrations upgrade` (and the harness's other verbs), `python -m app.worker`, `python -m app.owner <email>` |
| `backend/alembic/env.py`, `script.py.mako` | The harness's: one environment, every branch |
| `backend/kernel/` | `kernel/backend/kernel/` and `kernel/kernel.json` |
| `backend/migrations/kernel/`, `backend/migrations/<id>/` | `kernel/migrations/`, and each module's `migrations/` |
| `backend/modules/<id_>/` | `modules/<id>/backend/<id_>/`, with its `module.json`, `MODULE.md` and `CHANGELOG.md` |
| `backend/tests/` | `conftest.py` (a throwaway Postgres), `test_app.py`, `test_migrations.py`, `test_pages.py` |
| `web/src/kernel/`, `web/src/modules/<id>/` | `kernel/web/` and `modules/<id>/web/`, their tests left out |
| `web/src/modules.ts` | `export const modules: ModuleDefinition[]`, written by `add` and `remove` |
| `web/src/main.tsx` | Imports `./theme/tokens.css`, then `mountApp({ modules })` |
| `web/src/theme/tokens.css` | `themes/<theme>/tokens.css` |
| `web/src/site/` | The site's own pages (§8 question 4) |
| `web/package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, `playwright.config.ts`, `e2e/smoke.spec.ts` | The kernel's dependencies at MechFrame's exact versions; `@/kernel` resolving to `src/kernel/index.ts` |
| `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` | MechFrame's hashed pins; ruff, black, mypy and pytest set up as here |
| `.env.example` | The harness's, plus `SITE_NAME`, `CLIENT_IP_HEADER=X-Real-IP` and `FORWARDED_ALLOW_IPS` (§8 question 3) |
| `Dockerfile` | Node builds `web/dist`; Python runs `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips $FORWARDED_ALLOW_IPS` with `WEB_DIST=/app/web/dist` |
| `railway.toml` | The Dockerfile builder; `preDeployCommand = "python -m app.migrations upgrade"`; `healthcheckPath = "/api/kernel/health"` |
| `compose.yaml`, `.gitignore`, `.gitattributes`, `README.md`, `CLAUDE.md`, `AGENTS.md` | Local Postgres; the site's rules: its code in `site/` folders, copied folders edited only when settings, slots and events can't do it, `mechframe check` before each PR |

**Kernel addition:** `kernel.modules.load_module(manifest: Path) -> InstalledModule` builds an installed module from its manifest and its package's fixed names (decision 0009). It is lifted out of `harness/registry.py`, so the harness and every site build modules the same way.

## 3. Data

None: no tables or migrations. `app.owner` writes an account through the kernel's own functions.

## 4. Files, in PR order

1. **#91, the CLI's core:** `cli/mechframe/` (`__main__.py`, `source.py`, `lock.py`, `hashes.py`, `catalog.py`, `check.py`), `cli/tests/`, `pyproject.toml`'s scripts, the CLI in CI's Python job. Also this contract, decision 0047, SPEC 4, 12, 13 and 17, and `cli/README.md`.
2. **#92, the site template:** `templates/site/` (the table above), `load_module` with the harness moved onto it, `mechframe new` (kernel only), and `tools/site_smoke.py`. The smoke tool builds a new site in a temporary folder: venv, `pip install --require-hashes`, `npm ci`, build, migrations, the site's tests and `check`. CI's E2E workflow runs it, on main and weekly, never on a PR. A test holds the template's web dependencies equal to the root `package.json`'s.
3. **#93, SPEC 10's confirmation before a destructive migration** (change 7): `kernel.migrate`, with the harness's and the template's `migrations` on it, tests first.
4. **#94, `add` and `remove`:** the registries, `.env.example`, the lock, `new --recipe`; tested on fixture modules in `cli/tests/fixtures/`, since no module is built yet.
5. **#95, `create-owner`:** `kernel.auth.owners.create_owner(db, email) -> str`, the template's `app/owner.py`, the CLI's wrapper, tests first.
6. **#96, the gate's evidence** (docs only).

## 5. Conventions this follows

- **Skills:** `alembic-multi-module-migrations` (the site's one environment), `railway-deploy-playbook` (the start command, pre-deploy migrations, health check), `pytest-throwaway-postgres` (the site's conftest), `verify-real-pass` (the smoke tool's pass is real, not assumed).
- **Patterns:** `harness/` is the template's source; `tools/validate_schemas.py` for the schemas; each generator's `--check`, as in `tools/openapi.py`.
- **Decisions:** 0002 (copied in at build time), 0009 (fixed names), 0015 (CI gates), 0034 (the names `mechframe` and `mf`).

## 6. Non-goals

- No download: the CLI copies from its own checkout, so a site is made where MechFrame is checked out.
- No Railway project, domain or variables made for a site: that is outward-facing, the owner's call each time.
- `add` doesn't run migrations or tests: it prints them for the site's own environment (a SPEC 12 change in decision 0047).
- Not built in K5:
  - `remove --drop-data` (it must run the module's downgrade before its files go: with the first module that has data);
  - `mechframe diff` and `upgrade` (§8 question 1);
  - a module's own Python or npm packages in its manifest (with the first module that needs one);
  - the MCP server (SPEC 17, later).
- The kernel's tests aren't copied into a site: MechFrame's CI tests the kernel, and the lock's hashes prove a site's copy is that kernel.
- A separate worker service, more than one theme in a site, and i18n.

## 7. Acceptance

- **`cli/tests/`:** each command's refusals and exit codes; the lock validates and round-trips; a CRLF checkout of an unedited copy reads as unedited; `check` names an edited, a missing and an added file, a version behind, and fails on a high advisory only; `catalog --check` catches a stale file; `add` refuses a conflict and a missing requirement, and `remove` refuses while another module requires its module; the registries `add` writes import and build.
- **`tests/test_site_template.py`:** the template's web dependencies equal the root's; every file in the table exists; `.env.example` sets `CLIENT_IP_HEADER`; the start command carries `--proxy-headers`.
- **The site's own tests,** run by the smoke tool in the new site:
  - `test_app.py`: the app builds, and `undeclared(app) == []`;
  - `test_migrations.py`: upgrade, downgrade, upgrade, on an empty database;
  - `test_pages.py`: `/`, `/sign-in` and a 404 answer as SPEC 9 says;
  - Vitest on `src/site/`;
  - Playwright `e2e/smoke.spec.ts`: `/` and `/sign-in`, with axe finding nothing serious.
- **The gate (KICKOFF K5):** `python -m tools.site_smoke` in a temporary folder makes `mechframe new test-site` (kernel only), which installs, builds, migrates and passes its tests; then `mechframe check` exits 0. Evidence in `dev plans/<date>-k5-gate-evidence.md`.

## 8. Open questions

None. The owner answered all five on 2026-11-20, each as recommended:

1. **`diff` and `upgrade`: later,** when a module first ships a second version. A three-way diff needs the old copy's files, read from a Git tag per version.
2. **The first owner: a one-time link.** `app.owner` prints a link to set a password, so no password is typed into a terminal. There's no setup token at first boot.
3. **Railway: `FORWARDED_ALLOW_IPS=*` in `railway.toml`,** since its edge has no fixed addresses and a service is reached only through it. The default elsewhere stays `127.0.0.1`.
4. **The site's own pages: in K5.** #92 adds `mountApp({ site })` and `create_app(site=...)`: pages always on, with their server copy, and no switch on Features.
5. **The site's CI: shipped.** The template's `.github/workflows/ci.yml` runs the site's tests and `mechframe check` from a shallow clone of `mechframe/mechframe`.

## Changes after approval

1. **2026-11-20, `advisories.json`'s entries** (#91), which §2 didn't name. Each entry is `{id, module, introduced, fixed, severity, summary}`:
   - `id` matches `^MF-\d{4}-\d{4}$`;
   - `module` is `kernel` or a module's id;
   - `introduced` is the first version affected, and `fixed` the first fixed one, or null while there's no fix;
   - `severity` is `low`, `medium`, `high` or `critical`.

   A copy is affected when `introduced <= version` and, if `fixed` is set, `version < fixed`, by semver precedence. `schema/advisories.schema.json` holds the shape, and `tools.validate_schemas` checks the file against it.
2. **2026-11-20, `check` exits 2 on a copied manifest that doesn't validate** (#91), as it does on an invalid lock: §2's row named the lock only.
3. **2026-11-20, every version pattern in `schema/` is semver's own grammar** (#91, CodeRabbit): the lock's, the advisories' and the module manifest's. A version such as `0.1.0-01` now fails validation instead of reaching the parser. `check` also refuses a recorded file it can't read, and a checkout version semver refuses.
4. **2026-11-20, the install fetches nothing unpinned** (#91, CodeRabbit; SPEC 15): `jsonschema` is declared in `pyproject.toml`; setuptools joins `requirements-dev.in`, hash-pinned and audited; and the install is `python -m pip install --no-deps --no-build-isolation -e .` after the pinned requirements.
5. **2026-11-20, the site's own pages, in exact shape** (#92, decision 0048; §8 question 4):
   - **Server:** `create_app(site=server_copy.SitePages(public=..., member=..., pages=..., name="Pages"))`, from the template's `backend/app/site/pages.py` (`SITE_PAGES`). The patterns are checked as a module's and are always on. At the same rank the site's wins over a module's, and the start logs it; a module's more fixed pattern still wins.
   - **Web:** `defineSite({ routes: { public, member }, slots })` in `web/src/site/site.ts`, given to `mountApp({ modules, site })`. Its routes come first and never wait for a switch, and its slot entries show whatever modules are on. It has no admin pages.
   - **The id:** `site` is the owner of both, so no module may take it (the manifest schema, `RESERVED_IDS`, `defineModule`).
   - **Also:** `kernel.load_module` is exported from `kernel`, and the harness builds its modules with it.
6. **2026-11-20, what the template holds and how a site runs** (#92, decision 0048):
   - **Python:** every command runs with `backend` on the path (`PYTHONPATH=backend`; `/app/backend` in the Dockerfile). `app/__init__.py` adds `backend/modules` and gives `installed(MODULE_IDS)`.
   - **Beyond §2's table:** `backend/app/site/pages.py`, `backend/tests/e2e_server.py` (Playwright's server), `backend/modules/README.md`, `web/src/site/site.ts` with `Home.tsx` and its test, `web/.npmrc`, `web/vitest.setup.ts` and `.dockerignore`.
   - **Requirements:** `new` copies this checkout's `requirements*.in` and `.txt` rather than the template keeping copies. `tools/site_template.py` writes the template's `web/package.json` and its lockfile from the root's.
   - **`.env.example`** holds the live values, `DEBUG=false` among them; the README says which three lines change for local work.
   - **`.railway/railway.ts` in place of `railway.toml`** (§2's row and §8 question 3; the owner, 2026-11-20). Railway's docs: new services can't use config as code, and existing files stop being read on 2026-12-01. The file is a `partial` named `web`: the service built from the Dockerfile, its pre-deploy migrations, health check and variables (`FORWARDED_ALLOW_IPS=*` among them), and a `postgres`. Railway's SDK 3.16.0 is pinned in the site's root `package.json`. The owner applies it with `railway config plan` and `apply`.
   - **Checked live** on a throwaway project (`mechframe-iac-probe`, with the owner's OK): an apply deletes a variable on the service that the file doesn't list. So the file lists every setting in `.env.example` (`preserve()` for those typed into Railway), and `add` (#93) writes a module's settings into both.
7. **2026-11-20, a destructive migration waits for the owner** (#93, decision 0049; the owner: before any module with migrations). §4 gains it as item 3, so `add` and `remove` are #94, `create-owner` #95 and the gate's evidence #96.
   - `kernel.migrate` is both runners' command. An upgrade stops before an unconfirmed revision marked `destructive = True` once its branch is in the database: it exits 2, names it, and prints the command that runs it, `--confirm-destructive <revision>`.
   - A name covers its own revision only. On a database new to its branch (a new site, a module just added) a destructive revision runs unasked.
8. **2026-11-20, `add`, `remove` and `new --recipe`, in exact shape** (#94, decision 0050):
   - **`add`** also writes the module's settings into `.railway/railway.ts` as `preserve()`, in a `// <id>` group (change 6 said it would), and refuses a setting the site sets already and files where the module goes that the lock doesn't record. It runs whole or not at all, and holds the site by `.mechframe-busy` from its first read to its last write (Codex on #94).
   - **`remove`** keeps the module's migrations in `backend/migrations/<id>/` (the database's `alembic_version` names their revision, and Alembic stops on one it can't find) and its `railway.ts` lines (so an apply keeps what the owner typed in), and names the edited and added files that went with its code.
   - **Ranges:** `^`, `~`, exact or partial versions, `>=`, `>`, `<=`, `<`, `*`, and comparators separated by spaces; no `||`. A pre-release meets a range from the lowest pre-release of each lower bound, so the kernel `0.1.0-dev.0` meets `^0.1`.
   - **`new --recipe`** refuses a recipe that doesn't validate, a module not built, a requirement the recipe lacks and two that conflict, before writing anything. Its modules are added in the order their `requires` need; the theme is the recipe's unless `--theme` is given; the recipe's `settings` are printed for Admin, Settings.
   - **Fixtures:** `cli/tests/fixtures/` holds three modules and a recipe. `tests/test_site_template.py` adds two to a new site and runs its tests, and `tools/site_smoke.py` runs a second pass with them: lint, migrations, tests, the web's lint, types, Vitest and build, and `check`.
