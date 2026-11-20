# Handoff

Overwritten every session. This one: 2026-11-20, evening Eastern (Claude Code, the owner's machine). #92 had landed at `68149be`. This session built #93, the destructive-migration confirmation; #94, `add`, `remove` and `new --recipe`; and #95, `create-owner`.

## State

- **K0 to K4 are done** (K4's gate: #90). K2 steps 9 to 11 wait (decision 0029).
- **K5** (contract `dev plans/contracts/k5-cli-and-site-template.md`, changes 1 to 9; decisions 0047 to 0051): #91 and #92 landed.
  - **#93, landed at `4e9be32`: a destructive migration waits for the owner** (decision 0049, change 7). `kernel.migrate` is the harness's and every site's migrations command.
    - Once its branch is in the database, an upgrade stops before an unconfirmed revision marked `destructive = True`, exits 2, names it and prints the command: `--confirm-destructive <revision>`.
    - A name covers only its own revision. On a database new to its branch (a new site, a module just added) it runs unasked.
    - The Python API refuses too; `confirm_destructive=True` is for throwaway databases only.
  - **#94, landed at `40f494b`: `add`, `remove` and `new --recipe`** (decision 0050, change 8), on the fixture modules in `cli/tests/fixtures/`.
    - `requires` ranges: a pre-release counts, so the kernel `0.1.0-dev.0` meets `^0.1`.
    - Both registries and the lock are written whole. A module's settings go in `.env.example` and `.railway/railway.ts` as `preserve()`.
    - Each run is whole or not at all (a journal), and holds the site by `.mechframe-busy` from its first read to its last write (Codex on #94).
    - `remove` keeps the module's tables, its migrations (`alembic_version` names them) and its `railway.ts` lines.
    - **Checked live, read-only:** `railway config plan` on `mechframe-iac-probe` for a site with two fixture modules: exit 0, and the module settings plan no change while unset. Nothing applied.
    - The smoke (`tools/site_smoke.py`) gains a second pass with the fixture modules added: green in main's E2E at `40f494b`.
  - **#95, holding this handoff: `create-owner`** (decision 0051, change 9).
    - `kernel.auth.owners.create_owner(db, email)` answers a reset link's token (30 minutes, single use). Nothing is mailed: the command prints the link.
    - With no active owner, the address's account (made if there's none) gets `owner`. With one, only an owner's own address gets a fresh link (the owner, 2026-11-20); any other is refused.
    - Before the link, the account's password is cleared, its sessions end and its ways in are voided. `owner`'s role row is locked first. Audited as `auth.user.owner_link_issued`.
    - The template's `app/owner.py` runs it with the app's settings (the hash is keyed with SECRET_KEY). `mechframe create-owner` runs that with the site's `.venv`.
    - SPEC 14.1's setup token at first boot is gone.
- **v1.0:** 65 % (40 of 61 steps). Every K5 step is done but its gate.

## Next

1. **Land #95** if it's still open ("CI result" green and no open thread). Then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **#96, K5's gate** (docs only): `python -m tools.site_smoke --keep` locally, both passes, and the contract's §7 bullet by bullet, in `dev plans/<date>-k5-gate-evidence.md`.
3. **The kernel's close** (KICKOFF, "The kernel is done when"), then the modules' wave-1 kickoff it names.

## Open questions for the owner

- **A Railway variable to confirm a destructive migration** in the pre-deploy step, so the owner needn't reach the database from their machine (decision 0049, alternatives)? Today it's run by hand with the Postgres's `DATABASE_PUBLIC_URL`.
- **`mechframe-iac-probe`** is kept until K5's gate; the owner deletes it after.
- **A third unused ledger asset,** `7889d809…` (#92's rows), since the ledger moved to #94's: delete it with the other two?
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
