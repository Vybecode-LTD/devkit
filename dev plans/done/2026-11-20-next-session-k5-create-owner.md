# Next session: K5's `create-owner` (#95), then K5's gate (#96)

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-k5-create-owner.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public: mechframe/mechframe. Nothing is deployed but a throwaway Railway project (section 5).

## 2. Rules not in a CLAUDE.md

- **K5's contract** is `dev plans/contracts/k5-cli-and-site-template.md`, decisions 0047 to 0050. Its next change is 9.
- **Landing:** push once local suites are green, and batch fixes. Land by fast-forward once "CI result" is green and no thread is open. Stage by name, and run gitleaks on the staged diff.
- **CodeRabbit is at its free review limit** (since #93), so #94 landed on CI and Codex alone. Pay or drop it: the owner's call.
- **Outward-facing is the owner's call:** no Railway project, apply or variable for a site, and no change to CI's security gates.
- **`AGENTS.md` holds `CLAUDE.md`'s text,** and the template's two files hold the same rules: change both of each pair together.

## 3. State (2026-11-20, evening Eastern; check, don't trust)

- **main** should be #94's head, with this prompt. Check with `git log -1 origin/main` and `gh pr view 94`. If #94 is still open, land it first, then republish the ledger (`dev plans/progress-ledger/README.md`).
- **#93** gave `kernel.migrate` (decision 0049). **#94** gave `add`, `remove` and `new --recipe` (decision 0050). The rest: `docs/HANDOFF.md`.

## 4. The job

1. **#95, `create-owner`** (contract §2 and §4 item 5; the owner's answer 2, a one-time set-password link), tests first:
   - `kernel.auth.owners.create_owner(db, email) -> str`: the account, with the owner role, made through the kernel's own functions (no new tables), and a one-time link to set its password. Read SPEC 14 and `kernel/backend/kernel/auth/resets.py` first.
   - The template's real `backend/app/owner.py` (`python -m app.owner <email>`), and `mechframe create-owner <email> [--site <dir>]` running the site's `.venv` Python.
   - Ask the owner what a second run does, with an owner already there.
2. **#96, K5's gate** (docs only): `python -m tools.site_smoke --keep` locally (a kernel-only site, then a pass with the fixture modules added). Evidence in `dev plans/<date>-k5-gate-evidence.md`.

## 5. Ask the owner

- **`mechframe-iac-probe`** (Railway, "color8's Projects") is kept until K5's gate: only `railway config plan` against it, read-only. The owner deletes it after.
- **A Railway variable to confirm a destructive migration** in the pre-deploy step? Today the owner runs it by hand against the Postgres's `DATABASE_PUBLIC_URL` (decision 0049, alternatives).
- The rest: `docs/HANDOFF.md`, "Open questions". Ask, don't decide.

## 6. Environment and traps

- **Python tests,** in Git Bash, in the background, into a log in the scratchpad, about 13 minutes. Change no file while they run:

  ```bash
  TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov
  ```

- **`$TMP` in Git Bash is `%TEMP%` itself,** not the session's scratchpad: write logs and scripts to the scratchpad's full path.
- **The Bash tool decodes `\n`, `\r` and `\u`** in command text, heredocs too: write patch scripts with the Write tool. Most docs are CRLF here.
- **Railway's SDK on Windows:** `env "_=$RW" "$RW" config plan`, with `RW="$(cygpath -w "$(npm.cmd root -g | tr -d '\r')/@railway/cli/bin/railway.exe")"`.

## 7. Evidence and next IDs

`docs/HANDOFF.md`, decisions 0049 and 0050, the contract's changes 7 and 8, and the bodies of #93 and #94.

Next free: decision 0051, PR #95, migration `kernel_0013`, contract change 9.

## 8. Candidates for `knowledge/`

1. A destructive-migration gate asks only where the branch already holds data, and its confirmation names the revision. Otherwise owners learn to confirm blindly, or a flag left in a deploy lets every later one through.
2. Keeping a removed module's tables means keeping its migrations too: `alembic_version` still names the revision.
3. A Railway IaC partial deletes unlisted variables: a tool that adds settings writes them there too, as `preserve()`.
