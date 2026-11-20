# __SITE_NAME__

A website made with [MechFrame](https://github.com/mechframe/mechframe): its kernel (accounts, sign-in, the admin, settings, mail, jobs and the public pages' server copy), the modules this site has, and its own pages. `mechframe.lock.json` records what was copied in, and from which version.

## Where things are

| Path | What |
| --- | --- |
| `backend/app/` | This site's backend: `main.py` builds the app, `modules.py` lists its modules, `site/pages.py` its own pages' server copy |
| `web/src/site/` | This site's own pages (`site.ts` lists them) |
| `backend/kernel/`, `backend/modules/`, `backend/migrations/`, `web/src/kernel/`, `web/src/modules/` | Copied from MechFrame: change them only when settings, slots and events can't do it |
| `web/src/theme/tokens.css` | The theme's design tokens |
| `backend/tests/`, `web/src/site/*.test.tsx`, `web/e2e/` | The site's tests |

## Working on it

In PowerShell, from this folder. Every Python command runs with `backend` on the path: set it once per terminal.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
$env:PYTHONPATH = "backend"
docker compose up -d db
```

Copy `.env.example` to `.env`, set `DEBUG=true`, `SITE_URL=http://localhost:8000`, a blank `CLIENT_IP_HEADER=`, and fill in `SECRET_KEY` and `ENCRYPTION_KEYS` (the file says how). Then:

| What | Command |
| --- | --- |
| Migrate the database | `.venv\Scripts\python.exe -m app.migrations upgrade` |
| Run the backend | `.venv\Scripts\python.exe -m uvicorn app.main:app --reload` |
| Install and run the web app (another terminal) | `cd web; npm ci; npm run dev` (http://localhost:5173) |
| Build the web app the backend serves | `cd web; npm run build` |
| The first owner | `.venv\Scripts\python.exe -m app.owner <email>` (arrives with MechFrame's #94) |
| Python tests, lint, types | `.venv\Scripts\python.exe -m pytest`, `-m ruff check .`, `-m black --check .`, `-m mypy` |
| Web tests, lint, types | `cd web; npm test; npm run lint; npm run typecheck` |
| End-to-end tests | `cd web; npx playwright install chromium` once, then `npm run build; npm run e2e`, with `TEST_DATABASE_URL` set |
| What this site edited, and what is behind | from MechFrame's checkout: `python -m mechframe check --site <this folder>` |

The tests use their own databases on `TEST_DATABASE_URL`'s server (`postgresql://site:site@localhost:5432/postgres` by default, compose.yaml's).

## Deploying

The `Dockerfile` builds the web app and runs the backend on the `PORT` the host gives, reading the proxy's headers. On Railway, `.railway/railway.ts` describes the site as code: the `web` service built from the Dockerfile, with `python -m app.migrations upgrade` before each deploy (a migration that fails stops it), the health check `/api/kernel/health`, `CLIENT_IP_HEADER=X-Real-IP`, `FORWARDED_ALLOW_IPS=*` and `DATABASE_URL` from a `postgres` beside it. Railway doesn't read the file on deploy: it's applied with Railway's CLI (5.42.1 or newer), by the site's owner, from this folder:

```powershell
npm ci
railway init --name <project>
railway config plan
railway config apply
```

`railway init` makes the project and links this folder to it (`railway link` for one that exists). On Windows, from Git Bash, the SDK can't find the CLI through npm's shim: run each `railway config` command as `env "_=$RW" "$RW" config plan`, with `RW="$(cygpath -w "$(npm root -g)/@railway/cli/bin/railway.exe")"`.

Then, in Railway's dashboard, connect the `web` service to this repo (Settings, Source) and type its secrets into Variables: `SITE_URL`, `SECRET_KEY`, `ENCRYPTION_KEYS`, and mail and storage if the site uses them. Every key is typed by the site's owner into the host, never committed.

**A variable on the `web` service that `railway.ts` doesn't list is deleted by the next apply,** which the plan marks as destructive. Add a new setting to the file first, as `preserve()` when its value is typed into Railway.

**A migration marked `destructive = True` stops the deploy** once its module is in the database: the pre-deploy step exits 2, names it and leaves the database as it was, and the live deploy keeps serving. Back the database up and read the migration. Then, from this folder at the new commit, with `DATABASE_URL` set to one that reaches the database from your machine (the `postgres` service's `DATABASE_PUBLIC_URL`, behind its TCP proxy), run the command it printed with this site's own Python: `$env:PYTHONPATH = "backend"`, then `.venv\Scripts\python.exe -m app.migrations upgrade --confirm-destructive <revision>`. Then redeploy. Never add the flag to the deploy command: it names each revision, so a later one would stop the deploy again.
