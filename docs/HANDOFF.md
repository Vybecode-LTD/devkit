# Handoff

Overwritten every session. This one: 2026-11-20, afternoon Eastern (Claude Code, the owner's machine). #91 had landed at `e60b23c`, and the ledger already showed it. This session built #92, K5's site template.

## State

- **K0 to K4 are done** (K4's gate: #90). K2 steps 9 to 11 wait (decision 0029).
- **K5** (contract `dev plans/contracts/k5-cli-and-site-template.md`, changes 1 to 6; decisions 0047 and 0048):
  - **#91, landed:** the CLI's core, `check`, `catalog` and the lock.
  - **#92, this PR:**
    - `templates/site/`, the harness made into a site (`templates/README.md`);
    - `kernel.load_module`, with the harness on it;
    - the site's own pages: `create_app(site=server_copy.SitePages(...))` and `defineSite` for `mountApp({ site })`. They're always on and win a tie with a module's; `site` is reserved as a module id;
    - `mechframe new <dir> [--name] [--theme]`, kernel only;
    - `tools/site_template.py`, which holds the template's web package to the root's;
    - `tools/site_smoke.py`, run by the new `site-smoke` job in `e2e.yml`;
    - `tests/test_site_template.py`, which makes a site and runs its own tests and lint on every PR;
    - CI's Python filter gains `templates/` and the root's package files.
  - **Railway, the owner's choice:** `.railway/railway.ts`, Railway's infrastructure as code, in place of `railway.toml`. Railway's docs: new services can't use `railway.toml`, and existing files stop being read on 2026-12-01.
    - **Checked live**, with the owner's OK, on a throwaway project, `mechframe-iac-probe` in "color8's Projects". The plan and the apply made the `web` service (Dockerfile, pre-deploy migrations, health check, 5 restarts) and a `postgres`. An unset `preserve()` makes nothing, and a set one is kept. **A variable the file doesn't list is deleted by the next apply**, so the file lists every `.env.example` setting but `WEB_DIST`.
    - **Left on the probe:** a non-secret `SITE_URL=https://probe.invalid` and `PROBE_UNLISTED` were set and never applied away. No secrets, no code deployed. Deleting the project is the owner's (below).
- **Local evidence before the push:**
  - Python: all of it, with coverage;
  - Vitest with coverage, and Playwright on the harness;
  - `python -m tools.site_smoke`: every step passed, a new site made and run from nothing.

  The numbers are in #92's body.
- **v1.0:** 63 % (38 of 60 steps).

## Next

1. **Land #92** once "CI result" is green and the bots are clear. Then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **#93, `add` and `remove`,** on fixture modules (`cli/tests/fixtures/`). They write `backend/app/modules.py`, `web/src/modules.ts`, `.env.example` **and `.railway/railway.ts`** (a module's settings as `preserve()`, or the next apply deletes them), and the lock. Plus `new --recipe`.
3. **#94, `create-owner`:** `kernel.auth.owners.create_owner`, the template's real `app/owner.py`, and the CLI's wrapper.
4. **#95, K5's gate** (docs only): `python -m tools.site_smoke` evidence in `dev plans/<date>-k5-gate-evidence.md`.

## Open questions for the owner

- **Delete `mechframe-iac-probe`:** Railway, the project, Settings, Danger, Delete. Or keep it for #93's check of `add` writing `railway.ts`.
- **Plan a site's Railway file in its CI?** It would need a project token as an Actions secret: yours to make.
- A name for a person (nothing sets `display_name`)? A way for a site to reword the kernel's screens?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?
- cubic and CodeRabbit limits: pay, or drop them? Two unused ledger assets (`cd100445…`, `0f244b76…`): delete them?

## Notes

- **A site's Python runs with `backend` on the path:** `$env:PYTHONPATH = "backend"`.
- **On Windows the Railway SDK finds the CLI only through `$_`.** From Git Bash, run `env "_=$RW" "$RW" config plan`, with `RW="$(cygpath -w "$(npm.cmd root -g | tr -d '\r')/@railway/cli/bin/railway.exe")"`.
- **Railway's SDK pins `restartPolicyType` badly:** written as ON_FAILURE (its default), every plan shows it changing. Leave it out.
- **The Bash tool decodes `\n`, `\r` and `\uXXXX`** in command text, heredocs too. Build them with `chr()`. `SPEC.md`, `CLAUDE.md`, `AGENTS.md`, the K5 contract and `cli/README.md` are CRLF: edit them with a script that keeps the newline.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call. #92 only added path filters and the `site-smoke` job the contract names.
- Never apply a site's `railway.ts` for the owner: the apply, the project and its variables are theirs.
