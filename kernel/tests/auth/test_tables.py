"""Auth's tables keep one-time secrets so they can't collide or be read back
(decision 0012), and every foreign key can be followed by an index."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.auth.hashing import keyed_hash
from kernel.db import Database

NOW = datetime.now(UTC)


@pytest_asyncio.fixture(loop_scope="session")
async def tx(database: Database) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back after the test."""
    async with database.sessions() as session:
        yield session
        await session.rollback()


async def _user(db: AsyncSession) -> uuid.UUID:
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:10]}@site.test"
    await db.execute(
        text("INSERT INTO auth_user (id, email, email_normal) VALUES (:id, :e, :e)"),
        {"id": user_id, "e": email},
    )
    return user_id


async def _token(db: AsyncSession, purpose: str, token_hash: str, email: str | None) -> None:
    await db.execute(
        text(
            "INSERT INTO auth_token (id, purpose, token_hash, email_normal, created_at, expires_at)"
            " VALUES (:id, :p, :h, :e, :now, :later)"
        ),
        {
            "id": uuid.uuid4(),
            "p": purpose,
            "h": token_hash,
            "e": email,
            "now": NOW,
            "later": NOW + timedelta(minutes=10),
        },
    )


async def test_two_people_can_hold_the_same_sign_in_code(tx: AsyncSession) -> None:
    await _token(tx, "sign_in_code", "a" * 64, "one@site.test")
    await _token(tx, "sign_in_code", "a" * 64, "two@site.test")  # no clash


async def test_a_sign_in_code_names_its_address(tx: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="sign_in_code_has_email"):
        await _token(tx, "sign_in_code", "b" * 64, None)


async def test_link_tokens_stay_unique(tx: AsyncSession) -> None:
    await _token(tx, "magic_link", "c" * 64, "one@site.test")
    with pytest.raises(IntegrityError, match="uq_auth_token_token_hash"):
        await _token(tx, "reset_password", "c" * 64, "two@site.test")


async def test_recovery_codes_are_unique_per_person(tx: AsyncSession) -> None:
    one, two = await _user(tx), await _user(tx)
    insert = text(
        "INSERT INTO auth_recovery_code (id, user_id, code_hash) VALUES (gen_random_uuid(), :u, :h)"
    )
    await tx.execute(insert, {"u": one, "h": "d" * 64})
    await tx.execute(insert, {"u": two, "h": "d" * 64})  # another person: no clash
    with pytest.raises(IntegrityError, match="uq_auth_recovery_code_user_id"):
        await tx.execute(insert, {"u": one, "h": "d" * 64})


async def test_an_api_key_is_live_or_test(tx: AsyncSession) -> None:
    user = await _user(tx)
    with pytest.raises(IntegrityError, match="mode_known"):
        await tx.execute(
            text(
                "INSERT INTO auth_api_key (id, key_id, mode, user_id, name, secret_hash)"
                " VALUES (gen_random_uuid(), 'abcd1234', 'prod', :u, 'CI', :h)"
            ),
            {"u": user, "h": "e" * 64},
        )


async def test_a_session_keeps_its_user_agent(tx: AsyncSession) -> None:
    columns = (
        await tx.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'auth_session'"
            )
        )
    ).scalars()
    assert "user_agent" in set(columns)


async def test_every_foreign_key_has_an_index(tx: AsyncSession) -> None:
    missing = (await tx.execute(text("""
                SELECT c.conrelid::regclass || '.' || a.attname
                FROM pg_constraint c
                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                WHERE c.contype = 'f' AND NOT EXISTS (
                    SELECT 1 FROM pg_index i
                    WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])
                ORDER BY 1
                """))).scalars()
    assert list(missing) == []


def test_keyed_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    from kernel.config import reset_config

    first = keyed_hash("sign_in_code", "ana@site.test", "123456")
    assert len(first) == 64
    assert first == keyed_hash("sign_in_code", "ana@site.test", "123456")
    assert first != keyed_hash("sign_in_code", "ana@site.test", "123457")
    assert first != keyed_hash("magic_link", "ana@site.test", "123456")
    # The parts can't run into each other.
    assert keyed_hash("a", "bc") != keyed_hash("ab", "c")
    monkeypatch.setenv("SECRET_KEY", "another-key-" + "x7Kp2" * 8)
    reset_config()
    try:
        assert keyed_hash("sign_in_code", "ana@site.test", "123456") != first
    finally:
        monkeypatch.undo()
        reset_config()


async def test_the_seeded_grants_are_the_kernel_manifests(tx: AsyncSession) -> None:
    """SPEC 14.8: permissions are declared in manifests. The migration's seed
    is frozen, so this holds it to kernel.json (audit F51)."""
    import json
    from pathlib import Path

    manifest = json.loads((Path(__file__).parents[2] / "kernel.json").read_text("utf-8"))
    declared = {item["key"]: set(item["default_roles"]) for item in manifest["permissions"]}
    rows = await tx.execute(text("SELECT role_id, permission FROM auth_role_permission"))
    seeded: dict[str, set[str]] = {}
    for role, permission in rows:
        seeded.setdefault(permission, set()).add(role)
    assert seeded == {key: roles for key, roles in declared.items() if roles}
