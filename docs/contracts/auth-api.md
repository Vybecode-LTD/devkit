# Auth HTTP API (contract for SPEC.md section 14)

The kernel's auth routes, as the contract tests in `kernel/tests/contract/` call them. They say what a client sends and gets back, never how the server does it, so a TypeScript port (SPEC.md section 19) passes the same suite. Status codes and problem `code`s are the contract; `detail` sentences may be reworded.

All bodies are JSON. Errors are problem details (`application/problem+json`, SPEC.md section 7). The session is the cookie `__Host-mf_session` (HttpOnly, Secure, SameSite=Lax, Path=/). Every state-changing request passes the same-origin check (`kernel.cross_site_write`, 403).

## Answers that never say whether an account exists

`sign-up`, `sign-in`, `code` and `password/reset-request` answer the same status and body for a known and an unknown email, in similar time (14.6). That includes their 429s. Sign-up with an address that has an account mails that address a notice instead of a verification link.

## Limits (SPEC.md 14.6)

A refused request answers 429 `kernel.rate_limited` with a `Retry-After` header (whole seconds) and `retry_after` in the body. The thresholds are 14.6's. Limits keyed on an email use the normalized address. A route that hashes or checks a password can also answer 503 `kernel.busy`, with `Retry-After`, when the hashing pool is full.

- **Password sign-in:**
  - 10 per IP per minute.
  - Past 5 failures on one account in 15 minutes, 10 in an hour or 20 in a day, 429 with the wait, even for the right password, **except** on a browser holding that account's device cookie, where the right password answers 200.
  - Unknown emails count the same way, so the answers match.
- **Device cookie:** `__Host-mf_device` (HttpOnly, Secure, SameSite=Lax, Path=/) is set at a successful sign-in. It names the account, survives sign-out, and does nothing for any other account.
- **Codes and links:** 3 per email per 15 minutes, 10 per IP per hour. A second `POST /api/auth/code` within 60 seconds answers the same 202 and sends nothing.
- **Reset requests:** limited as codes are, the wait included: a second request within 60 seconds answers the same 202 and sends nothing.
- **Email change:** 3 requests per account per 15 minutes; a request within 60 seconds of the last answers the same 202 and sends nothing. Past 3 mails to one address in 15 minutes, nothing more is sent to it.
- **A new verification link:** 3 per account per 15 minutes. A second request within 60 seconds of the last link answers the same 202 and sends nothing.
- **Sign-up:** 5 per IP per hour. Past 3 sign-up mails to one address in 15 minutes, a sign-up for an address that has an account answers the same 202 and sends no notice. A new account's verification link always goes out.
- **Second factor:** 5 failures end the challenge (`auth.challenge_ended`). Past 10 failures on one account in an hour, its challenges answer 429 until the hour has passed.
- **Step-up:** 5 failures per session in 15 minutes end the session (401 `kernel.not_signed_in` from then on).
- **Passkey sign-in:** 10 per IP per minute for `passkeys/sign-in/start`, and the same for `/finish`.

## Passkeys (decision 0028)

Options are the JSON form of WebAuthn's `PublicKeyCredentialCreationOptions` or `PublicKeyCredentialRequestOptions` (base64url for bytes), and a credential is the JSON a browser's `PublicKeyCredential.toJSON()` gives. The relying party is the site's host and the origin the site's origin. A challenge is valid 5 minutes and works once. Registration asks for a discoverable credential (`residentKey: "required"`) with user verification, and excludes the account's passkeys. Signing in with a passkey alone and stepping up with one require user verification; as a second factor it is preferred. A sign count that doesn't rise, when either count isn't zero, is refused.

## Mail the suite reads

- **`POST /api/auth/code`:** one message holding both the 6-digit code and the link `/auth/link?token=…`.
- **`POST /api/auth/password/reset-request`:** `/auth/reset?token=…`.
- **Sign-up, and a new verification link:** `/auth/verify?token=…`.
- **Email change:** `/auth/email?token=…` to the new address when it is asked for, and `/auth/email/undo?token=…` to the old one once it is confirmed.
- **A passkey registered or a TOTP confirmed:** the security mail holds `/auth/second-factor/undo?token=…` (decision 0030).

## Public

| Method and path | Body | Answer |
| --- | --- | --- |
| `POST /api/auth/sign-up` | `{email, password, invite?}` | 202 `{"status": "check_email"}`; the account is a member, unverified. 403 `auth.sign_up_closed` or `auth.invite_required` by the site's mode; 422 `auth.password_rejected` with the reason; 422 `kernel.invalid_request` for anything but one email address |
| `POST /api/auth/verify-email` | `{token}` | 200 `{"status": "verified"}`; signs nobody in. 400 `auth.token_invalid` for a token used, older than 24 hours, or sent to an address the account no longer has |
| `POST /api/auth/sign-in` | `{email, password}` | 200 `{"status": "signed_in", "user": {...}}` and the cookie; or 200 `{"status": "second_factor", "challenge": "...", "methods": [...]}`; 401 `auth.invalid_credentials` |
| `POST /api/auth/sign-in/second-factor` | `{challenge, totp}`, `{challenge, recovery_code}` or `{challenge, passkey}` | 200 signed in; 401 `auth.invalid_second_factor`; after 5 failures, or for a challenge used, older than 10 minutes or unknown, 401 `auth.challenge_ended` (start over); 429 past the account's limit. A passkey answers the options its start route gave last |
| `POST /api/auth/sign-in/second-factor/passkey` | `{challenge}` | 200 WebAuthn request options for the account's passkeys, each call replacing the last; it costs no try. 401 `auth.challenge_ended` as above; 409 `auth.no_passkey` for an account with none |
| `POST /api/auth/passkeys/sign-in/start` | | 200 WebAuthn request options with no `allowCredentials` and user verification required. No email is asked |
| `POST /api/auth/passkeys/sign-in/finish` | the credential | 200 `{"status": "signed_in", "user": {...}}` and the cookie, as sign-in answers, for anyone, staff included, and never a second-factor step. 401 `auth.invalid_passkey` for anything wrong, the same answer whatever it is |
| `POST /api/auth/code` | `{email}` | 202 `{"status": "check_email"}`. Members only: a staff account is sent nothing, with the same answer |
| `POST /api/auth/code/verify` | `{email, code}` | 200 signed in, or for an account with a second factor 200 `{"status": "second_factor", …}` as sign-in answers; 401 `auth.invalid_code` |
| `POST /api/auth/link/confirm` | `{token}` | 200 signed in, or the second-factor answer as for a code; 401 `auth.invalid_link`. The emailed link opens the site's confirm page (`/auth/link?token=…`); only this POST signs in |
| `POST /api/auth/password/reset-request` | `{email}` | 202 `{"status": "check_email"}` |
| `POST /api/auth/password/reset` | `{token, password}` | 200 `{"status": "password_reset"}`; 400 `auth.token_invalid`; 422 `auth.password_rejected` with the reason, the link still working. Every session of the account ends, it signs nobody in, and the address counts as verified |
| `POST /api/auth/email/confirm` | `{token}` | 200 `{"status": "email_changed"}`: the account takes the new address, verified, and the old address is mailed an undo link valid 7 days. 400 `auth.token_invalid`. The emailed link opens the site's page (`/auth/email?token=…`); only this POST changes anything, and it signs nobody in |
| `POST /api/auth/email/undo` | `{token}` | 200 `{"status": "email_restored"}`: the old address is back and every session of the account ends. 400 `auth.token_invalid` |
| `POST /api/auth/second-factor/undo` | `{token}` | 200 `{"status": "second_factor_undone"}`: the passkey or TOTP the link was mailed for goes (a TOTP with its recovery codes) if it is still there; every session of the account ends; live sign-in codes and links, reset links and second-factor challenges stop working. 400 `auth.token_invalid`. The emailed link, valid 7 days and outliving resets and other undos, opens the site's page (`/auth/second-factor/undo?token=…`); only this POST changes anything, and it signs nobody in (decision 0030) |
| `GET /api/auth/session` | | 200 `{"user": {"id", "email", "roles", "permissions", "verified", "second_factor"}}`; 401 `kernel.not_signed_in` |
| `POST /api/auth/sign-out` | | 204, the cookie cleared |
| `GET /api/auth/oauth/{provider}/start?next=/path` | | 302 to the provider, with `state`, PKCE S256 and, for OpenID providers, `nonce`. `next` must be a path on this site (one leading `/`, not `//`); anything else becomes `/` |
| `GET /api/auth/oauth/{provider}/callback?code&state` | | 302 to `next`, signed in; or, when the identity can't link on its own (14.3), 302 to `/sign-in?link=<provider>` with nothing linked; 400 `auth.oauth_state_invalid` for a wrong, missing, reused or other browser's `state` |

## Signed in

Rows marked **step-up** answer 403 `auth.step_up_required` unless the session signed in or stepped up in the last 10 minutes (14.4).

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /api/auth/security` | | 200 `{"password": bool, "totp": {"since"} or null, "recovery_codes_left"}`: whether the account has a password, its confirmed TOTP and since when, and how many recovery codes are unused, for the account page. A TOTP set up but not confirmed is null |
| `POST /api/auth/verify-email/resend` | | 202 `{"status": "check_email"}`: a new 24-hour link to the address the account has now, the last one void. 409 `auth.already_verified` once it is verified |
| `POST /api/auth/step-up` | `{password}`, `{totp}` or `{passkey}` | 200 `{"status": "recent"}`; the session token is replaced. 401 `auth.invalid_credentials` for a wrong password, `auth.invalid_second_factor` for a wrong code or `auth.invalid_passkey` for a wrong passkey, the session kept; the fifth failure answers 401 `kernel.not_signed_in` and ends it. A passkey answers the options `step-up/passkey` gave this session |
| `POST /api/auth/step-up/passkey` | | 200 WebAuthn request options for the account's passkeys, user verification required; 409 `auth.no_passkey` for an account with none |
| `POST /api/auth/password/change` | `{current_password, new_password}` | **step-up.** 200 `{"status": "password_changed"}`: this session stays, with a fresh device cookie, and every other ends. 401 `auth.invalid_credentials` for a wrong current password, the session kept; it counts as a failed step-up, so the fifth ends the session. 422 `auth.password_rejected` with the reason |
| `POST /api/auth/email/change` | `{email}` | **step-up.** 202 `{"status": "check_email"}` whatever the address: the new address is mailed a link to confirm it, valid 24 hours, or a notice instead when it has an account. The old address works until then. 422 `kernel.invalid_request` for anything but one other address |
| `POST /api/auth/totp/setup` | | **step-up.** 200 `{"secret", "otpauth_uri"}`: a new secret of at least 160 bits, in place of any earlier one not yet confirmed. 403 `auth.email_unverified` until the email is verified (14.3); 409 `auth.totp_exists` while the account has a confirmed TOTP (remove it first). The TOTP counts as a second factor only once confirmed |
| `POST /api/auth/totp/confirm` | `{code}` | 200 `{"recovery_codes": [10 codes]}`, in place of any older ones: the TOTP is a second factor, and the code that confirmed it can't finish a sign-in. 401 `auth.invalid_second_factor` for a wrong code, the session kept; it counts as a failed step-up, so the fifth ends the session. 409 `auth.no_pending_totp` with nothing set up to confirm; 403 `auth.email_unverified`. The account is mailed, with an undo link |
| `DELETE /api/auth/totp` | | **step-up.** 204. A confirmed TOTP goes with its recovery codes, and every other session ends (the second-factor reset of 14.5); this one stays, with a fresh device cookie. Live sign-in codes and links, reset links and second-factor challenges stop working. A TOTP set up but not confirmed just goes; with none, nothing changes |
| `POST /api/auth/recovery-codes` | | **step-up.** 200 `{"recovery_codes": [10 codes]}`; the old ones stop working; 409 `auth.no_second_factor` while the account has no confirmed TOTP |
| `POST /api/auth/passkeys/register/start` | `{name}` | **step-up.** 200 WebAuthn creation options, for this session only; 403 `auth.email_unverified` until the email is verified; 409 `auth.too_many_passkeys` at 20; 422 `kernel.invalid_request` for a name not 1 to 80 characters once trimmed |
| `POST /api/auth/passkeys/register/finish` | the credential | 201 `{"id", "name", "created_at", "last_used_at"}`, the account mailed with an undo link. 400 `auth.invalid_passkey` for a credential that doesn't verify, a challenge used, expired or another session's, or a passkey registered already; 403 `auth.email_unverified`; 409 `auth.too_many_passkeys` |
| `GET /api/auth/passkeys` | | 200 `{"items": [{"id", "name", "created_at", "last_used_at"}]}`, oldest first |
| `PATCH /api/auth/passkeys/{id}` | `{name}` | **step-up.** 200 the passkey, renamed; 404 `auth.passkey_not_found` for an id that isn't one of the account's; 422 `kernel.invalid_request` as at registration |
| `DELETE /api/auth/passkeys/{id}` | | **step-up.** 204. Every other session ends (a second-factor reset, 14.5); this one stays, with a fresh device cookie. Live sign-in codes and links, reset links and second-factor challenges stop working, and the account is mailed. 404 `auth.passkey_not_found` for an id that isn't one of the account's |
| `GET /api/auth/sessions?cursor=&limit=` | | 200 `{"items": [{"id", "device_label", "location", "started_at", "last_seen_at", "current"}], "next_cursor"}`: the account's sessions that still count, the most recently seen first, this one `current`; `limit` 1 to 100 (50); 422 `kernel.invalid_request` for a `cursor` no answer gave. `device_label` names the browser and system ("Chrome on Android"); `location` is null when the site doesn't know it |
| `DELETE /api/auth/sessions/{id}` | | 204: that session ends at once. Ending this one is signing out, the cookie cleared. 404 `auth.session_not_found` for an id that isn't one of the account's sessions still counting |
| `POST /api/auth/sessions/sign-out-others` | | 204: every other session of the account ends; this one stays |
| `POST /api/auth/api-keys` | `{name, scopes, expires_in_days?}` | **step-up.** 201 `{"key": "mf_live_…"}`, shown once |
| `GET /api/auth/api-keys` / `DELETE /api/auth/api-keys/{id}` | | 200 / 204 |
| `POST /api/auth/account/delete` | | **step-up.** 202 `{"status": "deletion_scheduled", "at": "..."}`; signing in cancels it |
| `POST /api/auth/account/export` | | 202; the download link is emailed |
| `GET /api/auth/activity?cursor=&limit=` | | 200 `{"items": [{id, at, action, result, by_you, target, ip, user_agent, details}], "next_cursor"}`: the person's own `auth.*` entries, newest first; `limit` 1 to 100 (50); 422 `kernel.invalid_request` for a `cursor` no answer gave |

## Notifications (kernel.notifications, decision 0038)

Lists take `?cursor=&limit=` (1 to 100, 50) and answer `{items, next_cursor}` (SPEC 7); a `cursor` no answer gave is 422 `kernel.invalid_request`.

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /api/kernel/notifications` | | 200 `{"items": [{id, key, title, link, created_at, read_at}], "next_cursor", "unread"}`, newest first, the person's own |
| `POST /api/kernel/notifications/read` | `{ids: [1 to 100]}` or `{all: true}` | 204; only the person's own notices change |
| `GET /api/kernel/notifications/preferences` | | 200 `{"items": [{key, description, default, in_site, email}]}`: every key of the modules on |
| `PUT /api/kernel/notifications/preferences` | `{"<key>": {in_site, email}}` | 200, the whole list; 422 for a key of no module on |
| `GET /api/kernel/notifications/unsubscribe?token=` | | Public. 200 `{key, description, email}`, changing nothing; 404 `kernel.not_found` for a token the kernel didn't sign |
| `POST /api/kernel/notifications/unsubscribe?token=` | (RFC 8058's `List-Unsubscribe=One-Click`, ignored) | Public, and the one write another site may send: 200 `{"email": false}`, email off for that key alone; 404 as above |

## Moderation (kernel.moderation, decision 0039)

`reason` is one of `spam`, `harassment`, `hate`, `sexual`, `violence`, `self_harm`, `illegal`, `other`. Lists take `?cursor=&limit=` (1 to 100, 50) and answer `{items, next_cursor}`.

| Method and path | Body | Answer |
| --- | --- | --- |
| `POST /api/kernel/moderation/reports` | `{target: {type, id}, reason, note?}` (note up to 1,000) | Signed in with a verified address (else 403 `auth.email_unverified`); 20 an hour per account. 202 `{}`, the same for a first report and a repeat; 404 `kernel.report_target_unknown` for a kind no module on declares, or no such thing |
| `GET /api/kernel/admin/moderation/cases?status=&kind=&source=` | | `kernel.moderation.act`. 200, the latest report first; each `{id, target, source, status, author_id, excerpt, link, report_count, reasons, opened_at, last_report_at, closed_at, closed_by, outcome}`; `status` is `open` (default), `actioned` or `dismissed`; `source` is `report` or `filter` |
| `GET /api/kernel/admin/moderation/cases/{id}` | | `kernel.moderation.act`. 200, the case with `reports: [{reporter_id, reason, note, at}]`; 404 `kernel.not_found` |
| `POST /api/kernel/admin/moderation/cases/{id}/actions` | `{action, reason?, note?, minutes?}` | `kernel.moderation.act`; `ban` also `auth.user.suspend` (else 403 `kernel.forbidden`) and **step-up**. 200, the case, closed; a `dismiss` lets the module show again what the filters held. `action` is `dismiss`, `hide` or `delete` (if the kind lists it), `time_out` (`minutes` 60 to 43,200) or `ban`; a reason for all but `dismiss`. 403 `kernel.moderation_refused` for your own thing, staff timed out or banned, or staff's content without their permissions; 404 `kernel.module_off`; 409 `kernel.case_closed`; 422 `kernel.invalid_request` |
| `PUT /api/kernel/admin/moderation/people/{id}/time-out` | `{minutes, reason}` | `kernel.moderation.act`. 200 `{"until"}`. 403 `kernel.moderation_refused` for yourself or staff; 404 `kernel.not_found` |
| `DELETE /api/kernel/admin/moderation/people/{id}/time-out` | | `kernel.moderation.act`. 204 |
| `GET /api/kernel/admin/moderation/log?subject=` | | `kernel.moderation.act`. 200, the audit entries for moderation and suspensions, newest first, without `ip` or `user_agent` |

A module route that posts answers 403 `kernel.timed_out` with `until` while the person is timed out (`moderation.can_post`).

## Staff

Every route under `/api/<anything>/admin`, whatever its method, needs a session (else 401 `kernel.not_signed_in`), a staff role (else 403 `kernel.forbidden`) **and a confirmed second factor on the account** (else 403 `auth.second_factor_required`). Then it needs its own permission, else 403 `kernel.forbidden`. Owners hold every permission.

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /api/auth/admin/users` | | `auth.user.manage`. 200 `{"items": [...], "next_cursor"}` |
| `PUT /api/auth/admin/users/{id}/roles` | `{roles}` | `auth.role.assign`, **step-up.** 200. The person's next request gets a new session token. 403 `auth.role_not_yours` for a role whose permissions the caller doesn't all hold, or `owner` from a non-owner; 409 `auth.last_owner` for removing the last owner |
| `POST /api/auth/admin/users/{id}/suspend` | `{reason}`, one of moderation's reasons | `auth.user.suspend`, **step-up.** 200 `{"status": "suspended"}`; every session of theirs ends, they're mailed the reason, and `auth.user.suspended` is emitted; one already suspended changes nothing. 403 `auth.not_yourself`; 403 `auth.role_not_yours` for an owner suspended by a non-owner, or anyone holding a permission the caller doesn't (so the last owner is never suspended); 404 `kernel.not_found`; 409 `auth.account_not_active` for one being deleted, or when the caller's own account is no longer active (decision 0039) |
| `POST /api/auth/admin/users/{id}/restore` | | `auth.user.suspend`, **step-up.** 200 `{"status": "active"}`, emitting `auth.user.restored`; old sessions stay ended. The same refusals as suspending |
| `GET /api/kernel/admin/audit?actor=&subject=&action=&target_type=&target_id=&since=&until=&cursor=&limit=` | | `auth.audit.read`. 200 `{"items": [{id, at, action, result, actor_id, subject_id, target, ip, user_agent, details}], "next_cursor"}`, newest first. `action` is a name or a prefix ending in a dot (`blog.`); `target_id` only with `target_type`; `since` is inclusive, `until` not; `limit` 1 to 100 (50). 422 `kernel.invalid_request` for a bad filter or cursor |

## The harness's test support (never in a site)

Mounted by the harness only when `HARNESS_TEST_SUPPORT=1`, so the contract suite can drive time, mail and outside providers over HTTP. A port implements the same routes in its own harness. The harness site's sign-up mode is open, and its breach lookup is a fake that knows only the passwords given to `/api/_test/breached`, so the suite never goes online.

| Method and path | Does |
| --- | --- |
| `POST /api/_test/reset` | 204. Forgets rate-limit counts, captured mail, the clock offset and the breached list. With `{"accounts": true}` it also deletes every account |
| `GET /api/_test/mail?to=` | `{"messages": [{"to", "subject", "text"}]}`, oldest first, after running every job that is due (mail goes out as a job) |
| `POST /api/_test/clock` | `{"advance": seconds}`: 204, moves the server's clock forward (not rate-limit windows, which run on real time) |
| `POST /api/_test/users` | `{email, password?, roles?, verified?, totp?}` makes an account, without judging the password: 201 `{"id", "totp_secret"?}` (the TOTP confirmed) |
| `POST /api/_test/breached` | `{passwords: [...]}`: 204, the fake breach lookup reports these as breached until the next reset |
| `POST /api/_test/oauth/grant` | `{provider: "test", subject, email, email_verified}`: 200 `{"code"}` the fake provider accepts once |
| `POST /api/_test/jobs/run` | 204, after running every job that is due |
| `GET /api/_test/delete-hooks` | `{"deleted": [user ids]}`, recorded by the harness's probe module |
| `GET /api/_test/routes` | `{"undeclared": [...], "admin": [...], "step_up": [...]}`: the route audit's list, then every admin route and every step-up route as `METHOD /path/{template}` |
