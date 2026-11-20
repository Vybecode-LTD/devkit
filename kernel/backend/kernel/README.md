# kernel (Python package)

`__init__.py` is the public surface (SPEC.md section 6). Modules import from `kernel` only.

| File | What | Phase |
| --- | --- | --- |
| `app.py` | `create_app`: builds a site's app from the kernel, its modules and, from K5, its own pages (`site=`, decision 0048) | K1 |
| `config.py` | Environment config; refuses to start on unsafe secrets outside DEBUG; MODULES | K1 |
| `db.py` | `Base`, naming convention, `Database`, `get_db`, one-row tables (`for_saving`) | K1 |
| `crypto.py` | `seal` / `open` / `rotate` with MultiFernet | K1 |
| `errors.py` | `Problem` and the handlers: RFC 9457 problem details everywhere | K1 |
| `security.py` | CSP (with per-module hosts), security headers, same-origin writes, www redirect | K1 |
| `ratelimit.py` | `rate_limit(rule, key)` and `RateLimiter`, per IP (IPv6 /64) or account | K1 |
| `redact.py` | Strips emails, tokens, IPs, queries and DB values from text | K1 |
| `logs.py` | JSON or text logs, stdout/stderr split, every line redacted | K1 |
| `error_tracking.py` | Sentry, only when SENTRY_DSN is set; nothing private sent | K1 |
| `modules.py` | Manifests, the module registry, switches and `require_module`; from K5, `load_module`, which builds a module from its manifest and fixed names | K1 |
| `settings.py` | Versioned per-module settings with three-way merge on save | K1 |
| `access.py` | Route access marks (`public`) and the audit of undeclared routes | K1 |
| `models.py` | Kernel tables: `kernel_module_state`, `kernel_setting`, `kernel_setting_version` | K1 |
| `routes.py` | `/api/kernel/health`, `/api/kernel/modules` | K1 |
| `clock.py` | The kernel's clock, which tests can move forward (`advance`, `reset`) | K1 |
| `version.py` | `__version__`, kept in step with `kernel.json` | K1 |
| `email.py` | The `Mailer` adapter interface beneath K3's `email.send`: the checks every adapter sits behind (`Checked`), the default that sends nothing (`LogMailer`), the harness's capture and `get_mailer` | K2 |
| `storage.py` | S3-compatible storage: a private bucket behind signed links and a public one (decision 0032) | K3 |
| `mail_adapters.py` | The SMTP and Resend adapters beneath `email.send` and `email.queue` (decision 0033) | K3 |
| `jobs.py`, `cron.py`, `worker.py` | Jobs queued in the caller's transaction, the cron parser, and the worker and scheduler that run them (decision 0035) | K3 |
| `events.py` | Event payloads, listeners and `emit`, delivered as jobs (decision 0036) | K3 |
| `audit.py` | One append-only audit log for every module, `audit.record` in the caller's transaction, and the readers (decision 0037) | K3 |
| `notifications.py` | Notices in the site and by email, each person's choice per key, one-click unsubscribe (decision 0038) | K3 |
| `moderation.py` | Reports on declared kinds, the staff queue, filters that hold, actions and suspension (decision 0039) | K3 |
| `server_copy.py` | Public pages crawlers can read: matching `routes.public`, the builders, each page's head and JSON-LD, the default home page, `sitemap.xml`, `robots.txt`, `llms.txt` and the site's identity (decision 0041) | K3 |
| `shell.py` | The built web app from `WEB_DIST`, the shell, what every address outside the API answers, HEAD as GET (decision 0041) | K3 |
| `auth/` | `models.py` (every auth table), `passwords.py` (Argon2id, the rules, the bundled list, Pwned Passwords), `hashing.py` (keyed hashes for one-time secrets), `sessions.py` (opaque cookie sessions, their limits and new tokens, the known-device cookie), `permissions.py` (who holds what: owners, roles, per-resource overrides), `dependencies.py` (`current_user` and the other access dependencies, the admin gate, `SessionCookies`), `accounts.py` (addresses as looked up, the account a client is shown), `second_factor.py` (TOTP, recovery codes and the sign-in challenge), `audit.py` (auth's audit rows), `tokens.py` (one-time link tokens), `routes.py` (sign-in, the second factor, the session, sign-out and step-up at `/api/auth`), `sign_up.py` (sign-up, the site's mode and email verification), `codes.py` (sign-in codes and magic links), `floor.py` (the answer floor), `resets.py` (password resets), `email_change.py` and `password_change.py`, `totp.py` (TOTP setup and removal, new recovery codes), `passkeys.py` (registering, listing, renaming and removing passkeys, signing in with one, the options for one as a second factor or at step-up), `ceremonies.py` (the passkey challenges and the `webauthn` checks), `factor_undo.py` (undoing a passkey or TOTP from the link in its mail), `data/` (the common-password list) | K2, started |

Still to come: the rest of `auth` (K2 steps 9 to 11: OAuth, invites, API keys and the account routes); `retention` and the AI client (K3).
