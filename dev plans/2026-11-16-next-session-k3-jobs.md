# Next session: K3 jobs, contract first

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-16-next-session-k3-jobs.md and follow it, starting with section 4."

## 1. The project

AI DevKit, to be renamed MechFrame after K3 (decision 0034): website modules an agent copies into a site, around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`. Nothing is deployed. The owner's Vibrant Mindz site waits on these modules (decision 0029).

## 2. Rules that aren't in a CLAUDE.md

- **Landing needs the owner's OK for each PR:** once "CI result" is green and the bots have no open findings, `git push origin <sha>:refs/heads/main`, then delete the branch locally and on GitHub. CodeRabbit rate-limited: green CI plus Codex's first-push review is enough.
- **A PR branch behind `main`:** merge `main` into it and push normally; force-pushing is refused here.
- Commit with the no-reply address on `main`; stage by name; run `gitleaks git --pre-commit --staged` first.
- A kernel service is a seam: its contract first (`C:\DEV\_templates\feature-CONTRACT.md`), and the owner approves its goal and non-goals before code.
- Keep the DevKit name until the rename PR.

## 3. State (verified 2026-11-16, end of session)

- `main` at a1d0155 (#61). #58 to #61 landed this session; their branches are deleted.
- **#62** (`docs/handoff-k3-jobs`: `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md`, this file) is the only open PR.
- Last local full run: 1026 passed, 6 skipped, 27 xfailed, coverage 97.95%. CI passed on a1d0155. Nothing is half-done.

## 4. The job, in order

1. If #62 is open, ask the owner whether to land it once "CI result" is green; then `git switch main` and `git pull --ff-only`.
2. **K3 jobs:** write `dev plans/contracts/k3-jobs.md` and bring the owner its goal and non-goals. Inputs: SPEC 6 (`jobs.enqueue(name, payload, run_at)`, `@jobs.scheduled(cron)`), SPEC 11, `KICKOFF.md` K3 (lift from VybeSite `backend/app/worker.py`: `FOR UPDATE SKIP LOCKED`, the scheduler's lock, budget and retries), `docs/HANDOFF.md` Next 1. Then tests first, migration `kernel_0006`, the worker, mail moved onto jobs (retried by `MailError.retryable` and `retry_after`), unverified accounts removed after 7 days, and the gate's job that survives a worker restart. Update `docs/progress.json` in the same PR.
3. Then events, audit, notifications, moderation, public rendering and K3's gate; then the rename PR (decision 0034).

## 5. Questions for the owner (ask; don't decide)

- For jobs: does a site run the worker as its own Railway service (more cost, survives web restarts) or inside the web process?
- Decisions 0032 and 0033's own calls (`docs/HANDOFF.md`, Open questions): keep them?
- When to make the R2 test buckets for `test_storage_live.py`.
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, about 7 minutes, in the background, logged to the scratchpad.
- Git Bash collapses `\\` in heredocs and Write/Edit decode `\u`: write scripts with the Write tool, build such characters with `chr()`, run with `.venv/Scripts/python.exe -I`.
- Mutants: a scratchpad script swaps one string, runs the named tests and restores the file.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decisions 0032 to 0034; `dev plans/contracts/`; the bodies of #58 to #61.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0035, PR #63, migration `kernel_0006`.

## 8. Candidates for `knowledge/`

1. Railway's Hobby plan blocks outbound SMTP: use an HTTPS mail API there (`railway-deploy-playbook`).
2. Before moving wording or behavior, record a snapshot from the old code and hold old and new to it (`verify-real-pass`).
3. smtplib's `with` raises when QUIT fails after the server took the message: QUIT best effort, or a retry sends it twice.
4. botocore's `max_attempts` counts retries; `total_max_attempts` counts tries.
