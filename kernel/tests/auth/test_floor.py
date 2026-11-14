"""The answer floor (`kernel/auth/floor.py`; decisions 0021 and 0022). The
routes that use it test it through HTTP; these test the floor alone."""

from __future__ import annotations

import time

from kernel.auth import floor


async def test_it_waits_out_what_is_left() -> None:
    started = floor.start()
    await floor.wait_out(started)
    assert time.perf_counter() - started >= floor.ANSWER_FLOOR


async def test_work_past_the_floor_waits_no_longer() -> None:
    started = floor.start() - floor.ANSWER_FLOOR - 1  # the work took longer
    before = time.perf_counter()
    await floor.wait_out(started)
    assert time.perf_counter() - before < floor.ANSWER_FLOOR / 4
