"""Secrets at rest: sealed with Fernet, with keys that rotate (SPEC.md 14.12).

Lifted from VybeSite `core/crypto.py`, moved to MultiFernet. ENCRYPTION_KEYS
lists Fernet keys, newest first:

- `seal` encrypts with the newest key;
- `open` decrypts with whichever key sealed it;
- `rotate` reseals a value with the newest key. To retire a key: put a new
  one in front, reseal every stored value (each module's job, K3), then drop
  the old one.

Used for third-party API keys, TOTP secrets and provider tokens. Never for
passwords, which are hashed (K2). A value that can't be opened raises
`SealError`, which says nothing of the value.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from kernel.config import get_config


class SealError(ValueError):
    """A sealed value no key opens: it was sealed with a key since removed,
    or it was changed."""


@lru_cache(maxsize=4)
def _cipher(keys: tuple[str, ...]) -> MultiFernet:
    if not keys:
        raise SealError("ENCRYPTION_KEYS is empty, so nothing can be sealed or opened.")
    return MultiFernet([Fernet(key.encode("utf-8")) for key in keys])


def _current() -> MultiFernet:
    return _cipher(tuple(get_config().encryption_key_list))


def seal(value: str) -> str:
    """`value` encrypted with the newest key, as text safe to store."""
    return _current().encrypt(value.encode("utf-8")).decode("ascii")


def open(sealed: str) -> str:
    """The value `seal` sealed. Raises SealError when no key opens it."""
    try:
        return _current().decrypt(sealed.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError) as error:
        raise SealError(
            "This sealed value can't be opened with any key in ENCRYPTION_KEYS."
        ) from error


def rotate(sealed: str) -> str:
    """The value sealed again with the newest key. Always a new token, even
    when the newest key already opens it: check `sealed_with_newest` first to
    skip those."""
    try:
        return _current().rotate(sealed.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError) as error:
        raise SealError(
            "This sealed value can't be opened with any key in ENCRYPTION_KEYS."
        ) from error


def sealed_with_newest(sealed: str) -> bool:
    """Whether the newest key opens it, so rotating it can wait (`rotate`
    would still issue a new token)."""
    keys = get_config().encryption_key_list
    if not keys:
        return False
    try:
        Fernet(keys[0].encode("utf-8")).decrypt(sealed.encode("ascii"))
    except (InvalidToken, UnicodeError):
        return False
    return True


__all__ = ["SealError", "open", "rotate", "seal", "sealed_with_newest"]
