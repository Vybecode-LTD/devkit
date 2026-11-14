# 0012: One-time secrets are kept as keyed hashes

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** The audit of 2026-11-12 found that `auth_token` kept every one-time secret as a plain SHA-256 with one `UNIQUE` across all users, and `auth_recovery_code` did the same. A 6-digit sign-in code has only a million values:
  - two people sent the same digits collide (about one clash per thousand live codes);
  - a copy of the table reverses every live code in under a second;
  - a lookup by hash alone would let one person's code sign in another.

  The audit also found that 13 of the 16 foreign keys had no index, that `auth_session` had no user-agent column although 14.5 asks for one, and that an API key's mode wasn't checked.
- **Decision:**
  - One-time tokens, sign-in codes and recovery codes are kept as HMAC-SHA256 under SECRET_KEY (`kernel.auth.hashing.keyed_hash`), over their purpose, whose they are (the address or the user id) and the value. Comparisons use `hmac.compare_digest`.
  - A 32-byte token stays unique by hash. A sign-in code isn't: it is found by its purpose and address, and must name the address.
  - Recovery codes are unique per person, and every lookup names the person.
  - Session tokens and API-key secrets are 32 random bytes and keep a plain SHA-256 (14.5, 14.9).
  - `auth_session` keeps the user agent (up to 300 characters). An API key's mode is `live` or `test`. Every foreign key has an index.
  - **Amended 2026-11-14 (#39):** a 32-byte token found by its hash (an email link, a second-factor challenge) is keyed over its purpose and value only. Whose it is isn't known until its row is found, and its 32 random bytes make it unique without the owner. The owner and the address are kept beside the hash and checked after the lookup: a verification link verifies only the address it was sent to. Binding them into the hash too would guard only against someone who can write the token table, who could already write the accounts themselves. Sign-in codes and recovery codes, found by purpose and address or by person, keep the owner in the hash.
  - Migration `kernel_0002` was amended in place, since no site has run it. A local database made from the old version needs `python -m harness.migrations downgrade kernel_0001`, then `upgrade`.
- **Alternatives:**
  - A pepper separate from SECRET_KEY: one more secret to keep and rotate, for no gain while SECRET_KEY already signs links.
  - Argon2 for codes: too slow for a value that is checked often and lives ten minutes.
  - A new migration `kernel_0003`: cleaner for sites that had run 0002, but none had.
- **Consequences:** Rotating SECRET_KEY voids every live one-time token and code; people ask again. A port reads SECRET_KEY and computes the same HMAC, so stored tokens survive it.
- **See:** SPEC.md 14.2, 14.5, 14.11 and 14.12; `kernel/backend/kernel/auth/hashing.py`; `kernel/migrations/0002_auth_tables.py`
