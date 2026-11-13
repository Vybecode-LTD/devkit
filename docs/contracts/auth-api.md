# Auth HTTP API (contract for SPEC.md section 14)

The kernel's auth routes, as the contract tests in `kernel/tests/contract/` call them. They say what a client sends and gets back, never how the server does it, so a TypeScript port (SPEC.md section 19) passes the same suite. Status codes and problem `code`s are the contract; `detail` sentences may be reworded.

All bodies are JSON. Errors are problem details (`application/problem+json`, SPEC.md section 7). The session is the cookie `__Host-dk_session` (HttpOnly, Secure, SameSite=Lax, Path=/). Every state-changing request passes the same-origin check (`kernel.cross_site_write`, 403).

## Answers that never say whether an account exists

`sign-up`, `sign-in`, `code` and `password/reset-request` answer the same status and body for a known and an unknown email, in similar time (14.6). That includes their 429s. Sign-up with an address that has an account mails that address a notice instead of a verification link.

## Limits (SPEC.md 14.6)

A refused request answers 429 `kernel.rate_limited` with a `Retry-After` header (whole seconds) and `retry_after` in the body. The thresholds are 14.6's. Limits keyed on an email use the normalized address.

- **Password sign-in:**
  - 10 per IP per minute.
  - After 5 failures on one account in 15 minutes, 429 with growing waits, even for the right password, **except** on a browser holding that account's device cookie, where the right password answers 200.
  - Unknown emails count the same way, so the answers match.
- **Device cookie:** `__Host-dk_device` (HttpOnly, Secure, SameSite=Lax, Path=/) is set at a successful sign-in. It names the account, survives sign-out, and does nothing for any other account.
- **Codes and links:** 3 per email per 15 minutes, 10 per IP per hour. A second `POST /api/auth/code` within 60 seconds answers the same 202 and sends nothing.
- **Reset requests:** limited as codes are.
- **Sign-up:** 5 per IP per hour.
- **Second factor:** 5 failures end the challenge (`auth.challenge_ended`).
- **Step-up:** 5 failures per session in 15 minutes end the session (401 `kernel.not_signed_in` from then on).

## Mail the suite reads

- **`POST /api/auth/code`:** one message holding both the 6-digit code and the link `/auth/link?token=…`.
- **`POST /api/auth/password/reset-request`:** `/auth/reset?token=…`.
- **Sign-up:** `/auth/verify?token=…`.
- **Email change:** `/auth/email?token=…` to the new address, and `/auth/email/undo?token=…` to the old one.

## Public

| Method and path | Body | Answer |
| --- | --- | --- |
| `POST /api/auth/sign-up` | `{email, password, invite?}` | 202 `{"status": "check_email"}`. 403 `auth.sign_up_closed` or `auth.invite_required` by the site's mode; 422 `auth.password_rejected` with the reason |
| `POST /api/auth/verify-email` | `{token}` | 200 `{"status": "verified"}`; 400 `auth.token_invalid` |
| `POST /api/auth/sign-in` | `{email, password}` | 200 `{"status": "signed_in", "user": {...}}` and the cookie; or 200 `{"status": "second_factor", "challenge": "...", "methods": [...]}`; 401 `auth.invalid_credentials` |
| `POST /api/auth/sign-in/second-factor` | `{challenge, totp}` or `{challenge, recovery_code}` | 200 signed in; 401 `auth.invalid_second_factor`; after 5 failures 401 `auth.challenge_ended` (start over) |
| `POST /api/auth/code` | `{email}` | 202 `{"status": "check_email"}`. Members only: a staff account is sent nothing, with the same answer |
| `POST /api/auth/code/verify` | `{email, code}` | 200 signed in; 401 `auth.invalid_code` |
| `POST /api/auth/link/confirm` | `{token}` | 200 signed in; 401 `auth.invalid_link`. The emailed link opens the site's confirm page (`/auth/link?token=…`); only this POST signs in |
| `POST /api/auth/password/reset-request` | `{email}` | 202 `{"status": "check_email"}` |
| `POST /api/auth/password/reset` | `{token, password}` | 200 `{"status": "password_reset"}`; 400 `auth.token_invalid`; 422 `auth.password_rejected` with the reason. Every session of the account ends |
| `GET /api/auth/session` | | 200 `{"user": {"id", "email", "roles", "permissions", "verified", "second_factor"}}`; 401 `kernel.not_signed_in` |
| `POST /api/auth/sign-out` | | 204, the cookie cleared |
| `GET /api/auth/oauth/{provider}/start?next=/path` | | 302 to the provider, with `state`, PKCE S256 and, for OpenID providers, `nonce`. `next` must be a path on this site (one leading `/`, not `//`); anything else becomes `/` |
| `GET /api/auth/oauth/{provider}/callback?code&state` | | 302 to `next`, signed in; or, when the identity can't link on its own (14.3), 302 to `/sign-in?link=<provider>` with nothing linked; 400 `auth.oauth_state_invalid` for a wrong, missing, reused or other browser's `state` |

## Signed in

Rows marked **step-up** answer 403 `auth.step_up_required` unless the session signed in or stepped up in the last 10 minutes (14.4).

| Method and path | Body | Answer |
| --- | --- | --- |
| `POST /api/auth/step-up` | `{password}` or `{totp}` | 200 `{"status": "recent"}`; the session token is replaced |
| `POST /api/auth/password/change` | `{current_password, new_password}` | **step-up.** 200; every other session ends; 422 `auth.password_rejected` with the reason |
| `POST /api/auth/email/change` | `{email}` | **step-up.** 202; the new address confirms it |
| `POST /api/auth/totp/setup` | | **step-up.** 200 `{"secret", "otpauth_uri"}`; 403 `auth.email_unverified` until the email is verified (14.3). The TOTP counts as a second factor only once confirmed |
| `POST /api/auth/totp/confirm` | `{code}` | 200 `{"recovery_codes": [10 codes]}` |
| `DELETE /api/auth/totp` | | **step-up.** 204 |
| `POST /api/auth/recovery-codes` | | **step-up.** 200 `{"recovery_codes": [...]}`; the old ones stop working; 409 `auth.no_second_factor` while the account has no confirmed TOTP |
| `POST /api/auth/passkeys/register/start` | `{name}` | **step-up.** 200 WebAuthn creation options; 403 `auth.email_unverified` until the email is verified |
| `POST /api/auth/passkeys/register/finish` | the credential | 201 |
| `DELETE /api/auth/passkeys/{id}` | | **step-up.** 204 |
| `GET /api/auth/sessions` | | 200 `{"items": [...]}` with `current` marked |
| `DELETE /api/auth/sessions/{id}` | | 204 |
| `POST /api/auth/sessions/sign-out-others` | | 204 |
| `POST /api/auth/api-keys` | `{name, scopes, expires_in_days?}` | **step-up.** 201 `{"key": "dk_live_…"}`, shown once |
| `GET /api/auth/api-keys` / `DELETE /api/auth/api-keys/{id}` | | 200 / 204 |
| `POST /api/auth/account/delete` | | **step-up.** 202 `{"status": "deletion_scheduled", "at": "..."}`; signing in cancels it |
| `POST /api/auth/account/export` | | 202; the download link is emailed |

## Staff

Every route under `/api/<anything>/admin`, whatever its method, needs a session (else 401 `kernel.not_signed_in`), a staff role (else 403 `kernel.forbidden`) **and a confirmed second factor on the account** (else 403 `auth.second_factor_required`). Then it needs its own permission, else 403 `kernel.forbidden`. Owners hold every permission.

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /api/auth/admin/users` | | `auth.user.manage`. 200 `{"items": [...], "next_cursor"}` |
| `PUT /api/auth/admin/users/{id}/roles` | `{roles}` | `auth.role.assign`, **step-up.** 200. The person's next request gets a new session token. 403 `auth.role_not_yours` for a role whose permissions the caller doesn't all hold, or `owner` from a non-owner; 409 `auth.last_owner` for removing the last owner |
| `POST /api/auth/admin/users/{id}/suspend` | | `auth.user.suspend`. 200; every session of theirs ends. 403 `auth.role_not_yours` for an owner suspended by a non-owner; 409 `auth.last_owner` for the last owner |

## The harness's test support (never in a site)

Mounted by the harness only when `HARNESS_TEST_SUPPORT=1`, so the contract suite can drive time, mail and outside providers over HTTP. A port implements the same routes in its own harness. The harness site's sign-up mode is open, and its breach lookup is a fake that knows only the passwords given to `/api/_test/breached`, so the suite never goes online.

| Method and path | Does |
| --- | --- |
| `POST /api/_test/reset` | 204. Forgets rate-limit counts, captured mail, the clock offset and the breached list |
| `GET /api/_test/mail?to=` | `{"messages": [{"to", "subject", "text"}]}`, oldest first |
| `POST /api/_test/clock` | `{"advance": seconds}`: 204, moves the server's clock forward (not rate-limit windows, which run on real time) |
| `POST /api/_test/users` | `{email, password?, roles?, verified?, totp?}` makes an account, without judging the password: 201 `{"id", "totp_secret"?}` (the TOTP confirmed) |
| `POST /api/_test/breached` | `{passwords: [...]}`: 204, the fake breach lookup reports these as breached until the next reset |
| `POST /api/_test/oauth/grant` | `{provider: "test", subject, email, email_verified}`: 200 `{"code"}` the fake provider accepts once |
| `POST /api/_test/jobs/run` | 204, after running every job that is due |
| `GET /api/_test/delete-hooks` | `{"deleted": [user ids]}`, recorded by the harness's probe module |
| `GET /api/_test/routes` | `{"undeclared": [...], "admin": [...], "step_up": [...]}`: the route audit's list, then every admin route and every step-up route as `METHOD /path/{template}` |
