# kernel (Python package)

`__init__.py` is the public surface (SPEC.md section 6). Modules import from `kernel` only.

| File | What | Phase |
| --- | --- | --- |
| `app.py` | `create_app`: builds a site's app from the kernel and its modules | K1 |
| `config.py` | Environment config; refuses to start on unsafe secrets outside DEBUG; MODULES | K1 |
| `db.py` | `Base`, naming convention, `Database`, `get_db`, one-row tables (`for_saving`) | K1 |
| `crypto.py` | `seal` / `open` / `rotate` with MultiFernet | K1 |
| `errors.py` | `Problem` and the handlers: RFC 9457 problem details everywhere | K1 |
| `security.py` | CSP (with per-module hosts), security headers, same-origin writes, www redirect | K1 |
| `ratelimit.py` | `rate_limit(rule, key)` and `RateLimiter`, per IP (IPv6 /64) or account | K1 |
| `redact.py` | Strips emails, tokens, IPs, queries and DB values from text | K1 |
| `logs.py` | JSON or text logs, stdout/stderr split, every line redacted | K1 |
| `error_tracking.py` | Sentry, only when SENTRY_DSN is set; nothing private sent | K1 |
| `modules.py` | Manifests, the module registry, switches and `require_module` | K1 |
| `settings.py` | Versioned per-module settings with three-way merge on save | K1 |
| `access.py` | Route access marks (`public`) and the audit of undeclared routes | K1 |
| `models.py` | Kernel tables: `kernel_module_state`, `kernel_setting`, `kernel_setting_version` | K1 |
| `routes.py` | `/api/kernel/health`, `/api/kernel/modules` | K1 |
| `clock.py` | The kernel's clock, which tests can move forward (`advance`, `reset`) | K1 |
| `version.py` | `__version__`, kept in step with `kernel.json` | K1 |
| `auth/` | `models.py` (every auth table), `passwords.py` (Argon2id, the rules, the bundled list, Pwned Passwords), `hashing.py` (keyed hashes for one-time secrets), `sessions.py` (opaque cookie sessions, their limits and new tokens, the known-device cookie), `permissions.py` (who holds what: owners, roles, per-resource overrides), `dependencies.py` (`current_user` and the other access dependencies, the admin gate, `SessionCookies`), `data/` (the common-password list) | K2, started |

Still to come: the rest of `auth` (K2: sign-in, passkeys, OAuth, TOTP, API keys and the routes); `email`, `storage`, `events`, `jobs`, `notifications`, `moderation`, `audit`, `retention`, public rendering and the AI client (K3).
