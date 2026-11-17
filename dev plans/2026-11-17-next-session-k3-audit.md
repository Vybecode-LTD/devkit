# Next session: K3 audit, contract first

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-17-next-session-k3-audit.md and follow it, starting with section 4."

## 1. The project

AI DevKit (MechFrame after K3, decision 0034): website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`; nothing deployed. Vibrant Mindz waits on it (decision 0029).

## 2. Rules that aren't in a CLAUDE.md

- A kernel service is a seam: its contract first (`C:\DEV\_templates\feature-CONTRACT.md`); the owner approves the goal and non-goals before code.
- Commit with the no-reply address; stage by name; run `gitleaks git --pre-commit --staged` first.
- Pushing and landing are this session's call (`CLAUDE.md` Rules, the owner's explicit grant). If auto mode refuses the landing push, hand the owner the command.
- Keep the DevKit name until the rename PR.

## 3. State (verified 2026-11-17, end of session)

- `main` at 161d0fa (#65, K3 events, landed). Its branch is deleted.
- **#66** (`docs/handoff-k3-audit`: `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md`, progress, this file) is the only open PR. Land it when "CI result" is green.
- Last local full run: 1279 passed, 7 skipped, 27 xfailed, coverage 98.12 %. CI passed on 161d0fa. Nothing is half-done.
- `C:\DEV\knowledge\owner.md` is uncommitted (the push-and-merge rule and an older line): the owner's to commit.

## 4. The job, in order

1. If #66 is still open, land it once "CI result" is green; then `git switch main`, `git pull --ff-only`.
2. **K3 audit:** write `dev plans/contracts/k3-audit.md` and bring the owner its goal and non-goals. Inputs: SPEC 6 (`audit.record(actor, action, target, meta)`), 14.10 and 10 (retention), `kernel/auth/audit.py` (`record`, `record_by_kernel`, `auth_audit_event`), KICKOFF K3 (lift from VybeSite `services/staff_activity.py`, Basefra.me `app/audit/`). Ask the owner: one table or auth's plus a kernel one; who reads it (K4's Audit log page, `auth.audit.read`); retention. `settings.save`'s `# K3: audit it` marker is a first use. Update `docs/progress.json` in the PR.
3. Then notifications, moderation (it emits `auth.user.suspended`), public rendering, K3's gate; then the rename PR.

## 5. Questions for the owner (ask; don't decide)

- Decision 0036's own calls (`docs/HANDOFF.md`, Open questions): keep them?
- Decision 0035's, 0032's and 0033's own calls: keep them?
- When to make the R2 test buckets for `test_storage_live.py`.
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, about 9 minutes: run it with `run_in_background`, logged to the scratchpad.
- Kernel events in tests: the `heard` fixture (`kernel/tests/conftest.py`). Due jobs: `Draining`.
- A test that moves the clock and runs a worker with the kernel's jobs also runs mail other tests left queued: give it only the test's own jobs.
- Git Bash: `cat > file` with nothing piped in hangs; write scripts with the Write tool. Mutant scripts: `sys.executable`, and restore bytes (CRLF working tree).

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decision 0036; `dev plans/contracts/k3-events.md`; #65's body and thread.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\` (`push-and-merge-own-judgment.md` is new).
- Next free IDs: decision 0037, PR #67, migration `kernel_0008`.

## 8. Candidates for `knowledge/`

1. Auto mode refused recording "the agent may merge" as undermining oversight until the owner worded it as an explicit, conditional grant: now `owner.md`'s rule.
2. A shared test worker picks up other tests' retries once a test moves the clock: run only the test's own jobs (`verify-real-pass`).
3. Git Bash: `cat > f` without a heredoc blocks on stdin for ever (`windows-shell-and-tool-traps`).
4. `subprocess.run([".venv/Scripts/python.exe", ...])` fails with WinError 2: use `sys.executable`.
5. Events as jobs written at emit avoid a dispatcher's lost wake-up behind a job key held while it runs.
