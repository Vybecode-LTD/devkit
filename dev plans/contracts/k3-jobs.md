---
feature: K3 jobs (kernel.jobs, the worker and the scheduler)
status: approved
approved: 2026-11-16 (the owner: the worker runs in the web process by default, Vibrant Mindz runs its own)
plan: dev plans/2026-11-16-next-session-k3-jobs.md (section 4, item 2); docs/HANDOFF.md, Next 1
pr: 63
---

# Contract: K3 jobs (`kernel.jobs`)

## 1. Goal

A module or the kernel hands work to a worker instead of doing it in the request: `await jobs.enqueue(db, "discography.process_track", {"track_id": ...})` in the same transaction as the change it follows, so the job exists exactly when the change committed. Scheduled work runs from a cron line. The worker runs each job at least once, retries a failure with backoff, and loses nothing when it's restarted or killed mid-job. The kernel's 19 mails move onto it, so a provider's hiccup is retried and a crash doesn't drop a sign-in code. Unverified accounts are removed after 7 days (SPEC 14.7).

## 2. Interfaces

`kernel/backend/kernel/jobs.py`, public as `from kernel import jobs`; `kernel/backend/kernel/worker.py` for the site.

```python
@jobs.handler("blog.send_digest", tries=5, timeout=300)         # -> jobs.Job
async def send_digest(ctx: jobs.Context, payload: dict[str, Any]) -> None: ...

@jobs.scheduled("*/5 * * * *", "blog.publish_scheduled", timeout=300)   # -> jobs.Job; no payload
async def publish_scheduled(ctx: jobs.Context) -> None: ...

async def enqueue(db: AsyncSession, name: str, payload: Mapping[str, Any] | None = None, *,
                  run_at: datetime | None = None, key: str | None = None,
                  sealed: bool = False) -> uuid.UUID | None     # None: a live job has this key
class Retry(Exception)      # Retry(after: float | None = None): try again later; counts as a try
class Abandon(Exception)    # stop now: the job is dead without more tries
class Context               # job_id, name, try_number (from 1), sessions() -> AsyncSession context

def create_worker(*, modules=(), config=None, database=None, mailer=None, emails=None) -> Worker
class Worker: async def run(stop: asyncio.Event) -> None;  async def run_due() -> int   # tests, harness
```

- **Names** are `<owner>.<name>` (the module's id or `kernel`; `<name>` is `[a-z][a-z0-9_]*`), as email templates are. A module's jobs are every `jobs.Job` in `backend/<id_>/jobs.py`, found by the harness and put on `InstalledModule(jobs=...)`. `create_app` and `create_worker` stop the start on a name of another owner, a duplicate, a bad cron line, or a scheduled job missing from the manifest's `jobs` (`{name, schedule}`, unprefixed) or listed there differently.
- **Cron** (`kernel/backend/kernel/cron.py`, no dependency): five fields, UTC; `*`, numbers, `a-b`, lists and `/n` steps; no names, seconds, `L`, `W`, `#` or `?`. When both day fields are restricted, either matches, as cron does.
- **Payload:** a JSON object of at most 64 KiB, holding ids rather than rows. `sealed=True` stores it through `crypto.seal`; a sealed payload is wiped when its job ends. `key` makes the enqueue a no-op while a job of that name and key is queued or running.
- **The worker** claims due jobs every `JOBS_POLL_SECONDS` (1), up to `JOBS_CONCURRENCY` (4) at once, with `FOR UPDATE SKIP LOCKED`, only for handlers it has and modules that are on (an off module's jobs wait, SPEC 12; so does a name an older worker doesn't know yet). A claim sets a 60 s lease, renewed every 20 s while the handler runs; a job whose lease lapsed (its worker died) is claimed again. Each try is cut off at the handler's `timeout`.
- **Outcomes:** returning marks it done. `Retry` or any other exception queues it again after 30 s, doubling to at most 1 h (±10 %, or `Retry.after`), until its `tries` are used, then dead. `Abandon` is dead at once. The row keeps the exception's type name, never a value or the payload.
- **Stopping:** SIGTERM or SIGINT (with VybeSite's Windows fallback) stops claiming, gives running jobs `JOBS_DRAIN_SECONDS` (20), then exits 0; what's still running is left to its lease. A watchdog thread ends the process with status 124 if the event loop stops answering for 2 minutes, so the host starts a fresh worker.
- **Scheduler:** once a minute, under a transaction advisory lock (one scheduler across every worker), each scheduled job of an on module whose latest slot is newer than its `last_slot` is enqueued once (`key` = the slot) and `last_slot` moves to it. Missed slots collapse into one run; none older than 7 days is caught up; a new scheduled job starts from now.
- **Kernel jobs:** `kernel.send_mail`, `kernel.prune_jobs` (daily: done jobs after 7 days, dead after 30) and `kernel.remove_unverified` (hourly: accounts never verified, created over 7 days ago, `active`, holding no role but `member`, so staff are never removed; in batches, each account locked first and re-checked; their sessions, tokens and factors go by cascade; one audit row each).
- **Mail:** `email.queue(db, template, to, context)` renders now and enqueues `kernel.send_mail` sealed. `MailError.retryable` becomes `Retry(retry_after)`, a refusal `Abandon`. Every kernel mail is queued before its route's commit (inside the response-time floor where there is one) instead of `BackgroundTasks`, so a mail goes out only if its change committed. `email.send` stays for sending now.

**Config:** `JOBS_CONCURRENCY` (1 to 32), `JOBS_POLL_SECONDS` (0.1 to 60), `JOBS_DRAIN_SECONDS`, and `JOBS_IN_WEB` (true: `create_app`'s lifespan runs a worker in the web process; a site that runs `python -m app.worker` as its own service, as Vibrant Mindz will for ffmpeg, sets it false on the web service). Every time the jobs compare comes from `kernel.clock`, so tests move it. `Worker.run_due()` runs every due job and then waits for those other workers hold, so a test or the harness reads a settled queue.

## 3. Data

Migration `kernel/migrations/0006_jobs.py` (`kernel_0006`).

| Table | Column | Type | Null | Default / FK / index |
|---|---|---|---|---|
| `kernel_job` | `id` | uuid | no | PK |
| | `name` | varchar(130) | no | |
| | `module` | varchar(40) | no | `kernel` or the module's id |
| | `payload` | text | yes | JSON, or sealed; null once a sealed job ends |
| | `sealed` | boolean | no | false |
| | `key` | varchar(200) | yes | unique (`name`, `key`) where `state` in (queued, running) |
| | `state` | varchar(8) | no | `queued`; check in (queued, running, done, dead) |
| | `run_at` | timestamptz | no | index where `state = 'queued'` |
| | `tries` | integer | no | 0 |
| | `locked_until` | timestamptz | yes | index where `state = 'running'` |
| | `last_error` | varchar(200) | yes | the exception's type name |
| | `created_at`, `finished_at` | timestamptz | no / yes | now() / — |
| `kernel_job_schedule` | `name` | varchar(130) | no | PK |
| | `last_slot` | timestamptz | no | |

## 4. Files

- New: `kernel/backend/kernel/jobs.py`, `cron.py`, `worker.py`; `kernel/migrations/0006_jobs.py`; `harness/worker.py` (`python -m harness.worker`); `kernel/tests/test_cron.py`, `test_jobs.py`, `test_worker.py`, `auth/test_remove_unverified.py`; `docs/decisions/0035-kernel-jobs.md`.
- Changed: `email.py` (`queue`, `kernel.send_mail`); the nine auth route files; `app.py`, `modules.py` (`jobs`), `config.py`, `__init__.py`; `harness/registry.py`, `harness/testing.py` (`POST /api/_test/jobs/run`, and `GET /api/_test/mail` runs due jobs first, so "nothing more was sent" still proves something); the auth tests that read sent mail; `modules/_template` (an example `jobs.py`); `.env.example`; `SPEC.md` (6, 14.7, change log); `CLAUDE.md`/`AGENTS.md` (Commands); `docs/TESTING.md`, `docs/HANDOFF.md`, `docs/progress.json`.

## 5. Conventions this follows

`kernel/backend/kernel/email.py` (names by owner, declared per module, checked at build), `harness/registry.py` (fixed names), `accounts.lock` (the account row first), `crypto.seal`, `kernel.clock`. Lifted from VybeSite `backend/app/worker.py` (the stop request, signals, the watchdog) and Basefra.me `backend/app/scheduler/service.py` (claiming with `SKIP LOCKED` and a lease); the brand check runs on them. Skill `alembic-multi-module-migrations`; memory notes `race-tests-that-really-race`, `rollback-expires-orm-rows`.

## 6. Non-goals

- Not exactly once: at least once. A handler MUST be safe to run twice; a mail can go twice if the worker dies between the provider's OK and the commit.
- No LISTEN/NOTIFY: the worker polls, so a mail leaves within about a second of the answer.
- No priorities, per-job rate limits, chains, cancelling from code, or time zones in cron.
- No admin routes or System page (K4 reads these tables), no Dockerfile or Railway service (K5's site template), no ffmpeg (discography's step).
- No events dispatcher (the next PR, in this worker), so a removed unverified account emits no `auth.user.deleted` yet; and no reminder mail before removal.

## 7. Acceptance

- `test_cron.py`: each field form, the refusals, the two-day-field rule, the latest slot at month and year ends.
- `test_jobs.py`: a rolled-back enqueue leaves no job; `key` dedupes only while live; payload limits; a sealed payload isn't readable in the table and is wiped at the end; the build refusals; discovery from `jobs.py`.
- `test_worker.py`: due but not future jobs run; backoff, `Retry.after`, `Abandon`, dead after `tries`, the timeout; two workers never run one job (really racing); an off module's job waits; the lease renews on a long job; **a worker killed mid-job (a subprocess, `kill`) and its job finished by the next one**, the K3 gate; SIGTERM drains and exits 0; the watchdog; one run per slot across two schedulers; missed slots collapse; pruning.
- Mail: every kernel mail is queued; a rolled-back change sends nothing; a retryable `MailError` waits `retry_after`; a refusal is dead at once.
- `test_remove_unverified.py`: removed at 7 days and not before; verified, staff and suspended accounts never; a verification racing the sweep wins; the cascade and the audit row.
- The contract suite stays green through the harness's drain; the full suite stays green, coverage stays at 95 % or more, and the new files are at 100 %.

## 8. Open questions

None. On 2026-11-16 the owner approved the goal and non-goals as written, which includes SPEC 6's change (`enqueue` takes `db` first, so the job commits or rolls back with the caller's change, plus `key`, `sealed` and `@jobs.handler`; decision 0035), and chose where the worker runs: in the web process by default, its own service for Vibrant Mindz.

## Changes after approval

- 2026-11-16: `email.queue_message(db, to, subject, text, html)` sits beside `email.queue`, for the kernel's auth mails, which render through `kernel.auth.mails`; `kernel.auth.routes.new_device_mail` replaces `_mail_new_device`, and `BackgroundTasks` is gone from the kernel. `kernel.auth.audit.record_by_kernel` writes a job's audit rows, which have no request. `kernel_job` has a fourth partial index, on `finished_at`, for pruning. `kernel.worker` also exposes `Worker`, `Worker.tick()`, `serve`, `Watchdog` and `stop_on_signals`, for tests and a site's worker file. `docs/TESTING.md` doesn't exist in this repo: the test notes are in decision 0035 and the handoff. `POST /api/_test/jobs/run` answers 204, as `docs/contracts/auth-api.md` already said.
