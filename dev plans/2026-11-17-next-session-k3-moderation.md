# Next session: K3 moderation, contract first

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-17-next-session-k3-moderation.md and follow it, starting with section 4."

## 1. The project

AI DevKit (MechFrame after K3, decision 0034): website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`; nothing deployed. Vibrant Mindz waits on it (decision 0029).

## 2. Rules that aren't in a CLAUDE.md

- A kernel service is a seam: its contract first (`C:\DEV\_templates\feature-CONTRACT.md`); the owner approves the goal and non-goals before code.
- Commit with the no-reply address; stage by name; `gitleaks git --pre-commit --staged` first.
- Pushing and landing are this session's call (`CLAUDE.md` Rules): land when "CI result" is green on the head and the bots have no open findings (CodeRabbit rate-limited is fine). If auto mode refuses the push, hand the owner the command.
- New kernel audit actions join `audit.KERNEL_ACTIONS`; lists use `?cursor=&limit=` and `{items, next_cursor}`; bodies are strict models.
- Keep the DevKit name until the rename PR.

## 3. State (verified 2026-11-17, end of session)

- `main` at f3cd4db (#69, K3 notifications, landed). Its branch is deleted.
- **#70** (`docs/handoff-k3-moderation`: `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md`, this file) is the only open PR. Land it when "CI result" is green and the bots have no open findings.
- Last local full run: 1422 passed, 7 skipped, 27 xfailed, coverage 98.23 %. CI passed on f3cd4db. Nothing is half-done.
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner's to commit.

## 4. The job, in order

1. If #70 is still open, land it as above; then `git switch main`, `git pull --ff-only`.
2. **K3 moderation:** write `dev plans/contracts/k3-moderation.md` and bring the owner its goal and non-goals. Inputs: SPEC 6 (`moderation.report / queue / act`), 11 (`auth.user.suspended`), 14.1 and 14.10; decision 0031 (`kernel.moderation.act`); `kernel/audit.py` (record actions; the owner wants moderators to see a narrower audit view); `kernel/notifications.py` (telling the reported person?); KICKOFF K3: `C:\DEV\VybeMindz\moderation-audit-log.zip` (unzip into a new empty scratch folder, read only), VybeSite `services/blocklist_service.py`, `contact_filter.py`. Ask the owner: what a module reports (any target, by kind and id?), who sees the queue, which actions the kernel takes itself (suspend) and which modules carry out (hide a comment), filters now or later, and appeals. Update `docs/progress.json` in the PR.
3. Then public rendering, K3's gate, then the rename PR.

## 5. Questions for the owner (ask; don't decide)

- Decisions 0036's, 0035's, 0032's and 0033's own calls (`docs/HANDOFF.md`, Open questions): keep them?
- When to make the R2 test buckets for `test_storage_live.py`.
- Desk steps: the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, about 10 minutes, with `run_in_background`, logged to the scratchpad. Never `--cov=kernel.<module>`.
- Shared test database: filter on the test's own people and targets; after `db.rollback()` keep plain ids, never ORM attributes.
- Git Bash: write scripts with the Write tool; subprocesses use `sys.executable`; mutant scripts restore bytes.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decisions 0037, 0038; `dev plans/contracts/k3-audit.md`, `k3-notifications.md`; #67's and #69's threads.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0039, PR #71, migration `kernel_0010`.

## 8. Candidates for `knowledge/`

1. Python's email package folds a long `List-Unsubscribe` into RFC 2047 encoded words; a policy subclass writes it whole (CodeRabbit on #69).
2. One-click unsubscribe: GET never changes anything (link scanners); the POST is the one cross-site write to allow.
3. An upsert after a read must write only the columns it means to change, or it undoes a concurrent change (race test: hold the row, wait for `pg_stat_activity` to show the lock).
4. Queue the email before adding the row: a refused email then leaves nothing in the session.
5. A staff reader goes under `/api/<id>/admin`; lists follow SPEC 7's names.
