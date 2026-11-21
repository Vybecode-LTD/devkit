# Next session: the contract hooks, then the modules' wave 1

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-modules-wave-1.md and follow it, starting with section 4."

## 1. The project

MechFrame: website modules on a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`); public repo mechframe/mechframe. The kernel is done (K0 to K5) but K2's steps 9 to 11, which wait for the site (decision 0029). No module is built. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **Hooks before modules:** decision 0018's ten hooks go into SPEC before a module that fills them is extracted (`docs/plans/vibrant-mindz-backend/KICKOFF.md` line 18; `docs/plans/module-roadmap.md` wave 0: one decision for the batch, one PR per hook).
- **Contract first:** the hooks change the module contract, so their one-page contract (`C:\DEV\_templates\feature-CONTRACT.md`) goes to the owner, who approves it before any code.
- **Landing:** push once local suites are green; batch fixes; land by fast-forward on a green "CI result" with no open thread. Stage by name; gitleaks the staged diff.
- **The owner's call:** any Railway project, apply or variable; any change to CI's security gates.

## 3. State (2026-11-20, late evening Eastern; check, don't trust)

- **main** should be #96's head (K5's gate, this prompt): `git log -1 origin/main`, `gh pr view 96`. If #96 is open, land it, then republish the ledger (`dev plans/progress-ledger/README.md`).
- **K5's gate passed** at `b543642`; the kernel's close, the spec sections changed since K0 and one gap are in `dev plans/2026-11-20-k5-gate-evidence.md`. The rest: `docs/HANDOFF.md`.

## 4. The job

1. **The ten hooks' contract** (`dev plans/contracts/hooks.md`, decision 0052), with `mechframe-hook-designer` (its "first batch" table; re-check SPEC, the table is from 2026-11-13). Per hook: what SPEC has, the shape (manifest field, fixed file and function, slot or event), its contract test, its `module-contract-lint` row. Recommend an order, wave 1's hooks first (content lifecycle, taxonomy, search index, seed data, bot check, consent, export and erase). Ask the owner to approve; code nothing until they do.
2. **One PR per hook,** tests first, each with its SPEC change-log line; tell the owner which sections changed.
3. **Then wave 1** (that KICKOFF's step 1): `media`, `pages`, `blog`, `embeds`, `contact`, `campaigns` from VybeSite with `mechframe-module-extractor`, each to its brief in `docs/plans/vibrant-mindz-backend/extraction/`. The first one closes the gap: `mechframe check` and `module-contract-lint` check `MODULE.md`'s sections (SPEC 16's Docs row, SPEC 17).

## 5. Ask the owner

- **`mechframe-iac-probe`** isn't needed now K5's gate has passed: deleting it is the owner's.
- **A Railway variable to confirm a destructive migration** at pre-deploy (decision 0049, alternatives)?
- The rest: `docs/HANDOFF.md`, "Open questions". Ask, don't decide.

## 6. Environment and traps

- **Python tests** (Git Bash, background, log in the scratchpad, about 13 minutes, no edits meanwhile): `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov`.
- **The smoke:** `TEST_DATABASE_URL=... PYTHONPATH=cli .venv/Scripts/python.exe -m tools.site_smoke --keep` (about 6 minutes). A redirected log gets its stdout only at the end; each step shows live in `%TEMP%\mechframe-smoke-*\smoke.log`.
- **`tools.npm_audit` reads the repo's root lockfile only:** in a made site, run `npm audit` twice, once in its root and once in `web/`, one for each lockfile.
- **`$TMP` in Git Bash is `%TEMP%`,** not the scratchpad.
- **The Bash tool decodes `\n`, `\r`, `\u`:** write patch scripts with the Write tool, `chr(13) + chr(10)` for CRLF. Most docs are CRLF; `AGENTS.md` matches `CLAUDE.md` but its title.

## 7. Evidence and next IDs

`docs/HANDOFF.md`; the K5 gate evidence; decisions 0018, 0029, 0047 to 0051; `skills/mechframe-hook-designer/SKILL.md`. Next free: decision 0052, PR #97, migration `kernel_0013`.

## 8. Candidates for `knowledge/`

1. A destructive-migration gate asks only where the branch already holds data; its confirmation names the revision.
2. Keeping a removed module's tables means keeping its migrations: `alembic_version` still names them.
3. A lock test holding a row FOR UPDATE also blocks the foreign-key checks under test: hold it FOR SHARE.
4. An audit of a repo's own lockfile misses the lockfiles its generator ships: audit the generated project too.
