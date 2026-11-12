"""Passwords: how one is kept, and which are refused (SPEC.md 14.2).

Lifted from VybeSite `services/passwords.py`, with the spec's limits.
Following NIST SP 800-63B-4 section 3.1.1.2 and OWASP's Password Storage
Cheat Sheet:

- **12 to 256 characters,** counted after NFC, each code point one character
  (the owner's 12, Q7; 256 bounds the hashing cost). No composition rules,
  no rotation, no hints, no security questions.
- **Not a pattern** (`by_rules`, VybeSite's): one character repeated or very
  few different ones, a run along the keyboard or a count, one short piece
  repeated, or little more than the site's name or the person's own address.
- **Not one Have I Been Pwned has seen** (`breached`): only the first five
  characters of the SHA-1 leave the server, and `Add-Padding` makes every
  answer the same size. When the API can't be reached the password is
  accepted and the miss is logged.
- A refused password is always explained, in words.

**Kept as Argon2id.** The default parameters are argon2-cffi's (RFC 9106's
low-memory profile: 64 MiB, 3 passes, 4 lanes), above OWASP's minimum of
19 MiB, 2 passes, 1 lane, which `Hashing` refuses to go below. A hash made
with weaker parameters is upgraded at the next sign-in (`needs_rehash`).
Hashing runs on a thread: it takes tens of milliseconds and must not hold
the event loop. A check for an account with no password costs one hash too,
so the time says nothing about which accounts exist.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import logging
import unicodedata
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

log = logging.getLogger(__name__)

SHORTEST, LONGEST = 12, 256
RANGE_URL = "https://api.pwnedpasswords.com/range/"
LOOKUP_SECONDS = 3.0

#: OWASP's floor for Argon2id: 19 MiB, 2 passes, 1 lane.
FLOOR_MEMORY_KIB, FLOOR_TIME, FLOOR_LANES = 19 * 1024, 2, 1

TOO_SHORT = f"Use at least {SHORTEST} characters. Three or four unrelated words work well."
TOO_LONG = f"Use at most {LONGEST} characters."
BREACHED = (
    "That password has appeared in a data breach, so it's one people try first. "
    "Choose one you haven't used anywhere else."
)
FEW_CHARACTERS = "That's mostly one character repeated. Use more different ones."
A_RUN = "That's a run along the keyboard or a count, like qwerty or 123456. Choose something less regular."
REPEATED = "That's one short piece repeated. Choose something that doesn't repeat."
ABOUT_THIS_SITE = (
    "That's little more than this site's name or your own email address. "
    "Choose something that isn't about either."
)

_LINES = (
    "01234567890",
    "abcdefghijklmnopqrstuvwxyz",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik9ol0p",
)
_NEIGHBOURS = frozenset(
    pair for line in _LINES for a, b in itertools.pairwise(line) for pair in ((a, b), (b, a))
)


def normal(password: str) -> str:
    """A password as it is hashed and judged: NFC, so one typed on a phone
    and on a laptop is the same string."""
    return unicodedata.normalize("NFC", password or "")


# --- keeping one --------------------------------------------------------------------


@dataclass(frozen=True)
class Hashing:
    """Argon2id's parameters for this site."""

    memory_kib: int = 64 * 1024
    time_cost: int = 3
    lanes: int = 4

    def __post_init__(self) -> None:
        if (
            self.memory_kib < FLOOR_MEMORY_KIB
            or self.time_cost < FLOOR_TIME
            or self.lanes < FLOOR_LANES
        ):
            raise ValueError(
                "Argon2id below OWASP's minimum (19 MiB, 2 passes, 1 lane) isn't allowed."
            )

    def hasher(self) -> PasswordHasher:
        return PasswordHasher(
            memory_cost=self.memory_kib, time_cost=self.time_cost, parallelism=self.lanes
        )


class Passwords:
    """Hashing and checking with one site's parameters."""

    def __init__(self, hashing: Hashing | None = None) -> None:
        self.hashing = hashing or Hashing()
        self._hasher = self.hashing.hasher()
        self._dummy: str | None = None

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, normal(password))

    def _verify(self, hashed: str, password: str) -> bool:
        try:
            return self._hasher.verify(hashed, password)
        except (VerificationError, InvalidHashError):
            return False

    async def check(self, password: str, hashed: str | None) -> bool:
        """Whether `password` is the one kept. With no hash (an unknown
        account, or one that has no password) it still costs one check."""
        if hashed is None:
            if self._dummy is None:
                self._dummy = await asyncio.to_thread(self._hasher.hash, "no password is kept here")
            await asyncio.to_thread(self._verify, self._dummy, normal(password))
            return False
        return await asyncio.to_thread(self._verify, hashed, normal(password))

    def needs_rehash(self, hashed: str) -> bool:
        """Whether a kept hash uses other parameters than the site's now."""
        try:
            return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError:
            return True


# --- which are refused ----------------------------------------------------------------


def _letters(text: str) -> str:
    """Its letters and digits alone, in any script, folded."""
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum())


def by_rules(password: str, context: Iterable[str] = ()) -> str | None:
    """Why this password is refused, in words, or None: the length, then the
    patterns. `context` is what a guesser starts from: the site's name, its
    domain, the person's address."""
    password = normal(password)
    if len(password) < SHORTEST:
        return TOO_SHORT
    if len(password) > LONGEST:
        return TOO_LONG
    folded = password.casefold()
    if len(set(folded)) < 5:
        return FEW_CHARACTERS
    steps = list(itertools.pairwise(folded))
    regular = sum(1 for a, b in steps if a == b or (a, b) in _NEIGHBOURS)
    if regular >= 0.8 * len(steps):
        return A_RUN
    for period in range(1, (2 * len(folded)) // 3 + 1):
        if all(folded[i] == folded[i % period] for i in range(len(folded))):
            return REPEATED
    left = _letters(password)
    for term in sorted({_letters(t) for t in context} | {"password"}, key=len, reverse=True):
        if len(term) >= 4:
            left = left.replace(term, "")
    if len(left) < 8:
        return ABOUT_THIS_SITE
    return None


async def ask_range(prefix: str) -> str | None:
    """Have I Been Pwned's answer for a five-character SHA-1 prefix, or None
    when it can't be had."""
    try:
        async with httpx.AsyncClient(timeout=LOOKUP_SECONDS) as client:
            answer = await client.get(RANGE_URL + prefix, headers={"Add-Padding": "true"})
    except httpx.HTTPError as error:
        log.warning(
            "breach lookup failed (%s); the password is judged by the rules alone",
            type(error).__name__,
        )
        return None
    if answer.status_code != 200:
        log.warning(
            "breach lookup answered %s; the password is judged by the rules alone",
            answer.status_code,
        )
        return None
    return answer.text


RangeLookup = Callable[[str], Awaitable[str | None]]


async def breached(password: str, lookup: RangeLookup = ask_range) -> bool | None:
    """Whether Have I Been Pwned has seen this password: None when it can't
    be asked."""
    # SHA-1 is the range API's key, not a protection here.
    digest = (
        hashlib.sha1(normal(password).encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    )
    listed = await lookup(digest[:5])
    if listed is None:
        return None
    for line in listed.splitlines():
        suffix, _, count = line.strip().partition(":")
        if suffix.upper() == digest[5:] and count.strip() not in ("", "0"):
            return True
    return False


async def refusal(
    password: str, context: Iterable[str] = (), *, lookup: RangeLookup = ask_range
) -> str | None:
    """Why this password can't be kept, in words, or None when it can."""
    reason = by_rules(password, context)
    if reason is not None:
        return reason
    if await breached(password, lookup):
        return BREACHED
    return None
