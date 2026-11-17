# Next session: K3 events, contract first

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-17-next-session-k3-events.md and follow it, starting with section 4."

## 1. The project

AI DevKit (MechFrame after K3, decision 0034): website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`; nothing deployed. Vibrant Mindz waits on it (decision 0029).

## 2. Rules that aren't in a CLAUDE.md

- **Landing:** once "CI result" is green, the bots have no open findings and the owner says land it, check `git merge-base --is-ancestor origin/main <sha>` and **give the owner** `git -C C:\DEV\AI-DevKit push origin <sha>:refs/heads/main`: auto mode refuses it (memory note `landing-push-needs-owner`). Then delete the branch here and on GitHub.
- Commit with the no-reply address on `main`; stage by name; run `gitleaks git --pre-commit --staged` first.
- A kernel service is a seam: its contract first (`C:\DEV\_templates\feature-CONTRACT.md`); the owner approves the goal and non-goals before code.
- Keep the DevKit name until the rename PR.

## 3. State (verified 2026-11-17, end of session)

- `main` at 4a666e3 (#63, K3 jobs, landed). Its branch is deleted.
- **#64** (`docs/handoff-k3-events`: `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md`, this file) is the only open PR.
- Last local full run: 1223 passed, 7 skipped, 27 xfailed, coverage 98.08 %. CI passed on 4a666e3. Nothing is half-done.

## 4. The job, in order

1. If #64 is open, ask the owner whether to land it once "CI result" is green (they run the push); then `git switch main`, `git pull --ff-only`.
2. **K3 events:** write `dev plans/contracts/k3-events.md` and bring the owner its goal and non-goals. Inputs: SPEC 11 and 6, `docs/HANDOFF.md` Next 1. Build on `kernel/jobs.py` and `kernel/worker.py` (decision 0035): the dispatcher runs in that worker. `emit` likely takes `db` first, as `enqueue` does: say so in the contract. Then `remove_unverified` emits `auth.user.deleted`, and K3's gate test: an event delivered once to a handler that's safe to run twice. Update `docs/progress.json` in the PR.
3. Then audit, notifications, moderation, public rendering, K3's gate; then the rename PR (decision 0034).

## 5. Questions for the owner (ask; don't decide)

- Decision 0035's own calls, listed in `docs/HANDOFF.md`, Open questions: keep them?
- Decisions 0032 and 0033's own calls: keep them?
- When to make the R2 test buckets for `test_storage_live.py`.
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, about 10 minutes: run it with `run_in_background`, logged to the scratchpad (a shell `&` gives no notice).
- Tests run due jobs themselves (`Draining` in `kernel/tests/conftest.py`; the harness's `/api/_test/mail`): an event test will need the same.
- Shell and editing traps: `docs/HANDOFF.md`, Notes.
- Mutants: a scratchpad script swaps one string, runs the named tests and restores the file.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decision 0035; `dev plans/contracts/k3-jobs.md`; #63's body and threads.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0036, PR #65, migration `kernel_0008`.

## 8. Candidates for `knowledge/`

1. Auto mode refuses pushing a sha to `main`; hand the owner the landing command (`git-and-ci-traps`).
2. `UPDATE ... WHERE id IN (SELECT ... ORDER BY ... FOR UPDATE SKIP LOCKED LIMIT n) RETURNING` doesn't keep the subquery's order: claim one at a time where order matters.
3. Once mail moves onto a queue, drain the queue after each test request, or "nothing was sent" proves nothing (`verify-real-pass`).
4. `asyncio.run` waits for cancelled tasks however long they clean up: a worker process ends itself after a bounded drain.
5. On Windows, `signal.raise_signal` from a thread reaches the main thread's handler, so a `serve()` can be tested in process.
