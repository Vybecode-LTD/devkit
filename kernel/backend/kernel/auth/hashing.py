"""Keyed hashes for the one-time secrets auth keeps (decision 0012).

A 6-digit sign-in code or a recovery code has too few values to keep as a
plain SHA-256: anyone holding a copy of the table could try them all in under
a second. So every one-time token, code and recovery code is kept as
HMAC-SHA256 under SECRET_KEY, over its purpose, whose it is (the address or
the user id) and the value. Without the key the stored hashes say nothing,
and two people given the same 6-digit code keep different rows.

Session tokens and API-key secrets are 32 random bytes and keep a plain
SHA-256 (SPEC.md 14.5, 14.9).
"""

from __future__ import annotations

import hashlib
import hmac

from kernel.config import get_config


def keyed_hash(*parts: str) -> str:
    """HMAC-SHA256 under SECRET_KEY over `parts`, as 64 hex characters. Each
    part is length-prefixed, so ("a", "bc") and ("ab", "c") differ."""
    message = "".join(f"{len(part)}:{part}" for part in parts).encode("utf-8")
    key = get_config().secret_key.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def same(stored: str, computed: str) -> bool:
    """A constant-time comparison of two hashes (SPEC.md 14.12)."""
    return hmac.compare_digest(stored.encode("ascii"), computed.encode("ascii"))


__all__ = ["keyed_hash", "same"]
