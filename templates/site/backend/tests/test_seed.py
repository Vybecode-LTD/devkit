"""The site's seed data: `python -m app.seed` (MechFrame's hook 4, decision
0052). It refuses unless MECHFRAME_ALLOW_SEED=1 is in the environment, which
`.railway/railway.ts` never sets; then it seeds the modules and the site's own
`app/site/seed.py` last, and a second run changes nothing."""

from __future__ import annotations

import asyncio

import pytest

from app import seed
from app.migrations import upgrade
from kernel.config import reset_config


def test_without_the_variable_it_refuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MECHFRAME_ALLOW_SEED", raising=False)
    assert seed.main([]) == 2
    assert "MECHFRAME_ALLOW_SEED=1" in capsys.readouterr().err


async def test_it_seeds_the_site_last_and_twice_the_same(
    empty_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    monkeypatch.setenv("MECHFRAME_ALLOW_SEED", "1")
    reset_config()  # the app's settings, read again with this database
    try:
        for _ in range(2):
            assert await asyncio.to_thread(seed.main, []) == 0
            assert capsys.readouterr().out.strip().endswith("Seeded: site.")
    finally:
        reset_config()


def test_the_command_takes_no_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert seed.main(["extra"]) == 2
    assert "usage: python -m app.seed" in capsys.readouterr().err
