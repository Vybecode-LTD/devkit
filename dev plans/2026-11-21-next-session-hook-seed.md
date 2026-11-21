# Next session: hook 4, seed data (then hooks 5 to 10)

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-21-next-session-hook-seed.md and follow it, starting with section 4."

## 1. The project

MechFrame: website modules on a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`), public repo mechframe/mechframe. The kernel is done; decision 0018's ten contract hooks go in one PR each before any module. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **Build to the approved contract,** `dev plans/contracts/hooks.md` (decision 0052): §2 row 4, §6 non-goals, §7 test 4. A change is a dated line under "Changes after approval", told to the owner.
- **Each hook follows `skills/mechframe-hook-designer/SKILL.md`** steps 3 to 6, as #97 to #99 did.
- **Landing:** push once the local suites are green; land by fast-forward on a green "CI result" with no open thread. Stage files by name; run gitleaks on the staged diff.
- **The owner's call:** any Railway project, apply or variable, and any change to CI's security gates.

## 3. State (2026-11-21, morning Eastern; check it, don't trust it)

- **main** should be #99's head (hook 3, search index): `git log -1 origin/main`, `gh pr view 99`. **If #99 is open,** land it on a green "CI result", then republish the ledger (`dev plans/progress-ledger/README.md`).
- **#99 is hook 3** (`kernel/backend/kernel/search.py`, `kernel_0014`). The rest: `docs/HANDOFF.md`.

## 4. The job

1. **Hook 4, seed data** (contract §2 row 4), as #100:
   - `seed.py`'s `async def seed(db, ctx)`, idempotent, discovered like `SEARCH`; `ctx` as §2 says;
   - `python -m harness.seed`, the site's `python -m app.seed`, and `mechframe seed --site <dir>` (as `create-owner` runs `app.owner`); the kernel first, then `requires` order;
   - refused unless `MECHFRAME_ALLOW_SEED=1`, which the template's `railway.ts` never sets (a template test);
   - the probe seeds notes, `probe-addon` nothing. Contract test 4: twice leaves the same rows; without the variable it refuses.
2. **Then hooks 5 to 10** in the contract's order (bot check lifts VybeSite's `contact_filter.py`: run the brand check).
3. Then wave 1's modules (`docs/plans/vibrant-mindz-backend/KICKOFF.md` step 1).

## 5. Ask the owner, don't decide

- **How contract test 4 seeds over HTTP:** the contract suite calls routes only. A `/api/_test/seed` route in the test support (`harness/testing.py`, listed in `docs/contracts/auth-api.md`) is the likely way; say so in "Changes after approval" if you take it.
- A public name and handle for a person (before hook 10).
- The rest: `docs/HANDOFF.md`, "Open questions".

## 6. Environment and traps

- **The full suite** (Git Bash, in the background, its log in the scratchpad, **about 30 minutes**, no edits meanwhile): `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov`. Run the hook's own tests, and a mutant script, first.
- **A mutant that survives can be the test's fault:** #99's inner ORDER BY flip passed until a paging test had more results than a page and one.
- **A job's name has one dot** (`<owner>.<name>`, `jobs.NAME`): `kernel.search_reindex`, not `kernel.search.reindex`.
- **The kernel listens to its own events** since #99 (`app.KERNEL_LISTENERS`). The contract block runs first (pytest sorts `contract/` first), so its app keeps them.
- **Contract tests** call only routes in `docs/contracts/auth-api.md`; a 404 `kernel.not_found` reads as "not built".
- **A unit test's fixture** restores a kernel global with `monkeypatch.setattr`, never empties it.
- **A new config value** goes in `KernelConfig`, both `.env.example` files and the template's `railway.ts` (`tests/test_site_template.py`).
- **The Bash tool decodes `\n` and `\uXXXX`:** write patch scripts with the Write tool. `AGENTS.md` matches `CLAUDE.md` but its title.

## 7. Evidence and next IDs

Decision 0052 and the contract; `docs/HANDOFF.md`. Next free: PR #100, decision 0053 (the hooks share 0052), migration `kernel_0015` (seed data may need none).

## 8. Candidates for `knowledge/`

1. A keyset cursor over a float rank: cast `ts_rank` (a `real`) to `float8`, and send it back as Python's `repr`, which round-trips.
2. An inner ORDER BY ... LIMIT under an outer re-sort hides an order bug unless a test has more rows than the limit plus one.
3. Index events that may arrive in any order by re-reading the thing as it is now under a per-thing lock, not by trusting which event came.
