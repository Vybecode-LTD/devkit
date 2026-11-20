# Next session: K5's destructive-migration confirmation (#93), then add and remove (#94)

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-k5-destructive-migrations.md and follow it, starting with section 4."

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

1. **#93, SPEC 10's confirmation before a destructive migration** (the owner, 2026-11-20: build it next, before any module with migrations). Nothing reads `destructive = True` yet. Tests first: `app.migrations upgrade` (the template's) and `harness.migrations upgrade` refuse a pending revision marked True without `--confirm-destructive`, naming it, so Railway's pre-deploy stops until the owner runs it by hand. Record it as the contract's change 7 (its §4 numbers move on by one) and a decision.
2. **#94, `add` and `remove`** (contract §2 and §4 item 3), tests first, on fixture modules in `cli/tests/fixtures/`:
   - `add <id>` writes the registries, `.env.example` **and `.railway/railway.ts`** (a module's settings as `preserve()`, or an apply deletes them) and the lock; `remove` undoes it but its tables; `new --recipe`.
   - **Tests:** the registries build, `railway.ts` lists every setting (`tests/test_site_template.py`'s check), and `check` is clean after each.
3. Then #95 (`create-owner`) and #96 (K5's gate: `python -m tools.site_smoke`, evidence file).

## 5. Ask the owner

- `mechframe-iac-probe` (Railway, "color8's Projects") is kept for #94: only `railway config plan` against it, read-only. The owner deletes it after K5's gate.
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
