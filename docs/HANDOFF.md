# Handoff

Overwritten every session. This one: 2026-11-20, evening Eastern (Claude Code, the owner's machine). #92 had landed at `68149be`. This session built #93, the destructive-migration confirmation, and #94, `add`, `remove` and `new --recipe`.

## State

- **K0 to K4 are done** (K4's gate: #90). K2 steps 9 to 11 wait (decision 0029).
- **K5** (contract `dev plans/contracts/k5-cli-and-site-template.md`, changes 1 to 8; decisions 0047 to 0050): #91 and #92 landed.
  - **#93, landed at `4e9be32`: a destructive migration waits for the owner** (decision 0049, change 7). `kernel.migrate` is the harness's and every site's migrations command.
    - Once its branch is in the database, an upgrade stops before an unconfirmed revision marked `destructive = True`, exits 2, names it and prints the command: `--confirm-destructive <revision>`.
    - A name covers only its own revision. On a database new to its branch (a new site, a module just added) it runs unasked.
    - The Python API refuses too; `confirm_destructive=True` is for throwaway databases only.
  - **#94, holding this handoff: `add`, `remove` and `new --recipe`** (decision 0050, change 8), on the fixture modules in `cli/tests/fixtures/`.
    - `requires` ranges: a pre-release counts, so the kernel `0.1.0-dev.0` meets `^0.1`.
    - Both registries and the lock are written whole. A module's settings go in `.env.example` and `.railway/railway.ts` as `preserve()`.
    - Each run is whole or not at all (a journal; `.mechframe-busy`).
    - `remove` keeps the module's tables, its migrations (`alembic_version` names them) and its `railway.ts` lines.
    - **Checked live, read-only:** `railway config plan` on `mechframe-iac-probe` for a site with two fixture modules: exit 0, and the module settings plan no change while unset. Nothing applied.
    - The smoke (`tools/site_smoke.py`) gains a second pass with the fixture modules added. It hasn't run yet: it's E2E's, or `--keep` locally.
- **v1.0:** 63 % (39 of 61 steps).

## Next

1. **Land #94** if it's still open ("CI result" green and no open thread; CodeRabbit is at its free limit, so Codex is the only bot reviewing). Then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **#95, `create-owner`:** `kernel.auth.owners.create_owner(db, email) -> str` (a one-time set-password link, the owner's answer 2), the template's real `app/owner.py`, and the CLI's wrapper (`python -m app.owner` with the site's `.venv`). Tests first.
3. **#96, K5's gate** (docs only): `python -m tools.site_smoke` run locally, both passes, evidence in `dev plans/<date>-k5-gate-evidence.md`.

## Open questions for the owner

- **A Railway variable to confirm a destructive migration** in the pre-deploy step, so the owner needn't reach the database from their machine (decision 0049, alternatives)? Today it's run by hand with the Postgres's `DATABASE_PUBLIC_URL`.
- **`mechframe-iac-probe`** is kept until K5's gate; the owner deletes it after.
- **Plan a site's Railway file in its CI?** It needs a project token as an Actions secret: yours to make.
- A name for a person (nothing sets `display_name`)? A way for a site to reword the kernel's screens?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?
- cubic and CodeRabbit limits: pay, or drop them? CodeRabbit stopped reviewing at #93's fix (its free limit), and #94 landed without it. Two unused ledger assets (`cd100445…`, `0f244b76…`): delete them?

## Notes

- **A site's Python runs with `backend` on the path:** `$env:PYTHONPATH = "backend"`.
- **The CLI takes a hidden `--root`** (its tests' checkout). `tests/test_site_template.py` and the smoke build one from `schema/` and `cli/tests/fixtures/modules/` so `add` has modules to copy.
- **The Bash tool decodes `\n`, `\r` and `\uXXXX`** in command text, heredocs too. Write a patch script with the Write tool, which keeps them, and run it. Most docs are CRLF in this checkout.
- **Railway's SDK on Windows:** `env "_=$RW" "$RW" config plan`, with `RW="$(cygpath -w "$(npm.cmd root -g | tr -d '\r')/@railway/cli/bin/railway.exe")"`. `railway link -w "color8's Projects" -p mechframe-iac-probe -e production` links a folder; `railway unlink -y` undoes it.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call.
- Never apply a site's `railway.ts` for the owner: the apply, the project and its variables are theirs.
