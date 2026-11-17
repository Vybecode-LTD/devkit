---
feature: K3 notifications (kernel.notifications)
status: approved
approved: 2026-11-17 (the owner: as recommended, all four answers)
plan: dev plans/2026-11-17-next-session-k3-notifications.md (section 4, item 2); docs/HANDOFF.md, Next 1
pr: 69 (predicted)
---

# Contract: K3 notifications (`kernel.notifications`)

## 1. Goal

A module tells a person something happened with one call in the same transaction as the change: `await notifications.notify(db, user_id, "comments.reply", {"post": "Spring tour"}, link="/blog/spring-tour#c42")`. The person sees it in the site's notice list, gets it by email, or both, by their own choice for that kind of notice (the module's default until they change it). Every such email carries a one-click unsubscribe that works from the mail client without signing in. First users: comments' `reply` and `mention`, licensing's `license_issued` (Vibrant Mindz, decision 0029); in this PR, the module template's example key.

## 2. Interfaces

`kernel/backend/kernel/notifications.py`, public as `from kernel import notifications`.

```python
async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    key: str,                              # "<module>.<name>", declared in that module's module.json
    context: Mapping[str, str | int],      # the values its template uses, as email.send's
    *,
    link: str | None = None,               # a path on the site: "/...", never a scheme or "//"
) -> Sent                                  # Sent(in_site: bool, email: bool)
```

- **One template per key.** Each declared key has an email template of the same name in its module's `emails.py` (`email.Template`); the start refuses a key without one. Its subject, rendered, is the notice's title in the site (at most 200 characters); its text and HTML are the email. `link`, when given, is in the context as `link` (an absolute URL on `SITE_URL`).
- **Who gets what:** the person's choice for that key, else the manifest's `default` (`in_site`, `email`, `both`). Email goes only to an `active` account with a verified address; an account that isn't `active` gets nothing. Both are written in the caller's transaction: a `kernel_notification` row, and the mail queued sealed through `email` (kernel.jobs). Nothing is sent if the change rolls back.
- **Refusals** (ValueError, before anything is written): a key no installed module declares, a bad link, a context the template can't take.
- **The footer and headers.** The kernel appends a footer to every notice email (a `kernel.notification_footer` template a site can reword, with `${unsubscribe_url}` and `${settings_url}`) and sets `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058). `Mailer.send` and `email.queue_message` gain `headers: Mapping[str, str] | None`; the SMTP and Resend adapters pass them on.
- **The token** in an unsubscribe link names the person and the key, signed with `SECRET_KEY` (`kernel.auth.hashing`), and never expires.

**Routes** (signed in unless said; lists in SPEC 7's shape, `?cursor=&limit=` and `{items, next_cursor}`):

- `GET /api/kernel/notifications`: the person's notices, newest first, `{id, key, title, link, created_at, read_at}`, plus `unread` (a count).
- `POST /api/kernel/notifications/read` `{ids: [...]}` or `{all: true}`: 204; marks them read.
- `GET /api/kernel/notifications/preferences`: every key of the modules on, with its description, default and the person's `in_site` and `email`.
- `PUT /api/kernel/notifications/preferences` `{"<key>": {in_site, email}, ...}`: 200 with the whole list.
- `GET /api/kernel/notifications/unsubscribe?token=` (public): 200 `{key, description, email}`, changing nothing (link scanners open links). `POST` the same URL (public, the mail client's one-click or the site's confirm button): 200; email off for that key. A bad token is 404. The POST is exempt from the same-origin write check: a mail client sends no Origin.

**Pruning:** `kernel.prune_notifications`, nightly, removes notices per §8's answer.

## 3. Data

Migration `kernel/migrations/0009_notifications.py` (`kernel_0009`).

| Table | Column | Type | Null | Default / FK / index |
|---|---|---|---|---|
| `kernel_notification` | `id` | `uuid` | no | PK |
| | `user_id` | `uuid` | no | FK `auth_user.id` ON DELETE CASCADE; index `(user_id, created_at)` |
| | `key` | `varchar(100)` | no | |
| | `title` | `varchar(200)` | no | |
| | `link` | `varchar(500)` | yes | |
| | `created_at` | `timestamptz` | no | `now()` |
| | `read_at` | `timestamptz` | yes | partial index `(user_id)` where `read_at IS NULL` |
| `kernel_notification_preference` | `user_id` | `uuid` | no | PK with `key`; FK `auth_user.id` ON DELETE CASCADE |
| | `key` | `varchar(100)` | no | |
| | `in_site` | `boolean` | no | |
| | `email` | `boolean` | no | |
| | `updated_at` | `timestamptz` | no | `now()` |

A preference row exists only once the person changes a key from its default. Rows go with the account (cascade).

## 4. Files

- New: `kernel/backend/kernel/notifications.py`; `kernel/migrations/0009_notifications.py`; `kernel/tests/test_notifications.py`; `docs/decisions/0038-kernel-notifications.md`.
- Changed: `kernel/__init__.py`; `models.py`; `email.py`, `mail_adapters.py` (headers); `app.py` (checks keys against templates, installs them, routes, the prune job); `security.py` (the one exemption); `routes.py`; `config.py` if §8 makes the keep a setting; `modules/_template` (an example key and its template); `docs/contracts/auth-api.md`; `SPEC.md` (6, 14.6's line on security mails, change log); `.env.example`; `docs/progress.json` and its outputs; `docs/HANDOFF.md`.

## 5. Conventions this follows

`kernel/audit.py` (installed owners, keyset pages, nightly pruning), `kernel/email.py` (templates a site can reword, sealed queue), `kernel/events.py` (start checks against module.json). Skills `module-contract-lint`, `alembic-multi-module-migrations`, `verify-real-pass`.

## 6. Non-goals

- Not for security mail: sign-in codes, resets and the notices of 14.6 stay `kernel.auth.mails` and can't be turned off.
- No digests or batching, no quiet hours: one notice, one email.
- No push to the browser (WebSocket, SSE) and no web push, SMS or chat: the web shell asks for the unread count. SMS is the roadmap's `sms` module.
- No pages: K4 builds the bell, the list and the settings page on these routes.
- No muting a thread or a post: the module that owns threads does that, and simply doesn't call `notify`.
- No notices to people without an account (a mailing list is a module of its own).
- No translations: one language, as email's templates.
- Not audited, and no events emitted.

## 7. Acceptance

- `kernel/tests/test_notifications.py`: a rolled-back change leaves no notice and queues no mail; each default and each preference sends to the right places; no email to an unverified address, nothing to an account that isn't active; each refusal; the start refuses a key without a template; the footer and both headers on the queued mail; the routes' access, pages and unread count; read marks; preferences list only the keys of modules on; the unsubscribe GET changes nothing, the POST turns email off without a session or an Origin, a forged or altered token is 404; pruning.
- The SMTP and Resend adapters pass the headers (their existing tests extended). The full suite green, coverage 95 % or more, `notifications.py` 100 %; mutants on the routing and the token.

## 8. Open questions

None. On 2026-11-17 the owner approved the goal and non-goals as written, with the four answers recommended: (1) a notice is kept 90 days after it's read and a year at most unread, by a nightly job; (2) preferences per key only, no global switch; (3) the one-click link turns off email for that key only; (4) digests later.

## Changes after approval

- 2026-11-17, while building: `title` is `varchar(255)`, email's subject limit, since the title is the rendered subject. The routes sit in `kernel/routes.py`; `kernel.notifications` also exposes `build`, `install`, `Kind`, `TEMPLATES`, `unsubscribe_token`, `read_token`, `listed`, `mark_read`, `preferences`, `choose`, `looked_up`, `unsubscribe`, `view`, `PRUNE` and `BATCH`, and `kernel.email` gains `site_url()` and `HEADERS`. The footer's links point at the pages K4 will serve (`/notifications/unsubscribe?token=`, `/account/notifications`); the `List-Unsubscribe` header at the API. An unsubscribe token for an account that no longer exists is a 404. The module template declares `my-module.something_happened` with its template.
