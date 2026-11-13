"""Passwords: how one is kept, and which are refused (SPEC.md 14.2).

Lifted from VybeSite `services/passwords.py`, with the spec's limits.
Following NIST SP 800-63B-4 section 3.1.1.2 and OWASP's Password Storage
Cheat Sheet:

- **12 to 256 characters,** counted after NFC, each code point one character
  (the owner's 12, Q7; 256 bounds the hashing cost). No composition rules,
  no rotation, no hints, no security questions.
- **Not on the bundled common-password list** (`is_common`): 72,969
  passwords of 12 characters or more from four public lists of leaked and
  most-used passwords (NOTICE; `tools/build_common_passwords.py`), compared
  casefolded. Shorter ones are refused by length already.
- **Not a pattern** (`by_rules`, VybeSite's): one character repeated or very
  few different ones, a run along the keyboard or a count, one short piece
  repeated, or little more than the site's name or the person's own address.
- **Not one Have I Been Pwned has seen** (`breached`): only the first five
  characters of the SHA-1 leave the server, and `Add-Padding` pads each
  answer with fake entries, so its size says little about the prefix. When the API can't be reached the password is
  accepted and the miss is logged.
- A refused password is always explained, in words.

**Kept as Argon2id.** The default parameters are argon2-cffi's (RFC 9106's
low-memory profile: 64 MiB, 3 passes, 4 lanes), above OWASP's minimum of
19 MiB, 2 passes, 1 lane, which `Hashing` refuses to go below; a site sets
its own with ARGON2_MEMORY_KIB, ARGON2_TIME_COST and ARGON2_LANES. A hash
made with other parameters is flagged for upgrading (`needs_rehash`).

**Bounded.** Hashing runs on a pool of its own, ARGON2_CONCURRENCY threads
wide (4 by default), since each hash takes tens of milliseconds and its
memory: a flood of sign-ins queues instead of exhausting the host, and a
request that waits more than a few seconds for a slot is answered 503
`kernel.busy`. A check for an account with no password, or against a
stored hash that isn't Argon2, costs one verify against a dummy made when
`Passwords` is, so the time says nothing about which accounts exist.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import hashlib
import itertools
import logging
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import httpx
from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError

from kernel.errors import Problem

if TYPE_CHECKING:
    from kernel.config import KernelConfig

log = logging.getLogger(__name__)
T = TypeVar("T")

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
COMMON = (
    "That's one of the most common passwords, so it's one people try first. "
    "Choose something less predictable: three or four unrelated words work well."
)
CANT_KEEP = (
    "That password has characters that can't be kept, such as a stray half of an emoji. "
    "Type it again, or choose another."
)
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


def keepable(password: str) -> bool:
    """Whether it can be kept at all: UTF-8 can't hold a lone surrogate, which
    JSON can carry (`"\\ud800"`)."""
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


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

    @classmethod
    def from_config(cls, config: KernelConfig) -> Hashing:
        return cls(config.argon2_memory_kib, config.argon2_time_cost, config.argon2_lanes)


def _is_argon2(hashed: str) -> bool:
    try:
        extract_parameters(hashed)
    except InvalidHashError:
        return False
    return True


BUSY = "We're signing a lot of people in right now. Try again in a few seconds."


class Passwords:
    """Hashing and checking with one site's parameters, at most `concurrency`
    at once (a pool of their own), waiting at most `wait_seconds` for a slot."""

    def __init__(
        self, hashing: Hashing | None = None, *, concurrency: int = 4, wait_seconds: float = 5.0
    ) -> None:
        self.hashing = hashing or Hashing()
        self._hasher = self.hashing.hasher()
        self._pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="argon2")
        self._slots = asyncio.Semaphore(concurrency)
        self._wait = wait_seconds
        #: Made now, not on the first unknown account, which would cost that one twice.
        self._dummy = self._hasher.hash("no password is kept here")

    @classmethod
    def from_config(cls, config: KernelConfig) -> Passwords:
        return cls(Hashing.from_config(config), concurrency=config.argon2_concurrency)

    async def _acquire(self) -> None:
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=self._wait)
        except TimeoutError:
            raise Problem("kernel.busy", 503, BUSY, headers={"Retry-After": "5"}) from None

    @contextlib.asynccontextmanager
    async def _slot(self) -> AsyncIterator[None]:
        await self._acquire()
        try:
            yield
        finally:
            self._slots.release()

    async def _run(self, work: Callable[..., T], *args: Any) -> T:
        """`work` on the pool, holding a slot until its thread is done. A
        cancelled caller stops waiting, but the thread can't be stopped, so
        the slot stays taken until it ends: the queue never grows past
        `concurrency` behind the admission timeout."""
        await self._acquire()
        try:
            running = asyncio.get_running_loop().run_in_executor(self._pool, work, *args)
        except BaseException:
            self._slots.release()
            raise

        def done(finished: asyncio.Future[T]) -> None:
            self._slots.release()
            if not finished.cancelled():
                finished.exception()  # read, so a cancelled caller's error isn't "never retrieved"

        running.add_done_callback(done)
        return await asyncio.shield(running)

    async def hash(self, password: str) -> str:
        """The kept form of a password `refusal` has passed. Raises ValueError
        for one that can't be kept."""
        password = normal(password)
        if not keepable(password):
            raise ValueError(CANT_KEEP)
        return await self._run(self._hasher.hash, password)

    def _verify(self, hashed: str, password: str) -> bool:
        try:
            return self._hasher.verify(hashed, password)
        except (VerificationError, InvalidHashError):
            return False

    async def check(self, password: str, hashed: str | None) -> bool:
        """Whether `password` is the one kept. With no hash (an unknown
        account, or one that has no password), a stored hash that isn't
        Argon2, or a password no rule lets be kept (past 256 characters, or
        text UTF-8 can't hold), it still costs one verify, and is False."""
        password = normal(password)
        if (
            hashed is None
            or not _is_argon2(hashed)
            or len(password) > LONGEST
            or not keepable(password)
        ):
            await self._run(self._verify, self._dummy, "x" * SHORTEST)
            return False
        return await self._run(self._verify, hashed, password)

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
    if not keepable(password):
        return CANT_KEEP
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
    letters = left = _letters(password)
    for term in sorted({_letters(t) for t in context} | {"password"}, key=len, reverse=True):
        if len(term) >= 4:
            left = left.replace(term, "")
    # Only when a name or "password" was taken out: a password of symbols or
    # emoji has few letters to begin with, and that's no reason to refuse it.
    if left != letters and len(left) < 8:
        return ABOUT_THIS_SITE
    return None


COMMON_LIST = Path(__file__).resolve().parent / "data" / "common-passwords.txt.gz"


@cache
def _common() -> frozenset[str]:
    with gzip.open(COMMON_LIST, "rt", encoding="utf-8") as lines:
        return frozenset(line.rstrip("\n") for line in lines if line.strip())


def is_common(password: str) -> bool:
    """Whether this password is on the bundled list, casefolded, as typed or
    with its spaces taken out (the lists hold most phrases unspaced)."""
    folded = normal(password).casefold()
    common = _common()
    return folded in common or folded.replace(" ", "") in common


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
    if not keepable(normal(password)):
        return None
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
    if is_common(password):
        return COMMON
    if await breached(password, lookup):
        return BREACHED
    return None
