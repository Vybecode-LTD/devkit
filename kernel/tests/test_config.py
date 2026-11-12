"""The config refuses unsafe secrets and placeholder addresses outside DEBUG."""

from __future__ import annotations

import logging
import secrets

import pytest
from cryptography.fernet import Fernet

from kernel.config import (
    KernelConfig,
    get_config,
    modules_allowed,
    placeholder_addresses,
    refuse_unsafe,
    reset_config,
    unsafe_secrets,
)

GOOD_SECRET = secrets.token_urlsafe(48)
GOOD_KEY = Fernet.generate_key().decode()


def config(**values: object) -> KernelConfig:
    base: dict[str, object] = {
        "secret_key": GOOD_SECRET,
        "encryption_keys": GOOD_KEY,
        "site_url": "https://devkit.test",
        "debug": False,
    }
    base.update(values)
    return KernelConfig(**base)  # type: ignore[arg-type]


def test_good_values_pass() -> None:
    assert unsafe_secrets(config()) == []
    assert placeholder_addresses(config()) == []
    refuse_unsafe(config())


@pytest.mark.parametrize(
    ("secret", "problem"),
    [
        ("", "SECRET_KEY is shorter than 32 bytes."),
        ("short", "SECRET_KEY is shorter than 32 bytes."),
        (
            "change-me-change-me-change-me-change-me",
            "SECRET_KEY is a placeholder, not a random secret.",
        ),
        ("a" * 40, "SECRET_KEY is a placeholder, not a random secret."),
        (
            "this-is-just-an-example-secret-key-1234567",
            "SECRET_KEY is a placeholder, not a random secret.",
        ),
    ],
)
def test_bad_secret_keys(secret: str, problem: str) -> None:
    assert unsafe_secrets(config(secret_key=secret)) == [problem]


def test_encryption_keys_are_checked_one_by_one() -> None:
    assert unsafe_secrets(config(encryption_keys="")) == ["ENCRYPTION_KEYS is empty."]
    assert unsafe_secrets(config(encryption_keys=f"{GOOD_KEY}, not-a-key")) == [
        "ENCRYPTION_KEYS' key 2 is not a valid Fernet key."
    ]
    assert unsafe_secrets(config(encryption_keys=f"{GOOD_KEY},{GOOD_KEY}")) == [
        "ENCRYPTION_KEYS lists the same key twice."
    ]


def test_problems_never_hold_the_value() -> None:
    secret = "change-me-" + "x" * 30
    wrong = "plainly-wrong"
    problems = unsafe_secrets(config(secret_key=secret, encryption_keys=wrong))
    assert all(secret not in p and wrong not in p for p in problems)


@pytest.mark.parametrize(
    ("url", "problem"),
    [
        (
            "https://example.com",
            "SITE_URL is a placeholder (example.com), not the site's own address.",
        ),
        (
            "https://www.example.org/",
            "SITE_URL is a placeholder (www.example.org), not the site's own address.",
        ),
        ("ftp://site.test", "SITE_URL is not an http or https address."),
        ("not a url", "SITE_URL is not an http or https address."),
    ],
)
def test_placeholder_addresses(url: str, problem: str) -> None:
    assert placeholder_addresses(config(site_url=url)) == [problem]


def test_refuses_to_start_outside_debug() -> None:
    with pytest.raises(RuntimeError, match=r"^Refusing to start: SECRET_KEY is shorter") as caught:
        refuse_unsafe(config(secret_key="short"))
    assert "token_urlsafe" in str(caught.value)


def test_debug_only_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="kernel.config"):
        refuse_unsafe(config(secret_key="short", site_url="https://example.com", debug=True))
    assert [r.getMessage() for r in caplog.records] == [
        "SECRET_KEY is shorter than 32 bytes. Allowed only because DEBUG is on.",
        "SITE_URL is a placeholder (example.com), not the site's own address. Allowed only because DEBUG is on.",
    ]


def test_modules_allowed() -> None:
    installed = {"blog", "comments", "shop"}
    assert modules_allowed(config(modules="*"), installed) == installed
    assert modules_allowed(config(modules=" Blog , shop"), installed) == {"blog", "shop"}
    assert modules_allowed(config(modules=""), installed) == frozenset()
    with pytest.raises(ValueError, match=r"MODULES names blgo, which is not installed"):
        modules_allowed(config(modules="blgo,shop"), installed)


def test_derived_values() -> None:
    c = config(
        database_url="postgres://u:p@h:5432/d",
        cors_origins="http://localhost:5173, ,https://a.test",
        encryption_keys=f" {GOOD_KEY} ,",
    )
    assert c.async_database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert c.cors_origins_list == ["http://localhost:5173", "https://a.test"]
    assert c.encryption_key_list == [GOOD_KEY]


def test_get_config_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_config()
    first = get_config()
    monkeypatch.setenv("SITE_NAME", "Changed")
    assert get_config() is first
    reset_config()
    assert get_config().site_name == "Changed"
    monkeypatch.delenv("SITE_NAME")
    reset_config()
