"""Passwords: kept with Argon2id, refused by length, pattern and breach (SPEC.md 14.2)."""

from __future__ import annotations

import hashlib
import logging

import httpx
import pytest

from kernel.auth import passwords as pw
from kernel.auth.passwords import Hashing, Passwords, breached, by_rules, normal, refusal

FAST = Hashing(memory_kib=pw.FLOOR_MEMORY_KIB, time_cost=2, lanes=1)
PASSWORD = "quiet orbit lantern 4471 marsh"


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("short one", pw.TOO_SHORT),
        ("x" * 257, pw.TOO_LONG),
        ("aaaaaaaaaaaaaaaa", pw.FEW_CHARACTERS),
        ("ababababababab", pw.FEW_CHARACTERS),
        ("qwertyuiopasdf", pw.A_RUN),
        ("1234567890123", pw.A_RUN),
        ("horsebathorsebat", pw.REPEATED),
        ("devkit.test password", pw.ABOUT_THIS_SITE),
        ("correct horse battery staple", None),
        ("über-straße-café-wörter", None),
    ],
)
def test_rules(password: str, reason: str | None) -> None:
    assert by_rules(password, ["devkit.test", "DevKit site"]) == reason


def test_twelve_counts_code_points_after_nfc() -> None:
    decomposed = "é" * 6 + "zxqwvbn"  # é as e + combining accent: NFC makes it one
    assert len(decomposed) == 19
    assert len(normal(decomposed)) == 13
    assert by_rules("é" * 4 + "zqxjk" + "ü" * 2) == pw.TOO_SHORT  # 11 after NFC


def test_the_site_and_address_are_context() -> None:
    assert by_rules("ana.lopez@site.test99", ["ana.lopez@site.test"]) == pw.ABOUT_THIS_SITE
    assert by_rules("ana.lopez@site.test99") is None


async def _lookup_listing(password: str, count: int) -> pw.RangeLookup:
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()

    async def lookup(prefix: str) -> str | None:
        assert prefix == digest[:5]
        return f"0000000000000000000000000000000000A:0\n{digest[5:]}:{count}\n"

    return lookup


async def test_breached_passwords_are_refused() -> None:
    lookup = await _lookup_listing("correct horse battery staple", 1234)
    assert await breached("correct horse battery staple", lookup) is True
    assert await refusal("correct horse battery staple", lookup=lookup) == pw.BREACHED


async def test_padding_lines_dont_count() -> None:
    lookup = await _lookup_listing("correct horse battery staple", 0)
    assert await breached("correct horse battery staple", lookup) is False


async def test_a_lookup_that_fails_accepts_and_logs(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down(*_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx.AsyncClient, "get", down)
    with caplog.at_level(logging.WARNING, logger="kernel.auth.passwords"):
        assert await refusal("correct horse battery staple") is None
    assert "breach lookup failed (ConnectError)" in caplog.text


async def test_the_range_api_gets_five_characters_and_padding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def get(self: httpx.AsyncClient, url: str, headers: dict[str, str]) -> httpx.Response:
        seen["url"], seen["headers"] = url, headers
        return httpx.Response(503)

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    assert await pw.ask_range("ABCDE") is None
    assert seen == {"url": pw.RANGE_URL + "ABCDE", "headers": {"Add-Padding": "true"}}


async def test_hash_and_check() -> None:
    passwords = Passwords(FAST)
    hashed = await passwords.hash("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert await passwords.check("correct horse battery staple", hashed)
    assert not await passwords.check("correct horse battery stapl", hashed)
    assert not await passwords.check("anything", None)
    assert not await passwords.check("anything", "not a hash")


async def test_nfc_forms_are_one_password() -> None:
    passwords = Passwords(FAST)
    hashed = await passwords.hash("café au lait s'il vous plait")
    assert await passwords.check("café au lait s'il vous plait", hashed)


async def test_weaker_hashes_are_upgraded() -> None:
    old = await Passwords(FAST).hash("correct horse battery staple")
    assert Passwords().needs_rehash(old)
    assert not Passwords(FAST).needs_rehash(old)
    assert Passwords().needs_rehash("garbage")


def test_the_owasp_floor() -> None:
    with pytest.raises(ValueError, match="OWASP's minimum"):
        Hashing(memory_kib=8 * 1024, time_cost=2, lanes=1)
    with pytest.raises(ValueError, match="OWASP's minimum"):
        Hashing(memory_kib=19 * 1024, time_cost=1, lanes=1)


def test_the_common_list_is_bundled() -> None:
    assert len(pw._common()) > 70_000
    assert all(len(entry) >= pw.SHORTEST for entry in list(pw._common())[:1000])


COMMON_ONES = ["iloveyou1234", "qwertyuiop123", "CorrectHorseBatteryStaple", "password1234"]


@pytest.mark.parametrize("common", COMMON_ONES)
async def test_common_passwords_are_refused(common: str) -> None:
    assert pw.is_common(common)

    async def never(_prefix: str) -> str | None:
        raise AssertionError("a common password is refused before the breach lookup")

    reason = await refusal(common, lookup=never)
    assert reason in {pw.COMMON, pw.A_RUN, pw.ABOUT_THIS_SITE}


async def test_an_uncommon_password_passes_the_list() -> None:
    async def clean(_prefix: str) -> str | None:
        return ""

    assert not pw.is_common("lantern orbit pickle seventy")
    assert await refusal("lantern orbit pickle seventy", lookup=clean) is None


async def test_text_that_cant_be_kept_is_refused_not_a_crash() -> None:
    lone = "abc\ud800defghijklmn"
    assert by_rules(lone) == pw.CANT_KEEP
    passwords = Passwords(FAST)
    kept = await passwords.hash(PASSWORD)
    assert await passwords.check(lone, kept) is False
    assert await passwords.check(lone, None) is False
    assert await pw.breached(lone, lookup=lambda prefix: _never(prefix)) is None


async def _never(prefix: str) -> str | None:
    raise AssertionError("asked the breach API about a password that can't be kept")


async def test_a_password_past_256_is_never_checked_as_typed() -> None:
    passwords = Passwords(FAST)
    long = "a long passphrase " * 20  # 360 characters
    kept = await passwords.hash(long)  # kept somehow, say by an old rule
    assert await passwords.check(long, kept) is False
