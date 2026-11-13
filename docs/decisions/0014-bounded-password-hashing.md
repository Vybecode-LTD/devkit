# 0014: Password hashing is bounded

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** Each Argon2id hash holds 64 MiB for tens of milliseconds. `kernel.auth.passwords` ran them on asyncio's default thread pool, which is shared with everything else and sized by CPU count, so a burst of sign-ins could exhaust a small host's memory or starve other work. The dummy hash for unknown accounts was made on the first one, which made that request slower than the rest. A stored value that wasn't an Argon2 hash cost nothing at all. The site couldn't set its own parameters.
- **Decision:**
  - Hashing runs on a pool of its own, `ARGON2_CONCURRENCY` threads wide (4 by default). A request that waits more than 5 seconds for a slot is answered 503 `kernel.busy` with `Retry-After: 5`.
  - `ARGON2_MEMORY_KIB`, `ARGON2_TIME_COST` and `ARGON2_LANES` set the parameters, never below OWASP's 19 MiB, 2 passes and 1 lane.
  - The dummy hash is made when `Passwords` is. An unknown account, a password no rule keeps, and a stored value that isn't Argon2 each cost one verify against it.
  - The common-password check also tries the password with its spaces taken out. The bundled lists hold most phrases unspaced.
  - "About this site" is the refusal only when the site's name, the address or "password" was actually taken out. A password made of symbols or emoji isn't refused for having few letters.
- **Alternatives:**
  - A process pool: true parallelism, but every worker holds a copy of the hasher and the start-up cost lands on the first sign-in.
  - Queueing without a deadline: a flood would turn into timeouts at the proxy instead of an answer the page can explain.
- **Consequences:**
  - SPEC.md 14 and 14.6 and the change log gain the pool, the 503 and the one-verify rule. `docs/contracts/auth-api.md` lists `kernel.busy`.
  - The claude.ai design doc needs 14 and 14.6 synced.
- **See:** SPEC.md 14 (passwords) and 14.6; decision 0013; `kernel/backend/kernel/auth/passwords.py`
