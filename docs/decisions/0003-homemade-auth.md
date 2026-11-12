# 0003: Homemade auth, owned by the kernel

- **Date:** 2026-11-12
- **Status:** Locked
- **Context:** Auth was built about a dozen different ways across C:\DEV. The owner wants one thorough system with no vendor lock-in.
- **Decision:** Auth is the kernel's (SPEC.md section 14): one auth_user table for staff and members (Q4); passwords of at least 12 characters for every account (Q7, the owner's call, below NIST's 15 for a password used alone and offset by the blocklist, rate limits and passkeys first); passkeys, OAuth with PKCE, email codes for members only; second factors required for staff; no SMS codes in v1 (Q5); opaque cookie sessions with members at 14 days idle and 30 days total and staff at 8 hours and 7 days (Q6). It owns the system, never the crypto: vetted libraries only.
- **Alternatives:** Supabase Auth; a hosted identity provider. Both tie every module to a vendor.
- **Consequences:** The contract tests in SPEC.md 14.13 must exist before auth ships. VybeSite's JWT sessions and split staff and member tables are ported as behavior, not shape.
- **See:** SPEC.md section 14
