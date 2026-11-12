"""The kernel's auth (SPEC.md section 14), built in K2.

Lifted from VybeSite (sessions, sign-in codes, signed-in devices, Argon2id,
password reset), Basefra.me (OAuth providers, API keys, invites) and
VybeMindz (session revocation, invite-only, per-resource permissions). The
HTTP contract is `docs/contracts/auth-api.md`.
"""
