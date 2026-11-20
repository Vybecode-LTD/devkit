# Next session: K5's gate (#96), and the kernel's close

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-k5-gate.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public: mechframe/mechframe. Nothing is deployed but a throwaway Railway project (section 5).

## 2. Rules not in a CLAUDE.md

- **K5's contract** is `dev plans/contracts/k5-cli-and-site-template.md`, decisions 0047 to 0051. Its next change is 10.
- **Landing:** push once local suites are green, and batch fixes. Land by fast-forward once "CI result" is green and no thread is open. Stage by name, and run gitleaks on the staged diff.
- **CodeRabbit hit its free review limit** at #93; it may review again after it resets. Pay or drop it: the owner's call.
- **Outward-facing is the owner's call:** no Railway project, apply or variable for a site, and no change to CI's security gates.

## 3. State (2026-11-20, evening Eastern; check, don't trust)

- **main** should be #95's head, with this prompt. Check with `git log -1 origin/main` and `gh pr view 95`. If #95 is still open, land it first, then republish the ledger (`dev plans/progress-ledger/README.md`).
- **K5's PRs:** #91 (CLI core), #92 (template), #93 (destructive migrations), #94 (`add`, `remove`, `new --recipe`) and #95 (`create-owner`). The rest: `docs/HANDOFF.md`.

## 4. The job

1. **#96, K5's gate** (docs only; KICKOFF K5; the contract's §7):
   - `python -m tools.site_smoke --keep` locally: a kernel-only `test-site` that installs, builds, migrates, passes its tests and checks clean, then a second pass with the fixture modules added. Main's E2E has run it green since `40f494b`.
   - The rest of §7, each bullet to its tests, as `dev plans/2026-11-20-k4-gate-evidence.md` did for K4.
   - Write `dev plans/<date>-k5-gate-evidence.md`; set K5's `gate_passed` in `docs/progress.json`; run `python -m tools.progress`.
2. **"The kernel is done when"** (KICKOFF): SPEC 16's rows in CI, the auth contract tests, the brand check, gitleaks, pip-audit and npm audit clean, the docs current, and the owner given the list of spec sections that changed since K0. Then write `dev plans\<date>-next-session-modules-wave-1.md` as KICKOFF says.

## 5. Ask the owner

- **`mechframe-iac-probe`** (Railway, "color8's Projects") was kept until K5's gate: say it's no longer needed. Deleting it is the owner's.
- **A Railway variable to confirm a destructive migration** in the pre-deploy step? (Decision 0049, alternatives.)
- The rest: `docs/HANDOFF.md`, "Open questions". Ask, don't decide.

## 6. Environment and traps

- **Python tests,** in Git Bash, in the background, into a log in the scratchpad, about 13 minutes. Change no file while they run:

  ```bash
  TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov
  ```

- **The smoke:** `TEST_DATABASE_URL=... PYTHONPATH=cli .venv/Scripts/python.exe -m tools.site_smoke --keep` (about 5 minutes, pip cached).
- **`$TMP` in Git Bash is `%TEMP%` itself,** not the session's scratchpad: use the scratchpad's full path.
- **The Bash tool decodes `\n`, `\r` and `\u`** in command text: write patch scripts with the Write tool. Most docs are CRLF here.

## 7. Evidence and next IDs

`docs/HANDOFF.md`; decisions 0047 to 0051; the contract's changes 1 to 9; the bodies of #91 to #95.

Next free: decision 0052, PR #96, migration `kernel_0013`, contract change 10.

## 8. Candidates for `knowledge/`

1. A destructive-migration gate asks only where the branch already holds data, and its confirmation names the revision.
2. Keeping a removed module's tables means keeping its migrations too: `alembic_version` still names the revision.
3. A lock test that holds a row FOR UPDATE also blocks the foreign-key checks under test: hold it FOR SHARE to isolate a deliberate FOR UPDATE.
