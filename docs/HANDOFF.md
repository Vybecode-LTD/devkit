# Handoff

Overwritten every session. 2026-11-16 to 17, overnight (Claude Code, the owner's machine): K3 jobs (#63, decision 0035), contract first, then three rounds of review fixes in the PR. Then this page (#64).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3, in decision 0029's order:** storage (#58, 0032), email (#59, 0033), the kernel's mails as templates (#60), and now **jobs** (#63, 0035; contract `dev plans/contracts/k3-jobs.md`):
  - `kernel.jobs`: `@jobs.handler` and `@jobs.scheduled(cron, name)` in a module's `jobs.py`; `jobs.enqueue(db, name, payload, run_at=, key=, sealed=)` in the caller's transaction. At least once: a handler MUST be safe to run twice.
  - `kernel.worker`: `SKIP LOCKED` claims under a 60 s lease renewed every 20 s, outcomes fenced by the try number, backoff to an hour, a scheduler under an advisory lock. **In the web process by default** (`JOBS_IN_WEB`, the owner's choice); a site with heavy jobs runs `serve(create_worker(...))` as its own service (Vibrant Mindz will, for ffmpeg; `python -m harness.worker` here).
  - **Mail is on the queue, sealed:** every kernel mail is `email.queue_message` before its route's commit; `BackgroundTasks` is gone. Retries follow `MailError.retryable`.
  - `kernel.remove_unverified` (hourly): unverified accounts 7 days after **their address was set** (`auth_user.email_set_at`, migration `kernel_0007`; an email change's undo restarts the clock, the owner's choice), staff never. `kernel.prune_jobs` (daily).
- **The K3 gate's "job survives a worker restart"** is `test_a_killed_worker_s_job_is_finished_by_the_next` (a killed child process). Still to come for the gate: an event delivered once to a handler that's safe to run twice.
- **Tests:** last local run 1223 passed, 7 skipped (5 live storage, 1 symlink, 1 SIGTERM on Linux only), 27 strict expected failures; coverage 98.08 %, the jobs files at 100 %. CI passed on `main` at 4a666e3.
- **GitHub:** public `Vybecode-LTD/devkit`. A PR lands by fast-forwarding `main` once "CI result" is green, with the owner's OK; **the owner runs that push** (auto mode refuses it; memory note `landing-push-needs-owner`).

## Next

1. **K3 events, contract first** (SPEC 11; `C:\DEV\_templates\feature-CONTRACT.md`): `events.emit(db, name, payload)` writing `kernel_event_outbox` in the caller's transaction, the dispatcher in this worker (a kernel job), handlers by `@events.on(name)` found in `events.py`, retries with backoff and a dead-letter list after 8 failures, a switched-off module's handlers waiting. Then `remove_unverified` emits `auth.user.deleted` (it has no event yet), and K3's gate test: an event delivered once to a handler that's safe to run twice.
2. Then audit, notifications, moderation, public rendering, and K3's gate; then **the rename PR** (decision 0034).
3. Then K4, K5 (the site template's worker service and Dockerfile), the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Decision 0035's own calls: 5 tries for a handler and for mail, 1 for a scheduled job; backoff from 30 s to an hour; a 60 s lease; 1 s polling; 4 at once; a 20 s drain; 64 KiB payloads; done jobs kept 7 days and dead ones 30; missed slots caught up for 7 days; the watchdog at 2 minutes; removal hourly at :17, pruning at 03:41 UTC. Keep them?
- Decisions 0032 and 0033's own calls (storage links of 5 minutes unless asked, 6 hours at most; `get`'s 32 MiB; `string.Template`; Resend's 10 s and SMTP's 15 s timeouts). Keep them?
- When to make the R2 test buckets for `test_storage_live.py`: before the site's step 2.
- Desk steps: reset the Postgres `postgres` password (the owner types it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if wanted.

## Notes

- **Tests run due jobs themselves.** No test app runs a worker (`JOBS_IN_WEB=false` in `conftest.py`); `kernel/tests/conftest.py`'s `Draining` transport runs them after each answer (`Client(app, drain=False)` for a test that counts queries or has no database), the harness's `GET /api/_test/mail` runs them first, and `/reset` forgets queued mail. `Worker.run_due` runs one job at a time, oldest first, so mail arrives in order.
- **Each module's `jobs.py`** is found by type (`jobs.Job`); a scheduled job must match module.json's `jobs` or the start stops. `modules/_template/backend/my_module/jobs.py` has the example.
- **Updating a PR branch behind `main`:** merge `main` in and push normally; force-pushing is refused.
- **Every PR that changes a step's status updates `docs/progress.json`** and runs `python -m tools.progress`.
- Git Bash collapses `\\` in heredocs and runs backticks in double quotes; Write/Edit decode `\u`: write scripts with the Write tool and build such characters with `chr()`.
- Race and lock-order tests must really race; never hand an ORM row past the route (memory notes).

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
