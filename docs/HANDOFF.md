# Handoff

Overwritten every session. 2026-11-17, Eastern (Claude Code, the owner's machine, part over Remote Control): K3 audit (#67, decision 0037) and K3 notifications (#69, decision 0038), each contract first and approved by the owner with the answers recommended, each landed by this session; the audit handoff (#68) in between. Then this page (#70).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3, in decision 0029's order:** storage (#58), email (#59), the kernel's mails as templates (#60), jobs (#63), events (#65), audit (#67), and now **notifications** (#69; contract `dev plans/contracts/k3-notifications.md`):
  - `notifications.notify(db, user_id, key, context, *, link=None) -> Sent`: renders the key's email template (same name; its subject is the in-site title) and, in the caller's transaction, queues the email first, then adds the `kernel_notification` row, each by the person's choice for that key, else module.json's default. Email only to an active, verified account. A NUL, an undeclared key, a link off the site or a missing value is refused before anything is added.
  - `assemble` checks every module's keys (its own, once, with a template). Every notice email gets the `kernel.notification_footer` template and RFC 8058's two headers; `Mailer.send` and `email.queue_message` take `headers` (only those two, at most 900 characters); the SMTP adapter writes them unfolded.
  - Routes at `/api/kernel/notifications`: the list (`unread`), read marks, preferences (strict `RootModel` body), and the unsubscribe GET (changes nothing) and POST (public; the one write `SameOriginWrites` lets another site send; writes only `email`).
  - `kernel_0009`: `kernel_notification`, `kernel_notification_preference`. `kernel.prune_notifications` nightly: 90 days after read, a year at most.
- **Audit (#67):** one append-only `kernel_audit_event`; `audit.record`; `GET /api/kernel/admin/audit` and `GET /api/auth/activity`; triggers refuse UPDATE and TRUNCATE, and DELETE but the nightly pruning's.
- **Tests:** last local run 1422 passed, 7 skipped (5 live storage, 1 symlink, 1 SIGTERM on Linux only), 27 strict expected failures; coverage 98.23 %, `audit.py`, `notifications.py` and `mail_adapters.py` 100 %; every mutant killed (39 for audit, 40 for notifications). CI passed on `main` at f3cd4db.
- **Progress:** v1.0 at 41 % (23 of 56); the ledger shows it.

## Next

1. **K3 moderation, contract first** (`C:\DEV\_templates\feature-CONTRACT.md`): `moderation.report / queue / act` (SPEC 6): reports, the staff queue, word and link filters, actions (hide, delete, time out, ban), all audited; acting needs `kernel.moderation.act` (decision 0031). It emits `auth.user.suspended` (SPEC 11), records its actions (new `KERNEL_ACTIONS`), and gives moderators a narrower audit view (the owner's answer on #67). Lift from `C:\DEV\VybeMindz\moderation-audit-log.zip` and VybeSite `services/blocklist_service.py`, `contact_filter.py` (KICKOFF K3).
2. Then public rendering and K3's gate; then **the rename PR** (decision 0034).
3. Then K4 (the pages these routes wait for: the audit log, the account's activity, the notice bell and settings, the unsubscribe page; the System page), K5, the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Still open from earlier sessions: decision 0036's own calls (a listener's 300-second default timeout; `auth.user.verified` on an email change's confirmation as well as sign-up's link and a reset; no deliveries at all for a module `MODULES` leaves out); decisions 0035's, 0032's and 0033's own calls (listed in each record); when to make the R2 test buckets; the desk steps (the `postgres` password; `Set-ExecutionPolicy` if wanted).
- `C:\DEV\knowledge` has `owner.md` uncommitted (the push-and-merge rule and an older Boston-time line): the owner commits it.

## Notes

- **A new kernel audit action** joins `audit.KERNEL_ACTIONS` in the same PR. **A new notification key** needs an email template of the same name. **A list route** takes `?cursor=&limit=` and answers `{items, next_cursor}` (SPEC 7). **A request body** is a strict Pydantic model, a `RootModel` for a map (`test_every_request_body_is_strict`).
- **Shared test database:** filter on a target, actor, subject or person of the test's own. Old rows: insert them with explicit times (the clock only moves forward). Staff routes need a confirmed second factor (a `Totp` row). After `db.rollback()`, read no ORM row's attributes: keep plain ids.
- **Coverage on one module:** `--cov=kernel.<module>` breaks the run; use `--cov=kernel`.
- Git Bash: write scripts with the Write tool (`'''` heredocs can break `bash -c`, `cat > f` waits on stdin, `sed -i` drops CRs). Subprocesses: `sys.executable`.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
