"""SPEC 10: an upgrade stops before a migration marked `destructive = True`
whose branch is already in the database, and names it, until it's named back
(decision 0049). A deploy's pre-deploy step fails there, the database as it
was, and the site's owner runs it by hand after a backup.

The probe is a module branch written for each test: `probe_0001`, `probe_0002`
and on, each marked as the test says, the first depending on the kernel's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

import asyncpg
import pytest

from harness import layout, migrations
from kernel import migrate

REVISION = '''"""Probe step {number}."""

import sqlalchemy as sa
from alembic import op

revision = "probe_{number:04d}"
down_revision = {down}
branch_labels = {labels}
depends_on = {depends}

destructive = {destructive}


def upgrade() -> None:
    op.create_table("probe_step_{number}", sa.Column("id", sa.Integer, primary_key=True))


def downgrade() -> None:
    op.drop_table("probe_step_{number}")
'''

Probe = Callable[[Sequence[object]], Path]


@pytest.fixture
def probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Probe:
    """Writes the probe branch, one revision per mark, and adds it to the
    harness's migrations."""

    def make(marks: Sequence[object]) -> Path:
        branch = tmp_path / "probe"
        branch.mkdir()
        for number, mark in enumerate(marks, start=1):
            text = REVISION.format(
                number=number,
                down=repr(None if number == 1 else f"probe_{number - 1:04d}"),
                labels=repr(("probe",)) if number == 1 else "None",
                depends=repr("kernel_0001") if number == 1 else "None",
                destructive=repr(mark),
            )
            (branch / f"{number:04d}_probe.py").write_text(text, "utf-8")
        found = [*layout.migration_dirs(), branch]
        monkeypatch.setattr(migrations, "migration_dirs", lambda: found)
        return branch

    return make


async def _versions(url: str) -> set[str]:
    """The revisions alembic_version holds (none on a database never migrated)."""
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        if not await connection.fetchval("SELECT to_regclass('alembic_version') IS NOT NULL"):
            return set()
        rows = await connection.fetch("SELECT version_num FROM alembic_version")
    finally:
        await connection.close()
    return {row["version_num"] for row in rows}


async def _upgrade(url: str, target: str = "heads", **confirm: migrate.Confirm) -> None:
    await asyncio.to_thread(migrations.upgrade, url, target, **confirm)


async def test_a_new_database_runs_a_destructive_migration_unasked(
    empty_database_url: str, probe: Probe
) -> None:
    """Every table it could touch is made in the same upgrade: nothing yet to lose."""
    probe([False, True])
    await _upgrade(empty_database_url)
    assert "probe_0002" in await _versions(empty_database_url)


async def test_a_module_just_added_runs_its_destructive_migration_unasked(
    empty_database_url: str, probe: Probe
) -> None:
    """`mechframe add` on a site already running: the module's branch is new."""
    await _upgrade(empty_database_url)
    probe([True, True])
    await _upgrade(empty_database_url)
    assert "probe_0002" in await _versions(empty_database_url)


async def test_an_upgrade_stops_before_a_destructive_migration_and_names_it(
    empty_database_url: str, probe: Probe
) -> None:
    probe([False, True])
    await _upgrade(empty_database_url, "probe_0001")
    before = await _versions(empty_database_url)
    with pytest.raises(migrate.DestructiveMigrationRefused) as refused:
        await _upgrade(empty_database_url)
    assert [script.revision for script in refused.value.scripts] == ["probe_0002"]
    assert refused.value.target == "heads"
    assert await _versions(empty_database_url) == before  # not even the kernel's ran


async def test_a_destructive_migration_named_back_runs(
    empty_database_url: str, probe: Probe
) -> None:
    probe([False, True, False])
    await _upgrade(empty_database_url, "probe_0001")
    await _upgrade(empty_database_url, confirm_destructive=["probe_0002"])
    assert "probe_0003" in await _versions(empty_database_url)


async def test_a_confirmation_covers_only_the_migrations_it_names(
    empty_database_url: str, probe: Probe
) -> None:
    """So one left in a command can't let a later one through."""
    probe([False, True, True])
    await _upgrade(empty_database_url, "probe_0001")
    before = await _versions(empty_database_url)
    with pytest.raises(migrate.DestructiveMigrationRefused) as refused:
        await _upgrade(empty_database_url, confirm_destructive=["probe_0002"])
    assert [script.revision for script in refused.value.scripts] == ["probe_0003"]
    assert [script.revision for script in refused.value.flagged] == ["probe_0002", "probe_0003"]
    assert await _versions(empty_database_url) == before


async def test_upgrades_short_of_it_and_past_it_need_no_confirmation(
    empty_database_url: str, probe: Probe
) -> None:
    probe([False, True, False])
    await _upgrade(empty_database_url, "probe_0001")
    await _upgrade(empty_database_url, "probe_0002", confirm_destructive="probe_0002")
    await _upgrade(empty_database_url)
    assert "probe_0003" in await _versions(empty_database_url)


async def test_a_throwaway_database_confirms_them_all(
    empty_database_url: str, probe: Probe
) -> None:
    """The tests that step a revision down and back up: `confirm=True`."""
    probe([False, True, True])
    await _upgrade(empty_database_url, "probe_0001")
    await _upgrade(empty_database_url, confirm_destructive=True)
    assert "probe_0003" in await _versions(empty_database_url)


async def test_any_true_value_marks_a_migration_destructive(
    empty_database_url: str, probe: Probe
) -> None:
    """A mark other than False (a word, a 1) errs toward asking."""
    probe([False, "yes"])
    await _upgrade(empty_database_url, "probe_0001")
    with pytest.raises(migrate.DestructiveMigrationRefused):
        await _upgrade(empty_database_url)


def _main(*argv: str) -> int:
    return migrations.main(list(argv))


async def test_the_command_refuses_and_says_how_to_run_it_by_hand(
    empty_database_url: str,
    probe: Probe,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    branch = probe([False, True])
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    assert await asyncio.to_thread(_main, "upgrade", "probe_0001") == 0
    before = await _versions(empty_database_url)
    capsys.readouterr()

    assert await asyncio.to_thread(_main, "upgrade") == 2
    err = capsys.readouterr().err
    assert "destructive = True" in err
    assert "probe_0002" in err
    assert str(branch / "0002_probe.py") in err
    assert "Probe step 2." in err
    assert "Nothing was migrated." in err
    assert "python -m harness.migrations upgrade --confirm-destructive probe_0002" in err
    assert await _versions(empty_database_url) == before

    assert await asyncio.to_thread(_main, "upgrade", "--confirm-destructive", "probe_0002") == 0
    assert "Running probe_0002, marked destructive = True, as confirmed." in capsys.readouterr().out
    assert "probe_0002" in await _versions(empty_database_url)


async def test_the_command_takes_names_apart_by_commas_and_says_its_target(
    empty_database_url: str,
    probe: Probe,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe([False, True, True])
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    assert await asyncio.to_thread(_main, "upgrade", "probe_0001") == 0
    capsys.readouterr()
    assert await asyncio.to_thread(_main, "upgrade", "probe_0003") == 2
    err = capsys.readouterr().err
    assert (
        "python -m harness.migrations upgrade probe_0003"
        " --confirm-destructive probe_0002,probe_0003" in err
    )
    assert (
        await asyncio.to_thread(
            _main, "upgrade", "probe_0003", "--confirm-destructive", "probe_0002,probe_0003"
        )
        == 0
    )
    assert "probe_0003" in await _versions(empty_database_url)


async def test_a_name_that_matches_nothing_is_said(
    empty_database_url: str,
    probe: Probe,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A typo confirms nothing, and the refusal shows it."""
    probe([False, True])
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    assert await asyncio.to_thread(_main, "upgrade", "probe_0001") == 0
    capsys.readouterr()
    assert await asyncio.to_thread(_main, "upgrade", "--confirm-destructive", "probe_002") == 2
    err = capsys.readouterr().err
    assert "Named, but not a destructive migration this upgrade runs: probe_002" in err
    assert "--confirm-destructive probe_0002" in err


def test_only_upgrade_takes_a_confirmation(capsys: pytest.CaptureFixture[str]) -> None:
    assert _main("downgrade", "--confirm-destructive", "probe_0002") == 2
    assert "only upgrade takes --confirm-destructive" in capsys.readouterr().err
    assert _main("upgrade", "--confirm-destructive") == 2  # a name is required
    assert "usage:" in capsys.readouterr().err


async def test_a_name_beside_the_ones_it_needs_is_said_and_the_upgrade_runs(
    empty_database_url: str,
    probe: Probe,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe([False, True])
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    assert await asyncio.to_thread(_main, "upgrade", "probe_0001") == 0
    capsys.readouterr()
    confirmed = ("upgrade", "--confirm-destructive", "probe_0002,probe_9999")
    assert await asyncio.to_thread(_main, *confirmed) == 0
    out = capsys.readouterr().out
    assert "Named, but not a destructive migration this upgrade runs: probe_9999" in out
    assert "probe_0002" in await _versions(empty_database_url)


MERGE = '''"""Probe merge."""

revision = "probe_0004"
down_revision = ("probe_0002", "probe_0003")
branch_labels = None
depends_on = None

destructive = True


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
'''


async def test_a_merge_new_to_the_database_runs_unasked(
    empty_database_url: str, probe: Probe
) -> None:
    """Both of its branches lead back to one revision: each is walked once."""
    branch = probe([False, False])
    third = (branch / "0002_probe.py").read_text("utf-8")
    third = third.replace('"probe_0002"', '"probe_0003"').replace("probe_step_2", "probe_step_3")
    (branch / "0003_probe.py").write_text(third, "utf-8")
    (branch / "0004_probe.py").write_text(MERGE, "utf-8")
    await _upgrade(empty_database_url)
    assert await _versions(empty_database_url) >= {"probe_0004"}


async def test_the_other_verbs_reach_alembic(
    empty_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    assert await asyncio.to_thread(_main, "upgrade") == 0
    assert await asyncio.to_thread(_main, "current") == 0
    assert await asyncio.to_thread(_main, "history") == 0
    out = capsys.readouterr().out
    assert "(head)" in out
    assert await asyncio.to_thread(_main, "downgrade", "base") == 0
    assert await _versions(empty_database_url) == set()
