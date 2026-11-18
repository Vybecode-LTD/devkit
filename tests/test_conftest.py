"""The test run's own Postgres helpers (conftest.py).

`_drop` gets rid of a throwaway database even when `DROP DATABASE ... WITH
(FORCE)` is refused. A role without superuser can't end an autovacuum
worker's session, so FORCE fails while one is in the database ("permission
denied to terminate process"). The owner's machine runs the tests as such a
role; CI's is the container's superuser and never sees it. Then `_drop` ends
the role's own sessions and runs a plain DROP DATABASE, which stops
autovacuum by itself. Any other error still fails the run.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import pytest

import conftest


class _ForceRefused:
    """A real admin connection whose FORCE drop is refused, as it is for a
    role without superuser while an autovacuum worker is in the database."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection
        self.statements: list[str] = []

    async def execute(self, query: str, *args: Any) -> str:
        self.statements.append(query)
        if "WITH (FORCE)" in query:
            raise asyncpg.InsufficientPrivilegeError("permission denied to terminate process")
        return await self._connection.execute(query, *args)

    async def close(self) -> None:
        await self._connection.close()


async def _exists(server_url: str, name: str) -> bool:
    check = await asyncpg.connect(conftest._plain(server_url))
    try:
        return bool(await check.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name))
    finally:
        await check.close()


async def test_drop_ends_its_own_sessions_when_force_is_refused(
    server_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = f"mechframe_drop_{uuid.uuid4().hex[:12]}"
    await conftest._create(name)
    # A session of the test role's own still in the database, as a pool a
    # test forgot to close would leave one.
    left_open = await asyncpg.connect(conftest._plain(conftest._with_database(server_url, name)))
    admins: list[_ForceRefused] = []

    async def refusing_admin() -> _ForceRefused:
        admin = _ForceRefused(await asyncpg.connect(conftest._plain(server_url)))
        admins.append(admin)
        return admin

    monkeypatch.setattr(conftest, "_admin", refusing_admin)
    try:
        assert await _exists(server_url, name)  # the positive control
        await conftest._drop(name)
        assert not await _exists(server_url, name)
        assert "WITH (FORCE)" in admins[0].statements[0]  # FORCE is still tried first
    finally:
        monkeypatch.undo()
        left_open.terminate()
        await conftest._drop(name)


class _FakeAdmin:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.statements: list[str] = []
        self.closed = False

    async def execute(self, query: str, *args: Any) -> str:
        self.statements.append(query)
        raise self._error

    async def close(self) -> None:
        self.closed = True


async def test_drop_lets_any_other_error_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """FORCE is also refused while prepared transactions hold the database.
    That is a real leak, so it fails the run rather than being worked round."""
    fake = _FakeAdmin(asyncpg.ObjectInUseError("database is being used by prepared transactions"))

    async def admin() -> _FakeAdmin:
        return fake

    monkeypatch.setattr(conftest, "_admin", admin)
    with pytest.raises(asyncpg.ObjectInUseError):
        await conftest._drop("mechframe_never_made")
    assert len(fake.statements) == 1  # nothing else was tried
    assert fake.closed
