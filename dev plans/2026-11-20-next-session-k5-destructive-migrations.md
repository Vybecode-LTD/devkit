# Next session: K5's add and remove (#93)

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-k5-add-remove.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public: mechframe/mechframe. Nothing is deployed but a throwaway Railway project (section 5).

## 2. Rules not in a CLAUDE.md

- **K5's contract** is `dev plans/contracts/k5-cli-and-site-template.md`, decisions 0047 and 0048. Its next change is 7.
- **Landing:** push once local suites are green, batch fixes, wait for CodeRabbit before a fix; fast-forward once "CI result" is green and no thread is open. Stage by name; gitleaks the staged diff.
- **Outward-facing is the owner's call:** no Railway project, apply or variable for a site, and no change to CI's security gates.
- **`AGENTS.md` holds `CLAUDE.md`'s text,** and the template's two files hold the same rules as each other: change both of each pair together.

## 3. State (2026-11-20, afternoon Eastern; check, don't trust)

- **main** should hold #92, the site template. Check with `git log -1 origin/main` and `gh pr view 92`. If #92 is still open, land it first, then republish the ledger (`dev plans/progress-ledger/README.md`).
- **#92 gave** `templates/site/`, `mechframe new` (kernel only), `kernel.load_module`, the site's own pages (`server_copy.SitePages`, `defineSite`), `.railway/railway.ts`, `tools/site_template.py` and `tools/site_smoke.py`.
- **The rest:** `docs/HANDOFF.md`.

## 4. The job

1. **#93, `add` and `remove`** (contract §2 and §4 item 3), tests first, on fixture modules in `cli/tests/fixtures/`:
   - `add <id>`: requires and conflicts against the lock; copy (`mechframe.layout`); the registries `backend/app/modules.py` and `web/src/modules.ts`; the module's env vars appended to `.env.example` **and written into `.railway/railway.ts`** at its "added by mechframe add" line, as `preserve()`; version and hashes into the lock; then print the migration and test commands.
   - `remove <id>`: refuse while another module requires it; take out its files, registry entries and lock entry; comment out its env vars in both files; keep its tables.
   - `new --recipe <id>`: `new`, then `add` for each of the recipe's modules; refuse a recipe naming a module not built yet.
   - **Tests:** the registries import and build; `railway.ts` lists every `.env.example` key (reuse `tests/test_site_template.py`'s check); `check` is clean after `add` and after `remove`.
2. Then #94 (`create-owner`) and #95 (K5's gate: `python -m tools.site_smoke`, evidence file).

## 5. Ask the owner

- Delete `mechframe-iac-probe` (Railway, "color8's Projects")? Or keep it to check `add`'s `railway.ts` with a plan: only `railway config plan`, read-only.
- Where SPEC 10's destructive-migration confirmation goes (nothing reads `destructive = True` yet; `docs/HANDOFF.md`).
- The rest: `docs/HANDOFF.md`, "Open questions". Ask, don't decide.

## 6. Environment and traps

- **Python tests,** in Git Bash, in the background, into a log, about 11 minutes; change no file while they run:

  ```bash
  TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov
  ```

- **A made site's Python** runs with `PYTHONPATH=backend`. The smoke takes about 5 minutes, pip cached:

  ```bash
  TEST_DATABASE_URL=... PYTHONPATH=cli .venv/Scripts/python.exe -m tools.site_smoke --keep
  ```

- **Railway's SDK on Windows:** `env "_=$RW" "$RW" config plan`, with `RW="$(cygpath -w "$(npm.cmd root -g | tr -d '\r')/@railway/cli/bin/railway.exe")"`.
- **The Bash tool decodes `\n`, `\r` and `\u`** in command text: build them with `chr()`. `SPEC.md`, `CLAUDE.md`, `AGENTS.md`, the K5 contract and `cli/README.md` are CRLF.
- **Vitest by name:** `node node_modules/vitest/vitest.mjs run <file> -t "<name>"`.

## 7. Evidence and next IDs

`docs/HANDOFF.md`, decision 0048, the contract's changes 5 and 6, and #92's body.

Next free: decision 0049, PR #93, migration `kernel_0013`, contract change 7.

## 8. Candidates for `knowledge/`

1. `railway.toml` is dead for new services, and unread after 2026-12-01. `railway.ts` is applied by `railway config apply`, never on deploy (`railway-deploy-playbook`).
2. A `railway.ts` partial deletes a declared service's unlisted variables. `preserve()` keeps a set one and makes nothing while unset. A written default (`restartPolicyType`) shows as a change on every plan.
3. TanStack Query 5: cancel a query on its first load before invalidating it.
