---
feature: K3 audit (kernel.audit, widened from auth's audit log)
status: approved
approved: 2026-11-17 (the owner: as recommended, all four answers)
plan: dev plans/2026-11-17-next-session-k3-audit.md (section 4, item 2); docs/HANDOFF.md, Next 1
pr: 67 (predicted)
---

# Contract: K3 audit (`kernel.audit`)

## 1. Goal

Any module, and the kernel, records who did what to what ("Ana changed Ben's roles", "a moderator hid comment 42", "the blog's settings were saved") with one call in the same transaction as the change: `audit.record(db, "kernel.settings_saved", actor=user.id, target=("kernel.settings", "blog"))`. The entry exists exactly when the change committed, and no route can change or remove it. Staff holding `auth.audit.read` read the whole log through one API, newest first, filtered by person, action, target and time; each person reads their own security activity. Entries go after a year by default. First uses: auth's existing rows, now written through it, and `settings.save` (its `# K3: audit it` marker).

## 2. Interfaces

`kernel/backend/kernel/audit.py`, public as `from kernel import audit`.

```python
def record(
    db: AsyncSession,
    action: str,                       # "<owner>.<name>": "kernel.settings_saved", "blog.post_deleted"
    *,
    actor: uuid.UUID | None,           # required: who did it; None is the kernel on its own (a job)
    target: tuple[str, str | int | uuid.UUID] | None = None,   # ("blog.post", 42), ("auth.user", uid)
    subject: uuid.UUID | None = None,  # the person it concerns: their activity list, account deletion
    result: str = "success",           # auth's: success, failure, refused, waiting, taken
    details: Mapping[str, Any] | None = None,
    request: Request | None = None,    # given: the client's address and browser are kept
) -> None
```

- **Adds one row to the caller's session.** Nothing is awaited or committed: the caller's commit writes it with the change, and its rollback drops both. (Synchronous, as auth's is today.)
- **`action`** is `<owner>.<name>`, lowercase `[a-z0-9_]` parts joined by dots, at most 64 characters. The owner is `auth`, `kernel` or an installed module's id (`create_app` installs the list, as it does for events); a module writes only its own `<id>.*`. The kernel's own actions are a closed set, `audit.KERNEL_ACTIONS`, so a typo is a refusal (VybeSite's rule). Anything else raises ValueError.
- **`target`** is `(kind, id)`: the kind `<owner>.<entity>`, the id kept as text; each at most 64 characters. **`result`**: lowercase, at most 16.
- **`details`** holds ids, names, counts and flags, never a secret, a code or an address: a JSON object of at most 4 KiB, values `str`, `int`, `float`, `bool`, `None` and lists or objects of them (a UUID, datetime or enum becomes a string). It refuses a string holding `@` (VybeSite's rule) and a key naming a secret (`password`, `secret`, `token`, `code`).
- **`request`**, when given, keeps the client's network (`client_address`, as INET) and the first 300 characters of its user agent.
- **Auth's helpers stay:** `kernel.auth.audit.record(db, request, action, result, *, actor, subject, details)` and `record_by_kernel` become thin wrappers over `audit.record`, so their call sites don't change.

**Reading** (both take `?cursor=&limit=` and answer `{"items": [...], "next_cursor": <cursor> | null}`, SPEC 7's list shape, newest first, keyset on `(at, id)`; `limit` 1 to 100, default 50; 422 on a bad filter):

- `GET /api/kernel/audit` (`auth.audit.read`): filters `actor`, `subject`, `action` (exact, or a prefix ending in `.` such as `blog.`), `target_type` with `target_id`, `since`, `until`, `cursor`. Each item: `{id, at, action, result, actor_id, subject_id, target: {type, id} | null, ip, user_agent, details}`. 401 signed out, 403 without the permission.
- `GET /api/auth/activity` (signed in): the person's own security activity, entries whose subject is them and whose action is `auth.*`. Each item as above, but `by_you: bool` replaces `actor_id`, so it never names a staff member.

**Pruning:** `kernel.prune_audit`, scheduled daily (`@jobs.scheduled`, as `kernel.prune_jobs`), deletes entries older than `AUDIT_KEEP_DAYS` (`KernelConfig`, default 365, at least 30) in batches of 1,000.

**Append-only in the database:** a trigger refuses every UPDATE, and every DELETE unless the transaction set `kernel.audit_prune` (`SET LOCAL`), which only `kernel.prune_audit` does; a second refuses every TRUNCATE.

## 3. Data

Migration `kernel/migrations/0008_audit.py` (`kernel_0008`) renames `auth_audit_event` to `kernel_audit_event`, keeping its rows, sequence and indexes (renamed to match), and adds:

| Table | Column | Type | Null | Default / FK / index |
|---|---|---|---|---|
| `kernel_audit_event` | `target_type` | `varchar(64)` | yes | index `(target_type, target_id, at)` |
| | `target_id` | `varchar(64)` | yes | (in that index) |
| | `actor_id` (existing) | `uuid` | yes | new index `(actor_id, at)` |

The rest stays as 14.11 has it: `id` bigint identity, `at`, `subject_id` (index `(subject_id, at)`), `action` 64, `result` 16, `ip` INET, `user_agent` 300, `details` JSONB; index `(at)`. No foreign keys: ids stay plain, so a deleted account's history stays, pseudonymous (14.7). Plus the trigger and its function. The downgrade drops the trigger, the indexes and the two columns, then renames the table back.

## 4. Files

- New: `kernel/backend/kernel/audit.py`; `kernel/migrations/0008_audit.py`; `kernel/tests/test_audit.py`; `docs/decisions/0037-kernel-audit.md`.
- Changed: `kernel/__init__.py` (`audit`); `models.py` (the model moves here, `auth/models.py` re-exports `AuditEvent`); `auth/audit.py` (wrappers); `settings.py` (records `kernel.settings_saved`, `details` `{version, changed: [field names]}`, never values); `config.py` (`audit_keep_days`); `app.py` (installs the owners, the prune job, the routes); `routes.py` (`/audit`); `auth/routes.py` (`/activity`); `tests/test_migrations.py`; `docs/contracts/auth-api.md`; `SPEC.md` (6, 14.10, 14.11, change log); `.env.example` if it lists kernel variables; `CLAUDE.md`/`AGENTS.md`; `docs/HANDOFF.md`, `docs/progress.json`, `docs/PROGRESS.md`.

## 5. Conventions this follows

`kernel/backend/kernel/events.py` (owners installed by `assemble`), `jobs.py`'s `kernel.prune_jobs` (batched pruning), `auth/audit.py` (the row as it is). Ported, not copied: VybeSite `services/staff_activity.py` (a closed action set, no address in details, rows only ever added) and Basefra.me `app/audit/` (filters, newest first). Skills `alembic-multi-module-migrations`, `module-contract-lint`; memory note `rollback-expires-orm-rows`.

## 6. Non-goals

- Not a version store: an entry holds ids and what changed, not whole objects before and after. Restoring an earlier state reads the owning module's own history (settings' `kernel_setting_version`; the site's featured slots, whose plan says "the audit log can restore", keep theirs).
- Not tamper-proof against the database's owner: no hash chain, signing or copy kept elsewhere. Append-only holds against the app, not a superuser.
- Not an event: recording emits nothing. A change that needs both calls `audit.record` and `events.emit`.
- Reads aren't recorded, the audit log's own included.
- No pages: K4 builds the Audit log page and the account page's activity list on these two routes. No export and no search inside `details`.
- Not the general retention service (K3's later "Retention" step), which takes over the pruning when it lands.
- No scrubbing of a deleted person's address and browser from their entries: K2 step 11 (deletion) decides that, through the prune job's switch.
- No entries for changes that don't exist yet: role changes, suspensions and module switches record theirs when they're built (moderation in K3, the rest in K4); an API key as actor comes with K2 step 10.

## 7. Acceptance

- `kernel/tests/test_audit.py`: a rolled-back change leaves no entry and a committed one exactly one, every field as given; each refusal above (owner, kernel action, name, target, an address, a secret key, a value JSON can't hold, over 4 KiB); with a request the address and browser are kept, without it neither; the database refuses an UPDATE, and a DELETE outside the prune job; `kernel.prune_audit` removes only entries past `AUDIT_KEEP_DAYS`, across batches.
- The two routes: access (401, 403), each filter, newest first, pages that neither repeat nor skip; `/activity` shows only the person's own `auth.*` entries, with `by_you`.
- `settings.save` writes one `kernel.settings_saved` entry when something changed (field names, no values) and none when nothing did.
- `tests/test_migrations.py`: the round trip keeps auth's rows across 0008's upgrade and downgrade. Every existing auth audit test passes unchanged.
- The full suite green, coverage at 95 % or more, `audit.py` at 100 %; mutants on the refusals, the trigger and the prune cutoff, all killed.

## 8. Open questions

None. On 2026-11-17 the owner approved the goal and non-goals as written, with the four answers recommended: (1) one table, auth's renamed `kernel_audit_event`, every module writing there; (2) `auth.audit.read` (admins by default) reads everything, IP addresses included, and each person their own `auth.*` entries; moderators get a narrower view when moderation is built; (3) one year for every entry, `AUDIT_KEEP_DAYS` (at least 30) for a site that wants other; (4) the append-only trigger, now.

## Changes after approval

- 2026-11-17, review of #67 (CodeRabbit and Codex): both routes use SPEC 7's list names, `?cursor=` in and `next_cursor` out, not `before` and `next`; a cursor past the last datetime or Postgres's bigint is a 422; `record` refuses a NUL character (Postgres's JSONB and text refuse it at the flush) and an address as a details key; a second trigger refuses TRUNCATE, which runs no row trigger.

- 2026-11-17: the staff's log is `GET /api/kernel/admin/audit`, not `/api/kernel/audit`: under `/api/<id>/admin` the admin gate applies (a staff role and a confirmed second factor, `docs/contracts/auth-api.md`, Staff), as for every staff route. `kernel.audit` also exposes `install`, `keep`, `check_action`, `read`, `item`, `own_item`, `cursor_of`, `PRUNE`, `PRUNE_SWITCH`, `BATCH`, `NAME`, `PREFIX` and `MAX_DETAILS`, for `assemble`, the routes and the tests. A bad cursor answers 422 `kernel.invalid_request` on both routes. `kernel.models` imports auth's models last, since auth's re-export the audit log's model from it.
