---
feature: K3 moderation (kernel.moderation: reports, the queue, filters, actions)
status: approved
approved: 2026-11-17 (the owner: "Approve as recommended", all five answers)
plan: dev plans/2026-11-17-next-session-k3-moderation.md (section 4, item 2); docs/HANDOFF.md, Next 1
pr: 71 (predicted)
---

# Contract: K3 moderation (`kernel.moderation`)

## 1. Goal

A signed-in person with a verified address reports anything a module lets them report (a comment, a message, a profile) through one kernel route. Staff holding `kernel.moderation.act` work one queue: one case per reported thing, holding every report on it, the text as it was when reported, and its author. From a case they dismiss it, have the owning module hide or delete the thing, or time the author out of posting; an admin can also ban, which suspends the account, signs it out everywhere and emits `auth.user.suspended`. Modules screen new text through word and link filters that hold it for review and never drop it. Every action is in the audit log, moderators read their own slice of that log, and the person acted on is told why, never by whom.

## 2. Interfaces

`kernel/backend/kernel/moderation.py`, public as `from kernel import moderation`.

**A module declares what can be reported** in its `moderation.py`, which the kernel finds as it finds `events.py`; the start refuses a kind its module doesn't own:

```python
@moderation.kind("comments.comment", actions=("hide", "delete"))
class Comment(moderation.Kind):
    async def describe(self, db: AsyncSession, id: str) -> moderation.Item | None: ...  # None: no such thing
    async def apply(self, db: AsyncSession, id: str, action: str) -> None: ...          # in the caller's transaction
```

`Item(author_id: UUID | None, excerpt: str, link: str | None)`. The case keeps the excerpt (its first 1,000 characters), so the queue shows what was reported after an edit or a delete.

**Python:**

- `await moderation.report(db, target, *, reporter, reason, note=None) -> UUID`: opens the thing's case or adds to the open one, and returns the case. A second report from the same person changes nothing. `reason` is one of `moderation.REASONS`: `spam`, `harassment`, `hate`, `sexual`, `violence`, `self_harm`, `illegal`, `other`.
- `await moderation.screen(db, text) -> Screen(hold: bool, reasons: tuple[str, ...])`: the filters' verdict. On a hold the module keeps the text out of sight and calls `await moderation.hold(db, target, reasons=screen.reasons)`, which opens a case whose one report is the filters' (`reporter` None, `reason` `filter`). The poster gets the same answer either way.
- `await moderation.act(db, case_id, action, *, actor, reason, note=None, minutes=None)`, below.
- `Depends(moderation.can_post)`: the current user, or 403 `kernel.timed_out` with `until` while they're timed out. Every posting route of a module uses it.

**Actions**

| Action | Needs | Does |
| --- | --- | --- |
| `dismiss` | `kernel.moderation.act` | Closes the case |
| `hide`, `delete` | the same, and the kind lists it | The module's `apply`, then closes the case |
| `time_out` | the same | `auth_user.timed_out_until` = now + `minutes` (60 to 43,200, up to 30 days). They still sign in and read |
| `ban` | the same and `auth.user.suspend` | Suspends the author (below), closes the case |

Refused with 403 `kernel.moderation_refused`: acting on yourself, or on a case you wrote; a time-out or ban of staff (staff are suspended from the People page, under decision 0013); hiding or deleting staff's content without every permission they hold (0013's rule). A closed case is 409 `kernel.case_closed`; a kind whose module is off is 404 `kernel.module_off`, as its module's routes are.

**Suspension** (SPEC 14.7): `status` `suspended`, `session_epoch` + 1 (every session ends), audited, and `auth.user.suspended` emitted. Restoring sets `active` and emits `auth.user.restored`, which is new in SPEC 11. Only an owner suspends an owner, and never the last one (14.1).

**Telling the person:** a hide or a delete sends the notice `kernel.content_removed` (in the site and by email by default, then their choice). A time-out sends the mail `kernel.timed_out` and a ban sends `kernel.account_suspended`. Both are always sent, as security mail is. Each one names the reason and asks for a reply to the email if it's a mistake, never naming the reporter or the moderator. The reporter hears nothing more.

**HTTP.** Lists take `?cursor=&limit=` and answer `{items, next_cursor}`; bodies are strict models.

- `POST /api/kernel/moderation/reports` (signed in, verified, otherwise 403 `auth.email_unverified`): `{target: {type, id}, reason, note?}` → 202 `{}`, the same for a first report and a repeat. An unknown kind or thing is 404 `kernel.report_target_unknown`. Limited to 20 per account per hour.
- `GET /api/kernel/admin/moderation/cases` (`kernel.moderation.act`): filters `status` (`open` by default, `actioned`, `dismissed`), `kind` and `source`; the latest report first.
- `GET /api/kernel/admin/moderation/cases/{id}`: the case, its reports (reporter, reason, note, time) and its outcome.
- `POST /api/kernel/admin/moderation/cases/{id}/actions`: `{action, reason, note?, minutes?}` → 200, the case.
- `PUT` and `DELETE /api/kernel/admin/moderation/people/{user_id}/time-out` (`kernel.moderation.act`): time someone out without a case (live chat), or lift it.
- `POST /api/auth/admin/users/{user_id}/suspend` with `{reason}`, and `POST .../restore` (`auth.user.suspend`, step-up).
- `GET /api/kernel/admin/moderation/log` (`kernel.moderation.act`): the audit entries for moderation and suspensions, without IP or browser. This is the narrower view decision 0037 promised moderators.

**Filters** are the settings section `kernel.moderation`, saved through `settings.save`, which audits it:

- `held_terms`: up to 500 words or phrases, each at most 64 characters, matched whole-word after NFKC and case folding.
- `blocked_domains`: a link to one of them, or to any of its subdomains, is held.
- `max_links` (default 2): text with more links than this is held.

Empty lists hold nothing.

**Audit.** `KERNEL_ACTIONS` gains `kernel.moderation.dismissed`, `.hidden`, `.deleted`, `.timed_out`, `.time_out_lifted`, `auth.user.suspended` and `auth.user.restored`:

- target: the thing, or `("auth.user", id)`
- subject: the author
- details: `{case, reason}`, never the note or the excerpt

Reports aren't audited: their table is their record.

**Pruning:** `kernel.prune_moderation` runs daily and deletes cases, with their reports, closed more than `AUDIT_KEEP_DAYS` ago.

## 3. Data

Migration `kernel/migrations/0010_moderation.py` (`kernel_0010`). Ids of people stay plain, with no foreign key, as in the audit log.

| Table | Column | Type | Null | Default / FK / index |
|---|---|---|---|---|
| `kernel_moderation_case` | `id` | `uuid` | no | PK |
| | `target_type`, `target_id` | `varchar(64)` each | no | unique `(target_type, target_id)` where `status = 'open'` |
| | `source` | `varchar(8)` | no | `report` or `filter` (check) |
| | `status` | `varchar(16)` | no | `'open'`; `open`, `actioned`, `dismissed` (check); index `(status, last_report_at)` |
| | `author_id` | `uuid` | yes | index |
| | `excerpt` | `varchar(1000)` | no | |
| | `link` | `varchar(500)` | yes | |
| | `report_count` | `integer` | no | `0` |
| | `opened_at`, `last_report_at` | `timestamptz` | no | |
| | `closed_at`, `closed_by`, `outcome` | `timestamptz`, `uuid`, `varchar(16)` | yes | `outcome` is the action taken; index `(closed_at)` |
| `kernel_moderation_report` | `id` | `bigint` identity | no | PK |
| | `case_id` | `uuid` | no | FK to the case, ON DELETE CASCADE; index |
| | `reporter_id` | `uuid` | yes | unique `(case_id, reporter_id)`; None is the filters |
| | `reason` | `varchar(16)` | no | `REASONS` or `filter` (check) |
| | `note` | `varchar(1000)` | yes | |
| | `at` | `timestamptz` | no | |
| `auth_user` | `timed_out_until` | `timestamptz` | yes | |

The downgrade drops all three.

## 4. Files

**New:**

- `kernel/backend/kernel/moderation.py`
- `kernel/migrations/0010_moderation.py`
- `kernel/tests/test_moderation.py`
- `docs/decisions/0039-kernel-moderation.md`

**Changed:**

- `kernel/__init__.py`
- `models.py`: the case and the report
- `auth/models.py`: `timed_out_until`
- `auth/routes.py`: suspension
- `audit.py`: the new actions
- `events.py`: `UserSuspended`, `UserRestored`
- `modules.py`: finds `moderation.py`
- `app.py`: installs the kinds, the prune job, the routes and the settings section
- `routes.py`
- `auth/mails.py`: the two mails and the notice's template
- `kernel/kernel.json`: the notice key
- `tests/test_migrations.py`
- `docs/contracts/auth-api.md`
- `SPEC.md`: 6, 11, 14.7, 14.11, and the change log
- `modules/_template/` gets an example `moderation.py`
- `CLAUDE.md`/`AGENTS.md`, `docs/HANDOFF.md`, `docs/progress.json`, `docs/PROGRESS.md`

## 5. Conventions this follows

**Kernel patterns:**

- `events.py` and `jobs.py`: a module's declarations, found per module, with their owner checked at start
- `audit.py`, `notifications.py`, `settings.py`
- `kernel.prune_audit` for batched pruning
- SPEC 7's lists, and decision 0013's rule for acting on staff

**Ported, not copied:**

- VybeMindz `moderation-audit-log`: guard, change and record in one transaction; nobody acts on themselves or on someone above them; sessions end at once.
- VybeSite `contact_filter.py`: held, never thrown away, with the same answer to the sender. VybeSite's `blocklist_service.py` checks DNS blocklists for mail reputation, not text, so nothing is taken from it.

**Skills:** `alembic-multi-module-migrations`, `module-contract-lint`, `auth-threat-model-checklist` (suspension ends sessions).

**Memory notes:** `rollback-expires-orm-rows`, `race-tests-that-really-race`.

## 6. Non-goals

- No pages and no report button. K4 builds them on these routes: the queue, suspension on the People page, the filter settings, and the kit's `<ReportButton>`.
- No appeals: the mail names the site's contact address. A formal appeal comes later.
- No word to the reporter about the outcome, and no reports from guests.
- Nothing automatic. The filters hold and people decide: no hiding after N reports, no automatic bans, no classifiers or outside services, no DNS link blocklists yet.
- No live push. Closing a suspended person's open WebSocket is the community module's job, on `auth.user.suspended`.
- No slow mode, channel mutes or thread locks: those are community's.
- No IP or device bans: suspension is per account. Modules decide what hiding means and whether a suspended person's content stays up.
- No erasing a deleted person's reports and excerpts yet: K2 step 11's deletion hook does that.

## 7. Acceptance

**`kernel/tests/test_moderation.py`:**

- A report opens one case, more reports join it, and a repeat changes nothing. A rolled-back report leaves nothing.
- An unknown kind or thing is a 404, and so is a module switched off.
- Each action does what the table says and closes the case in the same transaction as the module's `apply`. A failing `apply` leaves the case open.
- Each refusal holds: yourself, staff, 0013's rule, a closed case, `ban` without `auth.user.suspend`, and minutes out of range.
- A time-out makes `can_post` answer 403 until it ends or is lifted.
- A suspension ends every session, emits `auth.user.suspended` (heard with the `heard` fixture) and sends its mail. A restore emits `auth.user.restored`. The last owner can't be suspended.
- The filters hold on a term (whole-word, after folding), a domain or a subdomain, and too many links. Empty lists hold nothing.
- The routes: access (401, 403, unverified), every filter, newest first, pages that neither repeat nor skip, and the report limit.
- The log shows only moderation and suspension entries, with no IP or browser.
- Pruning removes only cases closed past `AUDIT_KEEP_DAYS`.

**Elsewhere:**

- `tests/test_migrations.py`: 0010's round trip.
- The full suite is green, coverage is at 95 % or more, and `moderation.py` is at 100 %.
- Mutants on the guards, the filters' matching, the time-out bounds and the prune cutoff are all killed.

## 8. Open questions

None. On 2026-11-17 the owner approved the goal and non-goals as written, with the five answers recommended:

1. **What can be reported?** Recommended: only kinds a module declares, each with a `describe` and an `apply`. A profile is then its module's kind; the kernel has no profiles.
2. **Who reports, and who sees the queue?** Recommended: signed-in accounts with a verified address, 20 reports an hour, and no guests. The queue and the narrower log go to holders of `kernel.moderation.act` (admins and editors by default), who see who reported.
3. **Who bans?** Recommended: a ban also needs `auth.user.suspend`, which admins hold by default. Editors hide, delete and time out for up to 30 days. This narrows decision 0031's description ("hide, delete, time out and ban"); a site can grant editors `auth.user.suspend`.
4. **Filters now or later?** Recommended: now, as above. They hold and never drop, and they're built new, since VybeSite has no text filter to lift. Comments and community need them at the site's step 3.
5. **Telling people, and appeals?** Recommended: the author is told why, as above, never who did it; the reporter isn't told the outcome; and there are no appeals in v1 beyond the contact address.

## Changes after approval

2026-11-17, during the build (flagged in the handoff as contract changes):

- **Suspension routes follow `docs/contracts/auth-api.md`,** which already had them, with a contract test: `POST /api/auth/admin/users/{id}/suspend` and `/restore`, not `PUT` and `DELETE .../suspension`. Their refusals are auth's: 403 `auth.not_yourself`, and 403 `auth.role_not_yours` for an owner by a non-owner or anyone holding a permission the caller doesn't, as for roles.
- **Names take one dot** where the kernel's patterns allow only one, problem codes (`<module>.<snake_case>`) and notification keys and templates (`<owner>.<name>`): `kernel.report_target_unknown`, `kernel.moderation_refused`, `kernel.case_closed`, `kernel.timed_out`; the notice `kernel.content_removed`; the mails `kernel.timed_out` and `kernel.account_suspended`.
- **The templates live in `moderation.TEMPLATES`,** declared under the owner `kernel` as notifications' footer is, not in `auth/mails.py`. **The kernel's notice key lives in code** (`moderation.NOTIFICATIONS`): `kernel.json`'s schema has no `notifications`. `notifications.preferences` and `choose` always take the kernel's keys.
- **No contact address setting exists,** so the mails ask the person to reply to the email, which comes from `MAIL_FROM`.
- **The `member` role counts for nothing in decision 0013's comparison,** so a module's permission granted to members never stops an admin suspending one.
