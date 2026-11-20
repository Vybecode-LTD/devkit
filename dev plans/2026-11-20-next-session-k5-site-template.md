# Next session: K5's site template (#92)

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-k5-site-template.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public, mechframe/mechframe. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **K5's contract is approved** (`dev plans/contracts/k5-cli-and-site-template.md`; decision 0047). Its §8 holds the owner's five answers. The next change after approval is 4.
- **Landing:** push once the local suites are green, and batch the fixes. Wait for CodeRabbit before pushing a fix while CI runs. Land by fast-forward once "CI result" is green and no thread is open. Stage by name and run gitleaks on the staged diff.
- **Outward-facing is the owner's call:** no Railway project, domain or variables for a site, and no change to CI's security gates.
- **`AGENTS.md` holds `CLAUDE.md`'s text:** change both together.

## 3. State (2026-11-20, morning Eastern; check, don't trust)

- **main** should be #91's head (the CLI's core and this handoff). Check with `git log -1 origin/main` and `gh pr view 91`. If #91 is still open, land it first, then republish the ledger (`dev plans/progress-ledger/README.md`).
- **#91 gave** `cli/mechframe/` (`layout`, `lock`, `hashes`, `versions`, `catalog`, `check`), `cli/tests/`, `schema/advisories.schema.json`, and SPEC 4, 12, 13 and 17. The whole Python suite: 2,177 passed at 98.19 %.
- **The rest:** `docs/HANDOFF.md`.

## 4. The job

1. **#92, the site template** (contract §2 and §4 item 2), on a new branch, tests first:
   - **`templates/site/`**, every row of the contract's table, made from `harness/`:
     - `backend/app/` (`owner.py` a stub until #94);
     - `alembic/` and `backend/tests/`;
     - `web/` with its `package-lock.json`;
     - `Dockerfile`, `railway.toml` (`FORWARDED_ALLOW_IPS=*`), `.env.example` (`CLIENT_IP_HEADER=X-Real-IP`);
     - `.github/workflows/ci.yml`, `CLAUDE.md` and `AGENTS.md`.
   - **`kernel.modules.load_module(manifest)`**, lifted from `harness/registry.py`, with the harness moved onto it.
   - **The site's own pages:** `mountApp({ site })` and `create_app(site=...)`, always on, with server copy, no switch on Features. Record their exact shape as contract change 4.
   - **`mechframe new <dir>`** (kernel only), on `layout.copy` and `lock.write`.
   - **`tests/test_site_template.py`** and **`tools/site_smoke.py`.** The smoke tool builds a new site in a temporary folder: venv, `pip install --require-hashes`, `npm ci`, build, migrations, the site's tests and `mechframe check`. The E2E workflow runs it, never on a PR.
2. Then #93 (`add`, `remove`), #94 (`create-owner`), #95 (K5's gate).

## 5. Ask the owner

The list in `docs/HANDOFF.md`, "Open questions": ask, don't decide.

## 6. Environment and traps

- **Python tests,** in Git Bash, in the background, into a log: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov` (about 11 minutes). Change no file while it runs.
- **The CLI:** `PYTHONPATH=cli .venv/Scripts/python.exe -m mechframe check --site <dir>`. Try an editable install in a throwaway venv, never `.venv`.
- **The Bash tool decodes `\n`, `\r` and `\u` in command text:** build them with `chr()`. `SPEC.md`, `CLAUDE.md`, `AGENTS.md` and `pyproject.toml` are CRLF: edit them with a script that keeps the newline.
- **Vitest by name:** `node node_modules/vitest/vitest.mjs run <file> -t "<name>"`. Playwright: pick a test by `file:line`.

## 7. Evidence and next IDs

`docs/HANDOFF.md`, the K5 contract (changes 1 to 3), decision 0047, #91's body. Next free: decision 0048, PR #92, migration `kernel_0013`, contract change 4.

## 8. Candidates for `knowledge/`

1. TanStack Query 5 doesn't refetch a query on its first load when it's invalidated: cancel it first.
2. A tool may decode escapes in a command's text: build them with `chr()`.
3. Test an editable install in a bare venv, or a missing dependency hides.
4. A schema's semver pattern passes `0.1.0-01`, which a strict parser refuses: catch it at the boundary.
