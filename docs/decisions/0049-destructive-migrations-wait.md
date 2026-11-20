# 0049: A destructive migration waits for the owner: named back, once its branch holds data

- **Date:** 2026-11-20
- **Status:** Decided; applied in K5.3 (#93).
- **Context:** SPEC 10 said a migration that drops or rewrites data is marked `destructive = True`, "and the CLI asks before running it", but nothing read the mark (CodeRabbit on #92). A site's migrations run in Railway's pre-deploy step (`python -m app.migrations upgrade`, decision 0048), where nobody can answer a question. The owner asked for it next, before any module with migrations (2026-11-20). It had to settle:
  - how a command nobody watches asks;
  - what a confirmation covers;
  - which databases need one: on a new site's empty database every revision is pending, a destructive one among them.
- **Decision:**
  1. **`kernel.migrate` holds it,** so the harness's `python -m harness.migrations` and every site's `python -m app.migrations` are one command (`command_line`): `upgrade [target] [--confirm-destructive REVISION]`, `downgrade [target]`, `heads`, `history` and `current`.
  2. **An upgrade stops before any step runs** when it would run a destructive revision nobody named. The check sits in the upgrade's own run, after it reads the database's heads and before its first step, so what it checked is what runs. The command exits 2 and prints each revision with its file and the first line of its docstring, then the exact command that runs them. The database is as it was. A pre-deploy step fails there, so the new deploy never goes live and the old one keeps serving.
  3. **The owner names each one:** `--confirm-destructive <revision>`, repeated or separated by commas. A name covers only its own revision, so one left in a deploy command can't let a later one through. A name that matches none is shown, and confirms nothing.
  4. **Only data already there is asked about.** A destructive revision needs naming when a revision below it on its branch has already run. On a database new to its branch (a new site, or a module just added by `mechframe add`) it runs unasked: the tables it could touch are made in the same upgrade. A module's migrations touch only its own tables (SPEC 10), so its branch is the data at risk.
  5. **Any true value marks it,** so a mark other than `False` errs toward asking. A revision with no mark isn't destructive; `script.py.mako` writes `destructive = False` into every new one.
  6. **The Python API refuses too:** `upgrade(url, target, confirm_destructive=...)` in both runners. `True` confirms every one, for a database thrown away after: the repo's stairway test steps each revision down and back up.
- **Alternatives:**
  - *A bare `--confirm-destructive` flag:* added once to a refused deploy command, it would let every later destructive migration through. That's the fix an agent facing a red deploy is likeliest to make.
  - *Asking about every pending destructive revision:* every new site's first deploy, and every `add` of a module that has one, would stop for a revision with no data to lose, and owners would learn to confirm without reading.
  - *A question in the terminal:* the pre-deploy step has none.
  - *Running the safe revisions and stopping at the destructive one:* half an upgrade, under code that expects all of it or none. Stopping before all of them leaves the database as the running deploy expects.
  - *A Railway variable that names the revisions for the pre-deploy step:* the owner could confirm without reaching the database from their machine. Left to the owner (`docs/HANDOFF.md`).
- **Consequences:**
  - On Railway, the owner runs a refused revision from the site's checkout at the new commit, with `DATABASE_URL` set to one that reaches the database from their machine (the Postgres service's `DATABASE_PUBLIC_URL`, behind its TCP proxy), then redeploys (the site's README, "Deploying").
  - A site's agents never add the flag to the deploy command, nor unmark a migration (the template's `CLAUDE.md` and `AGENTS.md`).
  - `downgrade` asks nothing: it's run by hand, never by a deploy.
  - **A site made before #93 has no guard:** its `backend/app/migrations.py` calls Alembic itself, and the file is the site's own, so no `mechframe` command replaces it. Copy the template's over it before a destructive revision reaches its database (CodeRabbit on #93). Only test sites predate #93.
  - The check takes its steps from Alembic's `ScriptDirectory._upgrade_revs`, as `command.upgrade` does. Alembic is pinned, and the tests run through it.
- **See:** SPEC 10; decision 0048; the K5 contract's change 7; `kernel/backend/kernel/migrate.py`; `kernel/tests/test_migrate.py`; the template's `backend/tests/test_migrations.py`
