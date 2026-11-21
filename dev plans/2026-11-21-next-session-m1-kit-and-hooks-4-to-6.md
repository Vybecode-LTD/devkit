# Next session (M1): the kit's two fixes, then hooks 4 to 6

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-21-next-session-m1-kit-and-hooks-4-to-6.md and follow it, starting with section 4."

## 1. The project

MechFrame: website modules on a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`), public repo mechframe/mechframe. The kernel is done; hooks 1 to 3 are in (#97 to #99). This is session M1 of `dev plans/2026-11-21-vibrant-mindz-push-plan.md`, the road to Vibrant Mindz's step 1. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **Each hook** is built to `dev plans/contracts/hooks.md` (decision 0052): its §2 row, §6 and its §7 test. Follow `skills/mechframe-hook-designer/SKILL.md` steps 3 to 6. `git show --stat 43d3934` (#99) lists every place a hook touches. A change is a dated line under "Changes after approval", told to the owner in the PR.
- **Hooks 9 and 10 wait** (the owner, 2026-11-21): don't start them.
- **Landing:** push once local suites are green; land by fast-forward on a green "CI result" with no open thread. Stage by name; gitleaks on the staged diff.
- **Never edit `C:\DEV\VM Website`:** a Vibrant Mindz session works there.
- **The owner's call:** any Railway project, apply or variable, and CI's security gates.

## 3. State (2026-11-21, morning Eastern; check it, don't trust it)

- **main** should be #100's head (the plan), with #99 (hook 3) landed before it: `git log -1 origin/main`, `gh pr list`. **If #100 is open,** land it on a green "CI result", then republish the ledger (`dev plans/progress-ledger/README.md`).
- The rest: `docs/HANDOFF.md`.

## 4. The job, in order

Stack the PRs: start the next on a branch from the last while its CI runs, and merge `main` in once the first lands.

0. **Read the Vibrant Mindz handoff's "For MechFrame" list,** if it has one (`C:\DEV\VM Website\docs\HANDOFF.md`, read only).
1. **#101, the kit's two fixes** (the plan, "The kit's two fixes"): a field-fill token role, and the gap ring on every switch. Run the kit's tests, and `kernel/tests/e2e/kit.spec.ts` where they apply.
2. **#102, hook 4, seed data** (§2 row 4):
   - `seed.py`'s `async def seed(db, ctx)`, discovered like `SEARCH`;
   - `python -m harness.seed`, the site's `python -m app.seed`, and `mechframe seed --site <dir>`;
   - refused unless `MECHFRAME_ALLOW_SEED=1`, which the template's `railway.ts` never sets (a template test).
   - Settled ahead (log both): the contract test seeds through `POST /api/_test/seed`; the site's own seed (`backend/app/site/seed.py`) runs last, after the modules.
3. **#103, hook 5, bot check:** it lifts VybeSite's `contact_filter.py` (run the brand check). `bot.verify` answers Pass or Held, never a silent drop.
4. **#104, hook 6, consent** (stretch): the `CSP` entries' third item, `consent` on `GET /api/kernel/site`, `useConsent` and `<ConsentGate>`, `CONSENT_MODE=ask`.

Close out at a natural break past ~400K tokens; the next prompt names what's left (M2: hooks 7 and 8).

## 5. Ask the owner, don't decide

- A public name and handle for a person (hook 10, which waits).
- The rest: `docs/HANDOFF.md`, "Open questions".

## 6. Environment and traps

- **The full suite** (Git Bash, in the background, its log in the scratchpad, 20 to 30 minutes, no code edits meanwhile, since CLI tests copy the kernel): `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov`. Run the hook's own tests and a mutant script first. **Never use `--cov=<one module>`:** it breaks SQLAlchemy's compiled cache keys.
- **A surviving mutant can be the test's fault** (#99: a paging test needed more than a page plus one).
- **Contract tests** call only routes in `docs/contracts/auth-api.md`. A unit fixture restores a kernel global with `monkeypatch.setattr`. A new config value goes in `KernelConfig`, both `.env.example` files and the template's `railway.ts`. More: `docs/HANDOFF.md`, "Notes".
- **The Bash tool decodes `\n` and `\uXXXX`:** write patch scripts with the Write tool. `AGENTS.md` matches `CLAUDE.md` but its title.

## 7. Evidence and next IDs

Decision 0052, the contract, the plan, `docs/HANDOFF.md`. Next free: PR #101, decision 0053, migration `kernel_0015`.

## 8. Candidates for `knowledge/`

1. A keyset cursor over a float rank: cast `ts_rank` (a `real`) to `float8`, and send it back as Python's `repr`.
2. SQLAlchemy's `Session.execute` autoflushes even for `text()`, so a lock-order test needs `no_autoflush` to fail.
3. Index out-of-order events by re-reading the thing as it is now under a per-thing lock.
