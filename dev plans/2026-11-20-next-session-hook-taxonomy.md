# Next session: hook 2, taxonomy (then hooks 3 to 10)

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-hook-taxonomy.md and follow it, starting with section 4."

## 1. The project

MechFrame: website modules on a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`), in the public repo mechframe/mechframe. The kernel is done but K2's steps 9 to 11 (decision 0029). Decision 0018's ten contract hooks are being added, one PR each, before any module is built. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **Build to the approved contract,** `dev plans/contracts/hooks.md` (decision 0052): names §2, tables §3, order §4, non-goals §6, tests §7. A change to it is a dated "Changes after approval" line, told to the owner.
- **Each hook follows `skills/mechframe-hook-designer/SKILL.md`** steps 3 to 6, as #97 did.
- **Landing:** push once the local suites are green; land by fast-forward on a green "CI result" with no open thread. Stage files by name, and run gitleaks on the staged diff.
- **The owner's call:** any Railway project, apply or variable, and any change to CI's security gates.

## 3. State (2026-11-20, night Eastern; check it, don't trust it)

- **main** should be `407dadb` (#96), or #97's head if #97 has landed: `git log -1 origin/main`, `gh pr view 97`. **If #97 is open,** land it on a green "CI result", then republish the ledger (`dev plans/progress-ledger/README.md`).
- **#97 is hook 1, content lifecycle:** `kernel/backend/kernel/lifecycle.py`, the probe's notes in `harness/probe.py`, and their tests. The rest: `docs/HANDOFF.md`.

## 4. The job

1. **Hook 2, taxonomy** (contract §2 row 2, §3), as #98:
   - module.json's `vocabularies: [{key, label, hierarchical}]` and `content_types[].taxonomy`;
   - the tables `kernel_vocabulary`, `kernel_term` and `kernel_term_link` in migration `kernel_0013`, with `kernel.taxonomy.manage` (admin, editor) seeded in `kernel/kernel.json` and the migration;
   - `taxonomy.tag`, `terms_for`, `tagged` and `untag_all`;
   - `GET /api/kernel/terms?vocabulary=` (public), and admin `POST`, `PATCH` and `DELETE /api/kernel/admin/terms[/{id}]`;
   - the probe's notes take topics, and `probe-addon` none.
   - Then run `python -m tools.openapi` and `npm run api:types`, since routes change.
2. **Then hooks 3 to 10, in order:** search index, seed data, bot check (lifts VybeSite's `contact_filter.py`: run the brand check), consent, export and erase, dashboard cards, entitlements, profile tabs. **Before hook 10,** ask the owner for a person's public name and handle.
3. Then wave 1's modules (`docs/plans/vibrant-mindz-backend/KICKOFF.md` step 1).

## 5. Ask the owner, don't decide

- A public name and handle for a person (before hook 10).
- The rest is in `docs/HANDOFF.md`, "Open questions": `mechframe-iac-probe`, four unused ledger assets, the review bots' limits.

## 6. Environment and traps

- **The full suite** (Git Bash, in the background, its log in the scratchpad, **about 30 minutes**, no edits meanwhile): `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov`. Run a hook's own tests on their own first.
- **A contract test** may call only routes in `docs/contracts/auth-api.md` (add the probe's new ones to its test-support table); a public page or `sitemap.xml` takes `extensions=UNCHECKED`.
- **The probe's tables** go on `harness.probe.TABLES`, which the test support makes at start, never on `Base` (the migration check would see them).
- **A new kernel event or job:** update `test_the_kernel_declares_the_eleven_events_it_emits` and `test_create_worker_builds_what_create_app_would`.
- **A new kernel permission:** `kernel/kernel.json`, its seed in the migration, and the test that holds the seed to the list.
- **The Bash tool decodes `\n` and `\uXXXX`,** and heredocs with quotes can break: write patch scripts with the Write tool. `AGENTS.md` matches `CLAUDE.md` but for its title.

## 7. Evidence and next IDs

Decision 0052 and the contract; `docs/HANDOFF.md`. Next free: PR #98, decision 0053 (the hooks share 0052), migration `kernel_0013`.

## 8. Candidates for `knowledge/`

1. A declarative mixin's `__table_args__` is silently replaced by a subclass's own: check at start for the mixin's constraint and index names.
2. A fake module's tables for contract tests go on a metadata of their own, made when the test app starts, so the migration check never sees them.
