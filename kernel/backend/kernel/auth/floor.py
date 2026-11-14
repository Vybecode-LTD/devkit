"""The answer floor (SPEC.md 14.6; decisions 0021 and 0022).

A route that must not say whether an account exists, and has no Argon2 hash
to hide its work behind (a code ask, a try at a code, a reset request),
answers no sooner than `ANSWER_FLOOR` after it started. The work a known
address costs is a few milliseconds of queries, tens on a slow database, so
the floor hides it with room to spare. Call `wait_out` after the commit, so
the sleep holds no database connection.
"""

from __future__ import annotations

import asyncio
import time

#: Seconds, real time.
ANSWER_FLOOR = 0.2
#: asyncio runs a timer up to this early (`BaseEventLoop._clock_resolution`).
_TICK = time.get_clock_info("monotonic").resolution


def start() -> float:
    """The moment to measure the floor from."""
    return time.perf_counter()


async def wait_out(started: float) -> None:
    """Sleep out what is left of the floor since `started`. asyncio may wake
    a sleeper up to one tick of its clock early (about 16 ms on Windows), so
    the sleep is a tick longer."""
    left = ANSWER_FLOOR - (time.perf_counter() - started)
    if left > 0:
        await asyncio.sleep(left + _TICK)


__all__ = ["ANSWER_FLOOR", "start", "wait_out"]
