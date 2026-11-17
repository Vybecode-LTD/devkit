# Next session: K3 notifications, contract first

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-17-next-session-k3-notifications.md and follow it, starting with section 4."

## 1. The project

AI DevKit (MechFrame after K3, decision 0034): website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`; nothing deployed. Vibrant Mindz waits on it (decision 0029).

## 2. Rules that aren't in a CLAUDE.md

- A kernel service is a seam: its contract first (`C:\DEV\_templates\feature-CONTRACT.md`); the owner approves the goal and non-goals before code.
- Commit with the no-reply address; stage by name; run `gitleaks git --pre-commit --staged` first.
- Pushing and landing are this session's call (`CLAUDE.md` Rules, the owner's explicit grant): land when "CI result" is green on the head and the bots have no open findings. If auto mode refuses the landing push, hand the owner the command.
- A new kernel audit action joins `audit.KERNEL_ACTIONS` in the same PR (a test holds the set to the code).
- A list route follows SPEC 7: `?cursor=&limit=` in, `{items, next_cursor}` out.
- Keep the DevKit name until the rename PR.

## 3. State (verified 2026-11-17, end of session)

- `main` at 0005271 (#67, K3 audit, landed). Its branch is deleted.
- **#68** (`docs/handoff-k3-notifications`: `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md`, this file) is the only open PR. Land it when "CI result" is green on its head and the bots have no open findings.
- Last local full run: 1382 passed, 7 skipped, 27 xfailed, coverage 98.20 %. CI passed on #67's head. Nothing is half-done.
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner's to commit.

## 4. The job, in order

1. If #68 is still open, land it as above; then `git switch main`, `git pull --ff-only`.
2. **K3 notifications:** write `dev plans/contracts/k3-notifications.md` and bring the owner its goal and non-goals. Inputs: SPEC 6 (`notify(user, key, context)`), SPEC 5 and `schema/module.schema.json` (`notifications`), `kernel/email.py` (`email.queue`), `kernel/events.py`, the scaffolds in `modules/_*`, KICKOFF K3 (Basefra.me's notification center for ideas). Ask the owner: what the in-site list keeps and how long; per-key preferences only or a global "no email" too; the one-click unsubscribe link (RFC 8058); digests now or later. Update `docs/progress.json` in the PR.
3. Then moderation (emits `auth.user.suspended`, audits its actions, a narrower audit view for moderators), public rendering, K3's gate; then the rename PR.

## 5. Questions for the owner (ask; don't decide)

- Decisions 0036's, 0035's, 0032's and 0033's own calls (`docs/HANDOFF.md`, Open questions): keep them?
- When to make the R2 test buckets for `test_storage_live.py`.
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, about 10 minutes: run it with `run_in_background`, logged to the scratchpad. Not `--cov=kernel.<module>`: it breaks the run.
- Kernel events in tests: the `heard` fixture. Due jobs: `Draining`. Audit entries: filter on a target, actor or subject of the test's own.
- Git Bash: write scripts with the Write tool (heredocs break on `'''`, `cat > f` waits on stdin, `sed -i` drops CRs). Subprocesses: `sys.executable`. Mutant scripts restore bytes.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decision 0037; `dev plans/contracts/k3-audit.md`; #67's body and thread.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0038, PR #69, migration `kernel_0009`.

## 8. Candidates for `knowledge/`

1. A staff reader goes under `/api/<id>/admin`, where the admin gate adds a staff role and a second factor.
2. An append-only Postgres log: a row trigger allowing DELETE only after `set_config('x.y', 'on', true)`, plus a statement trigger for TRUNCATE; JSONB refuses a NUL at flush.
3. `pytest --cov=<package>.<module>` can import the package before a root conftest that must run first.
4. A `len(found) > limit` mutant survives unless a page ends exactly at the last row (`verify-real-pass`).
5. Git Bash's `sed -i` rewrites CRLF files as LF.
