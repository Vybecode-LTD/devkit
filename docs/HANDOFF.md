# Handoff

Overwritten every session. 2026-11-16, evening Eastern (2026-11-17 UTC; Claude Code, the owner's machine): K3 events (#65, decision 0036), contract first, one review fix in the PR, landed by this session under the owner's new grant. Then this page (#66).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3, in decision 0029's order:** storage (#58, 0032), email (#59, 0033), the kernel's mails as templates (#60), jobs (#63, 0035), and now **events** (#65, 0036; contract `dev plans/contracts/k3-events.md`):
  - `kernel.events`: `@events.payload(name, v=1)` declares a payload in the owner's `events.py`; `@events.on(event, "<id>.<name>")` declares a listener whose job delivers it; `events.emit(db, name, payload)` adds one job per listener to the caller's transaction. **The jobs table is the outbox:** no `kernel_event_outbox`, no dispatcher (SPEC 11 changed).
  - 8 tries with the jobs' backoff; a dead delivery is the dead-letter entry (K4's System page). A delivery waits while its module is off; a module `MODULES` leaves out gets none. Every listener and try sees one `event.id`: listeners MUST be safe to run twice.
  - The start checks module.json's `events.emits` / `listens` against `events.py`, owners, and listeners to undeclared kernel or installed-module events.
  - **The kernel emits** `auth.user.created`, `auth.user.verified` (sign-up's link, a reset that confirms the address, an email change's confirmation), `auth.user.deleted` (`kernel.remove_unverified`) and `kernel.settings.changed`. The other four in SPEC 11 come with their changes (moderation; K4's admin).
  - `python -m tools.event_schemas` writes `schema/events/*.v1.schema.json`.
- **The K3 gate's event test** is `test_an_event_reaches_its_listener_once_and_a_second_run_changes_nothing`; the job-restart one is `test_a_killed_worker_s_job_is_finished_by_the_next`.
- **Tests:** last local run 1279 passed, 7 skipped (5 live storage, 1 symlink, 1 SIGTERM on Linux only), 27 strict expected failures; coverage 98.12 %, `events.py` at 100 %; 23 of 23 mutants killed. CI passed on `main` at 161d0fa.
- **Pushing and merging are the agent's call in this project** (the owner, explicitly, 2026-11-17; `CLAUDE.md` Rules, under `C:\DEV\knowledge\owner.md`'s rule that it needs the owner's explicit statement). #65 landed by this session's own fast-forward push.

## Next

1. **K3 audit, contract first** (`C:\DEV\_templates\feature-CONTRACT.md`): `audit.record(actor, action, target, meta)` (SPEC 6), widened from auth's `auth_audit_event` (SPEC 14.10; `kernel/auth/audit.py`, which has `record` and `record_by_kernel`). Lift from VybeSite `services/staff_activity.py` and Basefra.me `app/audit/` (KICKOFF K3). Decide with the owner whether it's one table or auth's plus a kernel one, and the retention. `settings.save` has a `# K3: audit it` marker.
2. Then notifications, moderation (it emits `auth.user.suspended`), public rendering, and K3's gate; then **the rename PR** (decision 0034).
3. Then K4 (the System page reads dead jobs and deliveries), K5, the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Decision 0036's own calls: a listener's 300-second default timeout; `auth.user.verified` on an email change's confirmation as well as sign-up's link and a reset; no deliveries at all for a module `MODULES` leaves out. Keep them?
- Still open from earlier sessions: decision 0035's calls (listed in that record), 0032 and 0033's, when to make the R2 test buckets, and the desk steps (the `postgres` password; `Set-ExecutionPolicy` if wanted).
- `C:\DEV\knowledge` has `owner.md` uncommitted: this session's push-and-merge rule and an older Boston-time line. The owner commits it.

## Notes

- **Tests hear the kernel's events** through `kernel/tests/conftest.py`'s `heard` fixture (list it after the fixture that builds the app). In `test_events.py` the app's worker runs only its modules' jobs: with the kernel's, a test that moves the clock also runs mail other tests left queued.
- **Tests run due jobs themselves** (`Draining`, `/api/_test/mail`), as before.
- Git Bash: `cat > file` with nothing piped in waits for ever; write scripts with the Write tool. Heredocs collapse `\\`; Write/Edit decode `\u`. A subprocess on Windows needs `sys.executable`, not `.venv/Scripts/python.exe`.
- Working-tree files are CRLF (`autocrlf`); a byte-exact restore (mutants) reads and writes bytes.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
