from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kernel import clock


def test_the_clock_moves_forward_only() -> None:
    try:
        before = clock.now()
        assert before.tzinfo is UTC
        clock.advance(3600)
        assert (clock.now() - before).total_seconds() >= 3600
        with pytest.raises(ValueError, match="only moves forward"):
            clock.advance(-1)
    finally:
        clock.reset()
    assert abs((clock.now() - datetime.now(UTC)).total_seconds()) < 5
