# Auth HTTP API (contract for SPEC.md section 14)

The kernel's auth routes, as the contract tests in `kernel/tests/contract/` call them. They say what a client sends and gets back, never how the server does it, so a TypeScript port (SPEC.md section 19) passes the same suite. Status codes and problem `code`s are the contract; `detail` sentences may be reworded.

All bodies are JSON. Errors are problem details (`application/problem+json`, SPEC.md section 7). The session is the cookie `__Host-dk_session` (HttpOnly, Secure, SameSite=Lax, Path=/). Every state-changing request passes the same-origin check (`kernel.cross_site_write`, 403).

## Answers that never say whether an account exists

`sign-up`, `sign-in`, `code` and `password/reset-request` answer the same status and body for a known and an unknown email, in similar time (14.6).

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
| `POST /api/auth/password/reset` | `{token, password}` | 200 `{"status": "password_reset"}`; 400 `auth.token_invalid` |
| `GET /api/auth/session` | | 200 `{"user": {"id", "email", "roles", "permissions", "verified", "second_factor"}}`; 401 `kernel.not_signed_in` |
| `POST /api/auth/sign-out` | | 204, the cookie cleared |
| `GET /api/auth/oauth/{provider}/start?next=/path` | | 302 to the provider, with `state`, PKCE S256 and, for OpenID providers, `nonce` |
| `GET /api/auth/oauth/{provider}/callback?code&state` | | 302 to `next`, signed in, or to the sign-in page to link first; 400 `auth.oauth_state_invalid` |

## Signed in

Rows marked **step-up** answer 403 `auth.step_up_required` unless the session signed in or stepped up in the last 10 minutes (14.4).

| Method and path | Body | Answer |
| --- | --- | --- |
| `POST /api/auth/step-up` | `{password}` or `{totp}` | 200 `{"status": "recent"}`; the session token is replaced |
| `POST /api/auth/password/change` | `{current_password, new_password}` | **step-up.** 200; every other session ends |
| `POST /api/auth/email/change` | `{email}` | **step-up.** 202; the new address confirms it |
| `POST /api/auth/totp/setup` | | **step-up.** 200 `{"secret", "otpauth_uri"}` |
| `POST /api/auth/totp/confirm` | `{code}` | 200 `{"recovery_codes": [10 codes]}` |
| `DELETE /api/auth/totp` | | **step-up.** 204 |
| `POST /api/auth/recovery-codes` | | **step-up.** 200 `{"recovery_codes": [...]}`; the old ones stop working |
| `POST /api/auth/passkeys/register/start` | `{name}` | **step-up.** 200 WebAuthn creation options |
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

Every route under `/api/<anything>/admin` needs a staff role **and a second factor on the account**, else 403 `auth.second_factor_required`. Then its own permission, else 403 `kernel.forbidden`.

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /api/auth/admin/users` | | `auth.user.manage`. 200 `{"items": [...], "next_cursor"}` |
| `PUT /api/auth/admin/users/{id}/roles` | `{roles}` | `auth.role.assign`, **step-up.** 200. The person's next request gets a new session token |
| `POST /api/auth/admin/users/{id}/suspend` | | `auth.user.suspend`. 200; every session of theirs ends |

## The harness's test support (never in a site)

Mounted by the harness only when `HARNESS_TEST_SUPPORT=1`, so the contract suite can drive time, mail and outside providers over HTTP. A port implements the same routes in its own harness.

| Method and path | Does |
| --- | --- |
| `POST /api/_test/reset` | Forgets rate-limit counts, captured mail and the clock offset |
| `GET /api/_test/mail?to=` | `{"messages": [{"to", "subject", "text"}]}`, oldest first |
| `POST /api/_test/clock` | `{"advance": seconds}`: moves the server's clock forward |
| `POST /api/_test/users` | `{email, password?, roles?, verified?, totp?}` makes an account: `{"id", "totp_secret"?}` |
| `POST /api/_test/oauth/grant` | `{provider: "test", subject, email, email_verified}`: `{"code"}` the fake provider accepts once |
| `POST /api/_test/jobs/run` | Runs every job that is due |
| `GET /api/_test/delete-hooks` | `{"deleted": [user ids]}`, recorded by the harness's probe module |
| `GET /api/_test/routes` | `{"undeclared": [...], "admin": [...]}`: routes with no declared access, and every admin GET route |
