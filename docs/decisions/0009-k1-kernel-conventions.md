# 0009: Conventions settled while building the kernel's core (K1)

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** Phase K1 lifted the kernel's non-auth foundations from VybeSite. A few things the spec left open, or said loosely, had to be pinned down in code.
- **Decision:**
  - `settings.for_module(db, id)` takes the request's session, like every other kernel service that reads the database. A module's settings model is a Pydantic model with a default for every field; a field typed `SecretStr` is a secret, sealed at rest and never shown or kept in a version.
  - A problem's `type` is `urn:devkit:problem:<code>`, so it never depends on the site's address. Clients match on `code`.
  - `ENCRYPTION_KEYS` holds Fernet keys, newest first, comma-separated (MultiFernet). `SECRET_KEY` (32+ random bytes) is the HMAC key for signed values. There is no JWT secret: sessions are opaque (14.5).
  - A module's backend is found by fixed names: `router.py`'s `router`, `schemas.py`'s `Settings`, and `__init__.py`'s `CSP` (the hosts it adds to the Content-Security-Policy while it's on). The harness discovers them; a site's generated `backend/app/modules.py` lists them.
  - Module CSP hosts are https origins only, and only in `script-src`, `img-src`, `connect-src`, `frame-src`, `media-src`, `form-action` and `font-src`. Never `style-src`, never `'unsafe-inline'`.
  - ~~The module switches read the database on every module request. The security headers use the last switch state seen, since middleware can't wait on the database.~~ Changed after the audit (2026-11-12, finding F14): the per-request read cost about 2 ms and a pooled connection on every module call, and the headers' copy was per process, so another worker's switch never reached a page's CSP until that process served a module request. Now one cache per process, read at most every `MODULES_CACHE_SECONDS` (5 by default), is shared by `require_module`, the CSP and `/api/kernel/modules`. A switch applies at once in the process that made it and within the TTL everywhere else. If the database doesn't answer, the last set stands.
- **Alternatives:** A global session for `for_module` (rejected: hidden state, harder tests); a site-relative problem `type` URL (rejected: changes per site).
- **Consequences:** Spec section 6's table shows `for_module(db, id)`. List settings merge as one value, not item by item as VybeSite's do; revisit if a module needs it.
- **See:** SPEC.md sections 6, 7 and 15; `kernel/backend/kernel/settings.py`, `errors.py`, `security.py`, `modules.py`
