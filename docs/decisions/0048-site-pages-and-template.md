# 0048: The site's own pages, `kernel.load_module`, and how a site runs: always on, `backend` on the path, Railway as code

- **Date:** 2026-11-20
- **Status:** Decided; applied in K5.2 (#92). Point 5 replaces the contract's `railway.toml`: the owner's choice, 2026-11-20, checked live on a throwaway project.
- **Context:** K5.2 builds `templates/site/` and `mechframe new` (contract `dev plans/contracts/k5-cli-and-site-template.md`). The owner chose a site's own pages in K5 (§8 question 4): `mountApp({ site })` and `create_app(site=...)`, always on, with server copy, and no switch on Features. The contract asked for their exact shape as change 5. Building the template also had to settle:
  - how a site's `python -m app.…` finds `backend/`;
  - what the template holds beyond the contract's table;
  - what Railway reads. Its docs say config as code (`railway.toml`) is deprecated: new services can't opt in, and existing files stop being read on 2026-12-01. Its replacement, `.railway/railway.ts`, isn't read at deploy: it's applied with `railway config apply`.
- **Decision:**
  1. **The site's own pages, on the server,** are `create_app(site=server_copy.SitePages(public=..., member=..., pages=..., name="Pages"))`, from the site's `backend/app/site/pages.py` (`SITE_PAGES`):
     - their patterns are checked as a module's (`routes.public` with `pages`, nothing under `/api` or `/admin`, no kernel page taken);
     - they're always on, whatever MODULES and the switches say, and their entries are in `sitemap.xml` and `llms.txt` (under `name`);
     - at the same rank, a site's pattern takes an address from a module's, and the start logs `The site's / takes the place of <module>'s /.`; a module's more fixed pattern still wins;
     - their owner is `server_copy.SITE`, `site`, which no module may take (the manifest schema, `RESERVED_IDS`, the web's `defineModule`).
  2. **On the web,** `defineSite({ routes: { public, member }, slots })` in `web/src/site/site.ts`, given to `mountApp({ modules, site })`:
     - the router holds the site's routes first, so they win a tie, and never waits for the modules' switches to show them;
     - the site's slot entries show whatever modules are on;
     - the site has no admin pages: those are a module's;
     - in the tests, `renderApp({ sitePages })` takes it (`site` there is the identity).
  3. **`kernel.load_module(manifest)`** builds an `InstalledModule` from a `module.json` and its package's fixed names (decision 0009). The caller puts the package on `sys.path`. The harness's `discover` and a site's `app.installed(MODULE_IDS)` both use it.
  4. **A site's Python runs with `backend` on the path:**
     - `PYTHONPATH=backend` in a terminal (README.md);
     - `/app/backend` in the Dockerfile;
     - `pythonpath` in `pyproject.toml` for the tests.

     `app/__init__.py` adds `backend/modules`, so a module's package imports by its name. There's no `.pth` file or editable install to forget.
  5. **Railway as code: `.railway/railway.ts`** (the owner, 2026-11-20, over the recommended README steps). It's a `partial` named `web` for Railway's infrastructure as code (the `railway` SDK 3.16.0, pinned in the site's root `package.json`). It declares:
     - the `web` service, built from the Dockerfile;
     - `python -m app.migrations upgrade` before each deploy, and the health check `/api/kernel/health`;
     - five restarts (Railway's default policy, ON_FAILURE, is left unwritten: written, every plan shows it changing);
     - a `postgres`, whose `DATABASE_URL` the service references;
     - every setting in `.env.example` but `WEB_DIST`, the Dockerfile's: fixed ones written (`FORWARDED_ALLOW_IPS=*`, `CLIENT_IP_HEADER=X-Real-IP`), the rest `preserve()`.

     Railway doesn't read it on deploy: the site's owner runs `npm ci`, `railway config plan` and `railway config apply` from the linked folder, then connects the service to the repo and types the secrets in. The Dockerfile's `CMD` stays the start command on any host. **Checked live** on a throwaway project, `mechframe-iac-probe`:
     - the plan made the service and the database as written, and a second plan was clean;
     - an unset `preserve()` makes no variable, and a set one is kept;
     - a variable the file doesn't list is deleted by the next apply, marked destructive.
  6. **The template holds:**
     - beyond the table: `app/site/pages.py`; `web/src/site/site.ts` with a home page and its test; `backend/tests/e2e_server.py` for Playwright; `backend/modules/README.md`; `web/.npmrc`; `web/vitest.setup.ts`; `.dockerignore`;
     - not the requirements: `new` copies this checkout's `requirements*.in` and `.txt`, so they can't drift.

     `tools/site_template.py` writes the template's `web/package.json` from the root's and its lockfile with npm, seeded from the root's (`--check` in the tests).
  7. **`.env.example` lists every setting with its live value or a blank:** `DEBUG=false`, `CLIENT_IP_HEADER=X-Real-IP`, `FORWARDED_ALLOW_IPS=127.0.0.1`. It is the checklist of Railway's variables; the README says which three lines change for local work.
- **Alternatives:**
  - *The site's pages as a module called `site`:* it would get a switch on Features, a manifest and a branch it doesn't need.
  - *Refusing a tie between the site and a module:* adding a module that also owns `/` would stop the site starting until its home page went.
  - *An editable install of the site, or a `.pth` file:* one more step to forget, and the image still needs a path.
  - *`railway.toml` as the contract had it:* not read for a new service, and not at all after 2026-12-01.
  - *Railway's settings typed by hand from the README, and no file* (recommended): nothing to install, but nothing a plan can check either.
  - *A whole-project `railway.ts`, not a partial:* an apply would delete a worker or bucket added later outside the file.
- **Consequences:**
  - A site's home page is its own from the start: `server_copy.home` reused, and `Home.tsx` drawing the same words.
  - Adding a module that owns `/` leaves the site's home page in place until the site's `/` comes out of both lists.
  - A setting a site adds goes in `.railway/railway.ts` as well as `.env.example`, or the next apply deletes it from Railway. `mechframe add` (#93) writes a module's settings into both.
  - On Windows the SDK finds the CLI only through `$_`: from Git Bash, `env "_=$RW" "$RW" config plan` with the CLI's own `railway.exe` (the site's README).
  - The site's CI type-checks the file against the SDK, but can't plan without a Railway token, which stays the owner's.
  - The throwaway project `mechframe-iac-probe` is the owner's to delete.
- **See:** SPEC 4, 6, 8 and 9; decisions 0009, 0041 and 0047; the K5 contract's changes 5 and 6; `templates/site/`; `kernel/backend/kernel/server_copy.py`; `kernel/web/src/modules.ts`
