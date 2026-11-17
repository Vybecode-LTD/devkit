---
feature: K3 events (kernel.events, delivered by the jobs worker)
status: approved
approved: 2026-11-17 (the owner: all four kernel events whose change exists now)
plan: dev plans/2026-11-17-next-session-k3-events.md (section 4, item 2); docs/HANDOFF.md, Next 1
pr: 65
---

# Contract: K3 events (`kernel.events`)

## 1. Goal

A module reacts to a change in the kernel or in another module without importing it. The one making the change calls `await events.emit(db, "auth.user.deleted", events.UserDeleted(user_id=...))` in the same transaction as the change, so the event exists exactly when the change committed. Afterwards, every module listening gets it in the worker, each on its own: retried when it fails, set aside on a dead-letter list after 8 failures, and held while that module is switched off (SPEC 11, 12). First use: when `kernel.remove_unverified` removes an account, every module listening to `auth.user.deleted` erases that person's data.

## 2. Interfaces

`kernel/backend/kernel/events.py`, public as `from kernel import events`.

```python
# the emitting module's events.py: the payload, declared once by its owner
@events.payload("blog.post.published", v=1)      # returns the class
class PostPublished(events.Payload):             # Pydantic: frozen, strict, extra fields refused
    post_id: uuid.UUID

# a listening module's events.py: the listener names its delivery job
@events.on("auth.user.deleted", "comments.forget_user", timeout=300)   # -> events.Listener
async def forget_user(ctx: jobs.Context, event: events.Event) -> None:
    gone = event.parse(events.UserDeleted)

async def emit(db: AsyncSession, name: str, payload: events.Payload) -> int   # deliveries queued

@dataclass(frozen=True)
class Event:   # id: uuid.UUID; name: str; v: int; emitted_at: datetime; payload: dict[str, Any]
    def parse(self, model: type[M]) -> M          # validates payload as JSON into any Pydantic model
```

- **Names** are `<module>.<entity>.<past-tense verb>` (SPEC 11, the manifest's pattern). An emitter declares only its own (`<id>.*`; the kernel `auth.*` and `kernel.*`), each once. module.json's `events.emits` lists exactly what its `events.py` declares, and `events.listens` exactly what its listeners hear. A listener's second argument is a job name of its own module (`<id>.<name>`, kernel.jobs), checked with the module's jobs. `create_app` and `create_worker` stop the start on any mismatch, on a listener to an `auth.*` or `kernel.*` event the kernel doesn't declare, and on one to an installed module's event that module doesn't declare. An event of a module that isn't installed may be listened to: an optional integration.
- **A listener reads its own view.** Modules don't import each other (SPEC 7), so a listener parses `event.payload` into the kernel's model (`events.UserDeleted`) or a model of its own holding the fields it needs. The version is `event.v`, not a payload field.
- **`emit`** refuses a name nobody declared (ValueError) and a payload that isn't that name's model (TypeError). It adds one job per listener to the caller's session, through `jobs.enqueue`: one per listener of the kernel and of each module the deploy's `MODULES` allows, on or switched off now. It returns how many; with no listener it writes nothing. The job's payload is the event: `{"id", "name", "v", "emitted_at", "payload"}`, JSON of at most 64 KiB (jobs' limit), never sealed (ids only).
- **Delivery** is that job: named by its listener, so its module is the listener's and it waits while that module is off (the worker already claims only the jobs of modules that are on). 8 tries (SPEC 11); backoff, `Retry`, `Abandon`, the lease and the timeout are the jobs' (decision 0035), so the 8th try comes about an hour after the first. Every listener and every try sees the same `event.id`: the key a listener uses to be safe to run twice.
- **Dead letters:** a delivery dead after 8 tries is a dead `kernel_job`, keeping its exception's type name, pruned after 30 days by `kernel.prune_jobs`. K4's System page lists them.
- **The kernel emits now:** `auth.user.created` (sign-up made an account), `auth.user.verified` (an address is confirmed: sign-up's link, a reset that confirms it, an email change's confirmation), `auth.user.deleted` (`kernel.remove_unverified`, for each account in its batch's transaction; later K2's account deletion), each `{user_id}`; and `kernel.settings.changed` (`settings.save`: `{module, version}`). SPEC 11's other four (`auth.user.role_changed`, `auth.user.suspended`, `kernel.module.enabled` and `disabled`) are declared by the PR that builds their change: moderation in K3, roles and module switches in K4.
- **Schemas:** `python -m tools.event_schemas` writes each declared payload as `schema/events/<name>.v<N>.schema.json` (SPEC 11, decision 0004); `--check` only reports.

## 3. Data

None: deliveries are `kernel_job` rows (migration `kernel_0006`). SPEC 11's `kernel_event_outbox` isn't made: the jobs table is the outbox, and a dead delivery is the dead-letter entry. No migration, so `kernel_0008` stays free.

## 4. Files

- New: `kernel/backend/kernel/events.py`; `kernel/tests/test_events.py`; `tools/event_schemas.py`, `tests/test_event_schemas.py`; four files in `schema/events/`; `docs/decisions/0036-kernel-events.md`.
- Changed: `kernel/__init__.py`; `modules.py` (`InstalledModule.payloads`, `.listeners`); `app.py` (`assemble` checks the events and installs them; the listeners join the jobs); `harness/registry.py` (`events.py`, found by type); `auth/sign_up.py`, `auth/resets.py`, `auth/email_change.py`, `auth/unverified.py`, `settings.py` (emits); `modules/_template/backend/my_module/events.py` (an example listener: its module.json already listens to `auth.user.deleted`); `SPEC.md` (6, 11, change log); `CLAUDE.md`/`AGENTS.md` (Commands); `docs/HANDOFF.md`, `docs/progress.json`.

## 5. Conventions this follows

`kernel/backend/kernel/jobs.py` (names by owner, found by type in a fixed file, checked against module.json at the start), `email.install`, decision 0035 (at least once; tests drain due jobs). Skill `module-contract-lint`; memory notes `race-tests-that-really-race`, `rollback-expires-orm-rows`.

## 6. Non-goals

- Not exactly once: at least once for each listener. A listener MUST be safe to run twice.
- No event log of its own: an event nobody listens to leaves no row, and nothing replays past events to a listener added later (one that needs history fills it in itself).
- No order between events or between listeners.
- No wildcard listener (the outgoing-webhooks module's, later), no version negotiation (every payload is v1), no sealed payloads.
- No System page, requeueing or admin routes for dead letters (K4).
- Not SPEC 11's other four kernel events, and no change to how jobs run.

## 7. Acceptance

- `test_events.py`: a rolled-back emit delivers nothing; a committed one reaches each listener once, with the same id, name, v and payload; a failing listener retries alone while the other is done; dead after 8 tries; an off module's delivery waits and runs once it's back on; a module `MODULES` leaves out gets none; the payload and size refusals; every start refusal above; discovery from `events.py`.
- **K3 gate:** `test_an_event_reaches_its_listener_once_and_a_second_run_changes_nothing`: `remove_unverified` removes an account, a test module's listener erases its rows; the same delivery then runs again (the listener commits, then its try fails) and leaves the same rows, the listener having seen one `event.id` both times.
- Each kernel emit: once, in its change's transaction; a sign-up for an address that has an account, a second verification click and a re-checked account in the sweep emit nothing.
- `test_event_schemas.py` fails when a schema file is stale. The full suite stays green, coverage at 95 % or more, `events.py` at 100 %.

## 8. Open questions

None. On 2026-11-17 the owner approved the goal and non-goals as written, with SPEC 6 and 11's changes (`emit` takes `db` first and the payload model; `@events.on(event, name)` names its listener's job; no `kernel_event_outbox`, the jobs table is the outbox; decision 0036), and chose to emit all four kernel events whose change exists now.

## Changes after approval

- 2026-11-17: `kernel.events` also exposes `build`, `install`, `Catalog`, `declaration`, `check_name`, `KERNEL_PAYLOADS` and `TRIES`, for `assemble`, the harness, the schema tool and the tests; the harness's `module_events` finds a module's payloads (only the classes its `events.py` declares itself, not ones it imports) and listeners. Until an app is built, `emit` knows the kernel's events, heard by no one, so kernel code run outside an app (a test's sweep) emits without error. The tests hear the kernel's events through `kernel/tests/conftest.py`'s `heard` fixture. `tools.event_schemas` also removes a schema file no event declares any more. The template's `events.py` holds a working listener, since its module.json already listened to `auth.user.deleted`.
