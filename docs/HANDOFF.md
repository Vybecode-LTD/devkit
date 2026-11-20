# Handoff

Overwritten every session. This one: 2026-11-20, morning Eastern (Claude Code, the owner's machine). #88 had landed at `ca00054`. K4's gate passed (#89, #90), the owner approved K5's contract, and #91, the CLI's core, holds this handoff.

## State

- **K0 to K4 are done.** K2 steps 9 to 11 wait (decision 0029). **K4's gate passed** on `main` at `03675ac` (`dev plans/2026-11-20-k4-gate-evidence.md`, #90):
  - Python 2,126 passed at 98.73 %; Vitest 491 at 96.67 % of lines; Playwright 73 of 73, twice.
  - Every §7 bullet is matched to its tests, and the kernel's contract lint is clean.
- **#89** fixed what the gate's first run found. A role save that landed while People's search loaded its first page kept the old roles: TanStack Query 5 hands a query on its first load its own request back, rather than reading again. People now cancels the list before invalidating it. No other screen can meet this race.
- **K5** (contract `dev plans/contracts/k5-cli-and-site-template.md`, approved 2026-11-20; decision 0047): five PRs from #91.
  - **The owner's five answers:**
    - `diff` and `upgrade` wait for a module's second version;
    - `create-owner` prints a one-time set-password link;
    - Railway gets `FORWARDED_ALLOW_IPS=*`;
    - a site's own pages join in #92;
    - the template ships a CI workflow that runs `mechframe check` from a shallow clone.
  - **#91, the CLI's core:**
    - `cli/mechframe/` (`python -m mechframe`, or `mechframe` and `mf` after `python -m pip install -e .`), which copies from, and checks against, its own checkout;
    - `layout.py` (where the kernel and modules land in a site);
    - the lock and its hashes (`\r\n` read as `\n`);
    - `check`, which exits 2 on an invalid lock or manifest or a version semver refuses, 1 on an open high or critical advisory, and 0 otherwise;
    - `catalog`, and `schema/advisories.schema.json` (contract change 1);
    - every version pattern in `schema/` tightened to semver's grammar (change 3);
    - SPEC 4, 12, 13 and 17.
  - **Review:** Codex's two findings and CodeRabbit's four were fixed with failing-first tests: jsonschema is declared in `pyproject.toml`; a version semver refuses fails the schemas and `check`; an unreadable recorded file is a refusal; `validate_schemas` checks an `advisories.json` that holds `null`.
- **v1.0:** 58 % (35 of 60 steps). The ledger's `steps` dataset points at `main`'s rows once #91 lands (republished then).

## Next

1. **#92, the site template:**
   - `templates/site/` from the harness;
   - `kernel.modules.load_module`, with the harness moved onto it;
   - the site's own pages (`mountApp({ site })`, `create_app(site=...)`);
   - `mechframe new` (kernel only);
   - the Dockerfile, `railway.toml` and `.env.example`;
   - the site's tests and CI workflow;
   - `tools/site_smoke.py`, run by the E2E workflow.
2. **#93, `add` and `remove`**, on fixture modules.
3. **#94, `create-owner`.**
4. **#95, K5's gate.**

## Open questions for the owner

- A name for a person (nothing sets `display_name`)? A way for a site to reword the kernel's screens?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?
- cubic is at its trial limit, and CodeRabbit hit its free review limit once (#90): pay, or drop them?
- Two unused ledger assets, `cd100445…` and `0f244b76…`: delete them? The stray `C:\dev plans\` is the owner's to delete.

## Notes

- **The Bash tool decodes `\n`, `\r` and `\uXXXX` in command text,** even inside a quoted heredoc. Build backslashes and newlines with `chr()` in a script. `pyproject.toml`, `SPEC.md` and `CLAUDE.md` are CRLF: edit them with a script that keeps the file's newline.
- **`npx.cmd` breaks on an argument with a space:** run `node node_modules/vitest/vitest.mjs run <file> -t "<name>"`.
- **TanStack Query:** before invalidating a list whose key can change while a write is open, cancel it.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset`. The role e2e flake was the race #89 fixed.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first. (#91 only added `cli/` to the Python job's path filter.)
