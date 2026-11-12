"""The kernel's clock: every expiry, timeout and grace period reads it.

`now()` is UTC. The harness's test support can move it forward
(`advance`), so the contract suite can test a 30-minute token or a 14-day
grace period over HTTP without waiting. Nothing in a site ever moves it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_offset = timedelta()


def now() -> datetime:
    return datetime.now(UTC) + _offset


def advance(seconds: float) -> None:
    """Move the clock forward (the harness's test support only)."""
    global _offset
    if seconds < 0:
        raise ValueError("The clock only moves forward.")
    _offset += timedelta(seconds=seconds)


def reset() -> None:
    global _offset
    _offset = timedelta()
