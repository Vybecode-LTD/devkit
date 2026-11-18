# K3's gate: the evidence (2026-11-17)

The gate (KICKOFF K3; `docs/progress.json`): tests for each service, an event delivered once to a handler safe to run twice, and a job surviving a worker restart. Checked on `main` at `e009a13`, on the owner's machine, against the local Postgres 16. The owner decided the same night that retention and the AI client, both `later`, are outside the gate: their tests come with them.

## The run

`TEST_DATABASE_URL=… DEVKIT_REQUIRE_DB=1 python -m pytest --cov=kernel`: **1,690 passed, 8 skipped, 27 xfailed** in 13 min 55 s; coverage **98.50 %**. The 8 skips: the 5 live R2 tests (no buckets yet), `test_sigterm_drains_and_exits_0` (Windows can't send a child SIGTERM; CI runs it on Linux), and two symlink tests Windows can't make. The 27 strict expected failures are K2 steps 9 to 11. On Linux, main's last push run at `e009a13` (run 44223648330) passed both Python jobs, 3.12 and 3.13, the SIGTERM test included; its Web job failed only on npm audit's picomatch advisory.

## Each service

| Service | PR, decision | Tests | Coverage |
| --- | --- | --- | --- |
| Storage | #58, 0032 | `kernel/tests/test_storage.py` (30, moto); `test_storage_live.py` (5, skipped without R2) | `storage.py` 100 % |
| Email | #59, 0033 | `test_email.py` (11), `test_email_send.py` (16), `test_email_queue.py` (11), `test_mail_adapters.py` (26) | `email.py`, `mail_adapters.py` 100 % |
| The kernel's mails | #60, 0033 | `kernel/tests/auth/test_mail_wording.py` and each flow's own tests | `auth/mails.py` 100 % |
| Jobs | #63, 0035 | `test_jobs.py` (33), `test_worker.py` (62), `test_cron.py` (12) | `jobs.py`, `worker.py`, `cron.py` 100 % |
| Events | #65, 0036 | `test_events.py` (33), `tests/test_event_schemas.py` (5) | `events.py` 100 % |
| Audit | #67, 0037 | `test_audit.py` (36) | `audit.py` 100 % |
| Notifications | #69, 0038 | `test_notifications.py` (25) | `notifications.py` 100 % |
| Moderation | #71, 0039 | `test_moderation.py` (68) | `moderation.py` 100 % |
| Public rendering | #73, 0041 | `test_server_copy.py` (57), `test_shell.py` (32) | `server_copy.py`, `shell.py` 100 % |

## The two named tests

- **An event delivered once to a handler safe to run twice:** `kernel/tests/test_events.py::test_an_event_reaches_its_listener_once_and_a_second_run_changes_nothing`. One `auth.user.deleted` gives one delivery; its first try commits its work and then fails, as a worker dying before it writes the outcome would; the second try, with the same event id, changes nothing more. Also `test_a_committed_event_reaches_each_listener_once_with_one_id` and `test_a_rolled_back_emit_delivers_nothing`.
- **A job surviving a worker restart:** `kernel/tests/test_worker.py::test_a_killed_worker_s_job_is_finished_by_the_next`. A worker in its own process (`kernel/tests/jobs_child.py`) starts the job and is killed mid-try; while its lease is live nobody takes the job, and once it lapses the next worker runs it as try 2 and marks it done. Also the lease tests beside it, and `test_sigterm_drains_and_exits_0` (a stopped worker drains its job and exits 0), which runs in CI on Linux.

## The contract lint on the kernel (`module-contract-lint`)

| Area | Result | Evidence |
| --- | --- | --- |
| Manifest | pass | `python -m tools.validate_schemas`: 17 files, 0 problems |
| Layout | not applicable | the kernel isn't a module; its layout is SPEC 5's |
| Routes declare access | pass | `kernel/tests/test_app.py` (`undeclared(app) == []`, the harness's too); the 50 `/api` routes listed: admin ones only under `/api/kernel/admin` and `/api/auth/admin`, list reads paged (`cursor`, `limit`), the GET unsubscribe changes nothing |
| Boundaries | pass | no import of `modules` or `harness` from `kernel/backend` |
| Data and security | pass | bodies are strict Pydantic (`extra="forbid"`); outbound calls have timeouts (SMTP, Resend 10 s, R2 5 s and 60 s, the breach lookup) |
| Front end | pass | no colour literals in `kernel/web`; `npm run lint`, `typecheck`, `npm test` (7) pass |
| Quality gate | pass | ruff, black (211 files), mypy strict (143 files), coverage above |
| Secrets and dependencies | pass | gitleaks over 134 commits: none; pip-audit: none; the brand check: clean |
| npm audit | allowed | only GHSA-fc5q-39xc-vjpf (picomatch, no fix), now on the expiring allowlist the owner adopted (#75, decision 0015) |
