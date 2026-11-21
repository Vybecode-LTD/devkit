# Next session: hook 3, search index (then hooks 4 to 10)

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-hook-search.md and follow it, starting with section 4."

## 1. The project

MechFrame: website modules on a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`), public repo mechframe/mechframe. The kernel is done; decision 0018's ten contract hooks go in one PR each before any module. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **Build to the approved contract,** `dev plans/contracts/hooks.md` (decision 0052): §2 names, §3 tables, §6 non-goals, §7 tests. A change is a dated line under "Changes after approval", told to the owner.
- **Each hook follows `skills/mechframe-hook-designer/SKILL.md`** steps 3 to 6, as #97 and #98 did.
- **Landing:** push once the local suites are green; land by fast-forward on a green "CI result" with no open thread. Stage files by name; run gitleaks on the staged diff.
- **The owner's call:** any Railway project, apply or variable, and any change to CI's security gates.

## 3. State (2026-11-20, night Eastern; check it, don't trust it)

- **main** should be `cc3929b` (#97), or #98's head if #98 has landed: `git log -1 origin/main`, `gh pr view 98`. **If #98 is open,** land it on a green "CI result", then republish the ledger (`dev plans/progress-ledger/README.md`).
- **#98 is hook 2, taxonomy** (`kernel/backend/kernel/taxonomy.py`, `kernel_0013`). The rest: `docs/HANDOFF.md`.

## 4. The job

1. **Hook 3, search index** (contract §2 row 3, §3's `kernel_search_document`), as #99:
   - `search.py`'s `SEARCH`, a `search.Source` with `document(db, id)` and `documents(db)`; `content_types[].search: true`; `search.index(db, doc)` and `search.remove(db, type, id)` for content without lifecycle;
   - the table in migration `kernel_0014`: `tsv` weighted (title A, body B) with a GIN index, `language` regconfig;
   - the kernel listens to `kernel.content.published` and `.unpublished` and calls the module's `document()`; the job `kernel.search.reindex` runs on demand;
   - `GET /api/kernel/search?q=&type=&cursor=&limit=` (public, `rate_limit("30/1m")`), ranked by `websearch_to_tsquery` in `SEARCH_LANGUAGE` (default `english`), public documents only;
   - the probe's notes are searchable, and `probe-addon`'s aren't; contract test 3: published is found, unpublished isn't.
   - Then `python -m tools.openapi`, `npm run api:types`.
2. **Then hooks 4 to 10** in the contract's order (bot check lifts VybeSite's `contact_filter.py`: run the brand check).
3. Then wave 1's modules (`docs/plans/vibrant-mindz-backend/KICKOFF.md` step 1).

## 5. Ask the owner, don't decide

- A public name and handle for a person (before hook 10).
- The rest: `docs/HANDOFF.md`, "Open questions".

## 6. Environment and traps

- **The full suite** (Git Bash, in the background, its log in the scratchpad, **about 30 minutes**, no edits meanwhile): `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov`. Run the hook's own tests, and a mutant script, first.
- **Contract tests** call only routes in `docs/contracts/auth-api.md`. A 404 `kernel.not_found` reads as "not built": give a missing thing its own code.
- **The kernel listening to its own events is new:** `events.build` takes the kernel's listeners as `()` today (`app.py`). Update `test_the_kernel_declares_the_eleven_events_it_emits` and `test_create_worker_builds_what_create_app_would` for the new job.
- **A unit test's fixture** restores a kernel module's installed global with `monkeypatch.setattr`, never empties it: the contract suite's app reads the same one.
- **A new audit action** goes in `audit.KERNEL_ACTIONS`. **A new config value** (`SEARCH_LANGUAGE`) goes in `KernelConfig` and the site template's `.env.example`.
- **The Bash tool decodes `\n` and `\uXXXX`:** write patch scripts with the Write tool. `AGENTS.md` matches `CLAUDE.md` except its title.

## 7. Evidence and next IDs

Decision 0052 and the contract; `docs/HANDOFF.md`. Next free: PR #99, decision 0053 (the hooks share 0052), migration `kernel_0014`.

## 8. Candidates for `knowledge/`

1. A mixin's `__table_args__` is silently replaced by a subclass's own: check at start for its names.
2. A fake module's tables go on a metadata of their own, made when the test app starts.
3. A unit test that empties a module global breaks a session-wide app that reads it, but only when it runs first: restore the global, don't clear it.
