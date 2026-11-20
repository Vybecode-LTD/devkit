# CLAUDE.md: __SITE_NAME__

A website made with MechFrame: its kernel, the modules this site has and its own pages. `CLAUDE.md` and `AGENTS.md` hold the same rules, for Claude Code and for other agents: change both together. `README.md` has the commands.

## Rules

- **This site's code goes in its `site/` folders:** `backend/app/site/` and `web/src/site/`. Its pages are listed in `web/src/site/site.ts`, each public one with its server copy in `backend/app/site/pages.py`, the same words read from the same rows, so a crawler that runs no script reads what a person sees.
- **Copied folders are MechFrame's:** `backend/kernel/`, `backend/modules/`, `backend/migrations/`, `web/src/kernel/` and `web/src/modules/`. Change one only when its settings, slots and events can't do what the site needs, and say why in the commit. `mechframe check` reports every edit against `mechframe.lock.json`.
- **Modules come and go with `mechframe add` and `mechframe remove`,** never by copying files by hand: they write `backend/app/modules.py`, `web/src/modules.ts`, `.env.example` and the lock together.
- **Run `mechframe check` before each pull request** (from MechFrame's checkout: `python -m mechframe check --site <this folder>`). CI runs it too, and fails on an open high or critical advisory: patch it before anything else.
- **Styling comes only from the theme's tokens** (`var(--mf-*)`, `web/src/theme/tokens.css`); ESLint refuses a colour written in code. Use the kernel's UI kit (`@/kernel`) before writing a component.
- **Data comes only through the kernel's typed client and TanStack Query** (`useApiQuery`, `useApiMutation`): no `fetch` in a component.
- **Tests come with the change:** a bug fix gets a test seen failing first. Python tests in `backend/tests/`, the site's page tests beside them in `web/src/site/`.
- **No secrets, ever:** not in the repo, not in logs. Keys go in the host's variables, typed by the site's owner. Never commit `.env`.
- **A new setting goes in three places:** `.env.example`, the code that reads it, and `.railway/railway.ts` (`preserve()` for a secret), since an apply deletes a variable on the web service that the file doesn't list. Applying it (`railway config apply`) is the owner's.
- **A refused destructive migration is the owner's:** when `python -m app.migrations upgrade` stops on one marked `destructive = True`, never add `--confirm-destructive` to the deploy command or unmark the migration. Tell the owner: they back the database up and run it by hand (`README.md`, "Deploying").
- **Ask the owner first** before anything outward-facing: the host's projects, domains and variables, any account, any message sent for them.

## Commands

Python runs with `backend` on the path: `$env:PYTHONPATH = "backend"` once per terminal (PowerShell), then `.venv\Scripts\python.exe -m pytest`, `-m ruff check .`, `-m black --check .`, `-m mypy`, `-m app.migrations upgrade`. The web app: `cd web`, then `npm ci`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run e2e`.
