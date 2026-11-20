# Templates

`site/` is the empty site `mechframe new <dir>` starts every project from (K5 contract, `dev plans/contracts/k5-cli-and-site-template.md`; SPEC.md section 4). It is the harness made into a site: `backend/app/` builds the app from the kernel, the modules `app/modules.py` lists (each with `kernel.load_module`) and the site's own pages (`app/site/pages.py`, `web/src/site/`); `backend/alembic/` runs every branch; `web/` holds the kernel's web dependencies at MechFrame's exact versions; and the `Dockerfile`, `.railway/railway.ts` (Railway as code, with its SDK pinned in `package.json`), `.env.example`, CI workflow, `CLAUDE.md` and `AGENTS.md` are the site's.

`mechframe new` copies it without its build output, writes the site's name (`__SITE_NAME__`) and theme (`__THEME__`) in, adds this checkout's pinned requirements, the theme's `tokens.css` and the kernel, and writes `mechframe.lock.json`. `tests/test_site_template.py` makes a site from it and runs that site's own Python tests and lint; `python -m tools.site_smoke` goes on to a venv of its own, `npm ci`, the build, Vitest, Playwright and `mechframe check` (CI's E2E workflow, on main and weekly).

Keep `site/web/package.json` and `package-lock.json` at the root's versions: after a bump at the root, run `python -m tools.site_template` to write them again (`--check` only reports).
