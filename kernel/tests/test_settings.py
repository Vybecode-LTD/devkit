"""Versioned module settings, merged on save (SPEC.md section 7)."""

from __future__ import annotations

import asyncio
import uuid
import zlib
from datetime import date
from enum import StrEnum

import pytest
from pydantic import BaseModel, Field, SecretBytes, SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.auth.models import User
from kernel.db import Database
from kernel.errors import Problem
from kernel.models import Setting
from kernel.settings import LOCK_CLASS, SettingsRegistry, secret_fields

from .conftest import unique_id


class Blog(BaseModel):
    title: str = "Blog"
    posts_per_page: int = Field(default=10, ge=1, le=100)
    topics: list[str] = []
    api_key: SecretStr | None = None


@pytest.fixture
def registry() -> tuple[SettingsRegistry, str]:
    found = SettingsRegistry()
    module_id = unique_id("blog")
    found.register(module_id, Blog)
    return found, module_id


def test_secret_fields() -> None:
    assert secret_fields(Blog) == {"api_key"}


def test_every_field_needs_a_default() -> None:
    class Bad(BaseModel):
        name: str

    with pytest.raises(ValueError, match="needs a default"):
        SettingsRegistry().register("bad", Bad)


async def test_defaults_before_any_save(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    assert await found.for_module(db, module_id) == Blog()
    assert await found.form(db, module_id) == {
        "version": 0,
        "values": {
            "title": "Blog",
            "posts_per_page": 10,
            "topics": [],
            "api_key": {"kept": False, "changes": 0},
        },
    }
    assert await found.history(db, module_id) == []


async def test_unknown_module(db: AsyncSession) -> None:
    with pytest.raises(Problem) as caught:
        await SettingsRegistry().for_module(db, "nothing")
    assert (caught.value.status, caught.value.code) == (404, "kernel.settings_unknown")


async def test_save_records_a_version(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    who = uuid.uuid4()
    email = f"{who.hex}@site.test"
    db.add(User(id=who, email=email, email_normal=email))
    await db.commit()
    saved = await found.save(
        db, module_id, {"title": "News", "posts_per_page": 5}, version=0, by=who
    )
    assert (saved.version, saved.changed, saved.merged) == (1, ["posts_per_page", "title"], [])
    current = await found.for_module(db, module_id)
    assert isinstance(current, Blog)
    assert (current.title, current.posts_per_page) == ("News", 5)
    (entry,) = await found.history(db, module_id)
    assert (entry["number"], entry["changed"], entry["via"], entry["saved_by_id"]) == (
        1,
        ["posts_per_page", "title"],
        "form",
        who,
    )


async def test_a_save_that_changes_nothing_keeps_the_version(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    saved = await found.save(db, module_id, {"title": "Blog", "posts_per_page": 10}, version=0)
    assert (saved.version, saved.changed) == (0, [])


async def test_secrets_are_sealed_masked_and_kept(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    await found.save(db, module_id, {"api_key": "sk_live_secret"}, version=0)
    row = (await db.execute(select(Setting).where(Setting.module_id == module_id))).scalar_one()
    assert "sk_live_secret" not in str(row.values)
    current = await found.for_module(db, module_id)
    assert isinstance(current, Blog)
    assert current.api_key is not None
    assert current.api_key.get_secret_value() == "sk_live_secret"
    form = await found.form(db, module_id)
    assert form["values"]["api_key"] == {"kept": True, "changes": 1}
    # None keeps it; the form never sends the secret back.
    saved = await found.save(db, module_id, {"title": "News", "api_key": None}, version=1)
    assert saved.changed == ["title"]
    again = await found.for_module(db, module_id)
    assert isinstance(again, Blog)
    assert again.api_key is not None
    # "" removes it.
    saved = await found.save(db, module_id, {"api_key": ""}, version=2)
    assert saved.changed == ["api_key"]
    assert (await found.form(db, module_id))["values"]["api_key"] == {"kept": False, "changes": 2}


async def test_a_stale_save_merges_fields_only_others_changed(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    form = {"title": "Blog", "posts_per_page": 10, "topics": []}
    await found.save(db, module_id, {**form, "title": "Theirs"}, version=0)  # someone else
    saved = await found.save(db, module_id, {**form, "posts_per_page": 20}, version=0)  # you
    assert (saved.version, saved.changed, saved.merged) == (2, ["posts_per_page"], ["title"])
    current = await found.for_module(db, module_id)
    assert isinstance(current, Blog)
    assert (current.title, current.posts_per_page) == ("Theirs", 20)


async def test_both_changing_one_field_is_a_conflict(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    await found.save(db, module_id, {"title": "Theirs"}, version=0)
    await db.commit()
    with pytest.raises(Problem) as caught:
        await found.save(db, module_id, {"title": "Yours", "posts_per_page": 3}, version=0)
    await db.rollback()
    problem = caught.value
    assert (problem.status, problem.code, problem.extra["version"]) == (
        409,
        "kernel.settings_conflict",
        1,
    )
    assert problem.extra["conflicts"] == [{"field": "title", "yours": "Yours", "theirs": "Theirs"}]
    current = await found.for_module(db, module_id)
    assert isinstance(current, Blog)
    assert (current.title, current.posts_per_page) == ("Theirs", 10)  # nothing of yours saved


async def test_both_typing_a_secret_is_a_conflict(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    await found.save(db, module_id, {"api_key": "theirs"}, version=0)
    with pytest.raises(Problem) as caught:
        await found.save(db, module_id, {"api_key": "yours"}, version=0)
    await db.rollback()
    assert caught.value.extra["conflicts"] == [{"field": "api_key", "secret": True}]
    assert "theirs" not in str(caught.value.body())
    assert "yours" not in str(caught.value.body())


async def test_refusals(db: AsyncSession, registry: tuple[SettingsRegistry, str]) -> None:
    found, module_id = registry
    with pytest.raises(Problem) as ahead:
        await found.save(db, module_id, {"title": "x"}, version=3)
    assert (ahead.value.status, ahead.value.code) == (422, "kernel.settings_version_unknown")
    await db.rollback()
    with pytest.raises(Problem) as unknown:
        await found.save(db, module_id, {"colour": "red"}, version=0)
    assert unknown.value.errors == {"colour": ["Not a setting."]}
    with pytest.raises(Problem) as invalid:
        await found.save(db, module_id, {"posts_per_page": 0}, version=0)
    await db.rollback()
    assert (invalid.value.code, list(invalid.value.errors)) == (
        "kernel.invalid_request",
        ["posts_per_page"],
    )
    assert (await found.form(db, module_id))["version"] == 0


async def test_two_first_saves_at_once_both_land(
    database: Database, registry: tuple[SettingsRegistry, str]
) -> None:
    """The advisory lock orders them: the second merges onto the first."""
    found, module_id = registry

    async def save(changes: dict[str, object]) -> int:
        async with database.sessions() as session:
            return (await found.save(session, module_id, changes, version=0)).version

    versions = sorted(await asyncio.gather(save({"title": "A"}), save({"posts_per_page": 7})))
    assert versions == [1, 2]
    async with database.sessions() as session:
        current = await found.for_module(session, module_id)
    assert isinstance(current, Blog)
    assert (current.title, current.posts_per_page) == ("A", 7)


# --- secrets typed in code, and secrets the registry can't seal (audit F12) ---


async def test_a_secret_passed_as_secretstr_is_kept_as_typed(
    db: AsyncSession, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    await found.save(db, module_id, {"api_key": SecretStr("sk_live_REAL")}, version=0, via="cli")
    current = await found.for_module(db, module_id)
    assert isinstance(current, Blog)
    assert current.api_key is not None
    assert current.api_key.get_secret_value() == "sk_live_REAL"


class _Inner(BaseModel):
    token: SecretStr | None = None


class _Nested(BaseModel):
    inner: _Inner = _Inner()


class _Bytes(BaseModel):
    key: SecretBytes | None = None


class _Listed(BaseModel):
    keys: list[SecretStr] = []


class _Mixed(BaseModel):
    key: SecretStr | int = 0


@pytest.mark.parametrize("model", [_Nested, _Bytes, _Listed, _Mixed])
def test_secrets_it_cant_seal_are_refused_at_register(model: type[BaseModel]) -> None:
    with pytest.raises(ValueError, match="SecretStr field of its own"):
        SettingsRegistry().register("bad", model)


class _Required(BaseModel):
    signing_secret: SecretStr = SecretStr("")


async def test_a_secret_without_none_saves_reads_and_removes(db: AsyncSession) -> None:
    found, module_id = SettingsRegistry(), unique_id("hooks")
    found.register(module_id, _Required)
    assert secret_fields(_Required) == {"signing_secret"}
    await found.save(db, module_id, {"signing_secret": "whsec_typed"}, version=0)
    current = await found.for_module(db, module_id)
    assert isinstance(current, _Required)
    assert current.signing_secret.get_secret_value() == "whsec_typed"
    saved = await found.save(db, module_id, {"signing_secret": ""}, version=1)
    assert saved.changed == ["signing_secret"]
    removed = await found.for_module(db, module_id)
    assert isinstance(removed, _Required)
    assert removed.signing_secret.get_secret_value() == ""  # back to its default


# --- the merge compares normalised values (audit F13) ---


class Tone(StrEnum):
    CALM = "calm"
    LOUD = "loud"


class Shop(BaseModel):
    posts_per_page: int = 10
    opens: date = date(2026, 1, 1)
    tone: Tone = Tone.CALM


async def test_a_stale_form_sending_old_values_as_text_isnt_a_conflict(db: AsyncSession) -> None:
    found, module_id = SettingsRegistry(), unique_id("shop")
    found.register(module_id, Shop)
    theirs = {"posts_per_page": 12, "opens": "2026-03-01", "tone": "loud"}
    await found.save(db, module_id, theirs, version=0)
    # A form read at version 0 sends the values it was shown, as text and objects.
    stale = {"posts_per_page": "10", "opens": "2026-01-01T00:00:00", "tone": Tone.CALM}
    saved = await found.save(db, module_id, stale, version=0)
    assert (saved.version, saved.changed) == (1, [])
    assert saved.merged == ["opens", "posts_per_page", "tone"]
    current = await found.for_module(db, module_id)
    assert current == Shop(posts_per_page=12, opens=date(2026, 3, 1), tone=Tone.LOUD)


async def test_a_stale_change_sent_as_text_still_lands(db: AsyncSession) -> None:
    found, module_id = SettingsRegistry(), unique_id("shop")
    found.register(module_id, Shop)
    await found.save(db, module_id, {"tone": "loud"}, version=0)
    saved = await found.save(db, module_id, {"posts_per_page": "25", "tone": "calm"}, version=0)
    assert (saved.version, saved.changed, saved.merged) == (2, ["posts_per_page"], ["tone"])


# --- the advisory lock's lifetime (audit F45) ---


async def _lock_is_free(database: Database, module_id: str) -> bool:
    key = zlib.crc32(module_id.encode("utf-8")) - 2**31
    async with database.sessions() as other:
        free = (
            await other.execute(
                text("SELECT pg_try_advisory_xact_lock(:kind, :key)"),
                {"kind": LOCK_CLASS, "key": key},
            )
        ).scalar_one()
        await other.rollback()
    return bool(free)


async def test_commit_false_holds_the_lock_until_the_caller_commits(
    database: Database, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    async with database.sessions() as session:
        saved = await found.save(session, module_id, {"title": "Mine"}, version=0, commit=False)
        assert saved.version == 1
        assert not await _lock_is_free(database, module_id)
        await session.commit()
    assert await _lock_is_free(database, module_id)
    async with database.sessions() as session:
        assert (await found.form(session, module_id))["values"]["title"] == "Mine"


async def test_a_save_that_changes_nothing_lets_the_lock_go(
    database: Database, registry: tuple[SettingsRegistry, str]
) -> None:
    found, module_id = registry
    async with database.sessions() as session:
        saved = await found.save(session, module_id, {"title": "Blog"}, version=0)
        assert saved.changed == []
        assert await _lock_is_free(database, module_id)
