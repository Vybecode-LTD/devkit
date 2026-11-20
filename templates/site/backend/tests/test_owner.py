"""The site's owner, from the server: `python -m app.owner <email>` (decision
0051). The first address becomes the owner and gets a link to set its
password; with an owner, any other address is refused."""

from __future__ import annotations

import asyncio

import pytest

from app import owner
from app.migrations import upgrade
from kernel.config import reset_config


async def test_the_first_owner_gets_a_link_and_a_stranger_is_refused(
    empty_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    monkeypatch.setenv("SITE_URL", "https://site.test")
    reset_config()  # the app's settings, read again with this database
    try:
        assert await asyncio.to_thread(owner.main, ["owner@site.test"]) == 0
        out = capsys.readouterr().out
        assert "owner@site.test is the site's owner" in out
        assert "  https://site.test/auth/reset?token=" in out
        assert await asyncio.to_thread(owner.main, ["someone@site.test"]) == 2
        assert "has an owner already" in capsys.readouterr().err
    finally:
        reset_config()


def test_the_command_says_how_to_use_it(capsys: pytest.CaptureFixture[str]) -> None:
    assert owner.main([]) == 2
    assert "usage: python -m app.owner <email>" in capsys.readouterr().err
