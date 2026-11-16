"""The config refuses unsafe secrets and placeholder addresses outside DEBUG."""

from __future__ import annotations

import logging
import secrets

import pytest
from cryptography.fernet import Fernet

from kernel.config import (
    KernelConfig,
    get_config,
    mail_problems,
    modules_allowed,
    placeholder_addresses,
    refuse_unsafe,
    reset_config,
    storage_problems,
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
        ("", "SECRET_KEY is shorter than 43 characters."),
        ("short", "SECRET_KEY is shorter than 43 characters."),
        ("my-company-production-secret-2026", "SECRET_KEY is shorter than 43 characters."),
        (secrets.token_urlsafe(24), "SECRET_KEY is shorter than 43 characters."),
        (
            "change-me-change-me-change-me-change-me-change",
            "SECRET_KEY is a placeholder, not a random secret.",
        ),
        ("a" * 50, "SECRET_KEY is a placeholder, not a random secret."),
        (
            "this-is-just-an-example-secret-key-1234567890",
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
        "SECRET_KEY is shorter than 43 characters. Allowed only because DEBUG is on.",
        "SITE_URL is a placeholder (example.com), not the site's own address. Allowed only because DEBUG is on.",
    ]


def test_modules_allowed() -> None:
    installed = {"blog", "comments", "shop"}
    assert modules_allowed(config(modules="*"), installed) == installed
    assert modules_allowed(config(modules=" Blog , shop"), installed) == {"blog", "shop"}
    assert modules_allowed(config(modules=""), installed) == frozenset()
    with pytest.raises(ValueError, match=r"MODULES names blgo, which is not installed"):
        modules_allowed(config(modules="blgo,shop"), installed)


def test_modules_cant_mix_every_module_with_names() -> None:
    with pytest.raises(ValueError, match=r"MODULES mixes \* with names"):
        modules_allowed(config(modules="*,blog"), {"blog", "shop"})


def test_the_hint_makes_keys_that_pass() -> None:
    for make in (lambda: secrets.token_urlsafe(32), lambda: secrets.token_urlsafe(48)):
        assert all(unsafe_secrets(config(secret_key=make())) == [] for _ in range(200))
    assert unsafe_secrets(config(secret_key=secrets.token_hex(32))) == []


@pytest.mark.parametrize(
    ("url", "problem"),
    [
        ("http://devkit.test", "SITE_URL must be https outside DEBUG."),
        ("https://localhost:8000", "SITE_URL is a local address (localhost), not the site's own."),
        ("https://127.0.0.1", "SITE_URL is a local address (127.0.0.1), not the site's own."),
        ("https://[::1]:8443", "SITE_URL is a local address (::1), not the site's own."),
    ],
)
def test_a_live_site_url_is_https_and_not_local(url: str, problem: str) -> None:
    assert placeholder_addresses(config(site_url=url)) == [problem]
    assert placeholder_addresses(config(site_url=url, debug=True)) == []  # local development


def test_a_blank_client_ip_header_is_warned_about(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="kernel.config"):
        refuse_unsafe(config(client_ip_header=""))
        refuse_unsafe(config(client_ip_header="X-Real-IP"))
        refuse_unsafe(config(client_ip_header="", debug=True))
    assert [r.getMessage()[:40] for r in caplog.records] == [
        "CLIENT_IP_HEADER is blank, so every visi"
    ]


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


# --- storage (kernel.storage, decision 0032) ---------------------------------------

STORAGE_KEY_ID = "key-id-7f3a9b"
STORAGE_SECRET = "storage-secret-2c8e41"
STORAGE = {
    "storage_endpoint_url": "https://acct.r2.cloudflarestorage.com",
    "storage_access_key_id": STORAGE_KEY_ID,
    "storage_secret_access_key": STORAGE_SECRET,
    "storage_bucket": "site-private",
    "storage_public_bucket": "site-public",
    "storage_public_url": "https://files.site.test",
}


def test_storage_off_or_whole_passes() -> None:
    assert storage_problems(config()) == []
    assert storage_problems(config(**STORAGE)) == []
    private_only = {**STORAGE, "storage_public_bucket": "", "storage_public_url": ""}
    assert storage_problems(config(**private_only)) == []
    assert config(**STORAGE).storage_secret_access_key.get_secret_value() == STORAGE_SECRET
    assert STORAGE_SECRET not in repr(config(**STORAGE))


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        (
            {"storage_bucket": "x"},
            "STORAGE_ENDPOINT_URL, STORAGE_ACCESS_KEY_ID, STORAGE_SECRET_ACCESS_KEY",
        ),
        ({**STORAGE, "storage_secret_access_key": ""}, "STORAGE_SECRET_ACCESS_KEY"),
        (
            {**STORAGE, "storage_endpoint_url": "acct.r2.cloudflarestorage.com"},
            "STORAGE_ENDPOINT_URL is not",
        ),
        (
            {**STORAGE, "storage_endpoint_url": "http://acct.r2.cloudflarestorage.com"},
            "STORAGE_ENDPOINT_URL must be https",
        ),
        ({**STORAGE, "storage_public_url": ""}, "STORAGE_PUBLIC_BUCKET and STORAGE_PUBLIC_URL"),
        ({**STORAGE, "storage_public_bucket": ""}, "STORAGE_PUBLIC_BUCKET and STORAGE_PUBLIC_URL"),
        (
            {**STORAGE, "storage_public_url": "http://files.site.test"},
            "STORAGE_PUBLIC_URL must be https",
        ),
        (
            {**STORAGE, "storage_public_url": "https://files.example.com"},
            "STORAGE_PUBLIC_URL is a placeholder",
        ),
        ({**STORAGE, "storage_public_url": "files.site.test"}, "STORAGE_PUBLIC_URL is not"),
        ({**STORAGE, "storage_public_bucket": "site-private"}, "the same bucket"),
    ],
)
def test_storage_set_in_part_is_refused(values: dict[str, str], problem: str) -> None:
    problems = storage_problems(config(**values))
    assert any(problem in found for found in problems), problems
    for found in problems:
        assert STORAGE_SECRET not in found
        assert STORAGE_KEY_ID not in found
    with pytest.raises(RuntimeError, match="Refusing to start") as caught:
        refuse_unsafe(config(**values))
    assert STORAGE_SECRET not in str(caught.value)


def test_storage_over_http_is_allowed_with_debug(caplog: pytest.LogCaptureFixture) -> None:
    local = {
        **STORAGE,
        "storage_endpoint_url": "http://localhost:9000",
        "storage_public_url": "http://localhost:9000/site-public",
    }
    assert storage_problems(config(debug=True, **local)) == []
    assert storage_problems(config(debug=True, storage_bucket="x"))
    with caplog.at_level(logging.WARNING):
        refuse_unsafe(config(debug=True, storage_bucket="x"))
    assert any("STORAGE_ENDPOINT_URL" in record.getMessage() for record in caplog.records)


# --- mail (kernel.email, decision 0033) ---------------------------------------------

MAIL_PASSWORD = "smtp-pass-31c7aa"
MAIL_KEY = "made-up-resend-key"
SMTP = {"mail_from": "hello@site.test", "smtp_host": "smtp.site.test"}
RESEND = {"mail_from": "hello@site.test", "resend_api_key": MAIL_KEY}


def test_mail_off_or_whole_passes() -> None:
    assert mail_problems(config()) == []
    assert mail_problems(config(**SMTP)) == []
    assert mail_problems(config(**SMTP, smtp_username="u", smtp_password=MAIL_PASSWORD)) == []
    assert mail_problems(config(**RESEND)) == []
    assert MAIL_KEY not in repr(config(**RESEND))
    assert MAIL_PASSWORD not in repr(config(**SMTP, smtp_password=MAIL_PASSWORD))


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({**SMTP, "mail_from": ""}, "MAIL_FROM is blank"),
        ({**SMTP, "mail_from": "Site <hello@site.test>"}, "MAIL_FROM is not one bare address"),
        ({**SMTP, "mail_from": "a@site.test, b@site.test"}, "MAIL_FROM is not one bare address"),
        ({**SMTP, "mail_from": "hello@example.com"}, "MAIL_FROM is a placeholder"),
        ({**SMTP, "smtp_host": ""}, "Mail is set in part"),
        ({"mail_from": "hello@site.test"}, "Mail is set in part"),
        ({"smtp_username": "u", "smtp_password": MAIL_PASSWORD}, "Mail is set in part"),
        ({**SMTP, "smtp_username": "u"}, "SMTP_USERNAME and SMTP_PASSWORD go together"),
        ({**SMTP, "smtp_password": MAIL_PASSWORD}, "SMTP_USERNAME and SMTP_PASSWORD go together"),
        ({**RESEND, "resend_api_key": ""}, "Mail is set in part"),
        ({**RESEND, "mail_from": ""}, "MAIL_FROM is blank"),
    ],
)
def test_mail_set_in_part_is_refused(values: dict[str, str], problem: str) -> None:
    problems = mail_problems(config(**values))
    assert any(problem in found for found in problems), problems
    for found in problems:
        assert MAIL_PASSWORD not in found
        assert MAIL_KEY not in found
    with pytest.raises(RuntimeError, match="Refusing to start"):
        refuse_unsafe(config(**values))


def test_smtp_comes_first_and_resend_only_without_it() -> None:
    # The owner's rule (decision 0033): SMTP whenever it's set; Resend only on a
    # host that blocks SMTP, where only its key is set.
    assert config().mail_adapter == ""
    assert config(**SMTP).mail_adapter == "smtp"
    assert config(**RESEND).mail_adapter == "resend"
    assert config(**SMTP, resend_api_key=MAIL_KEY).mail_adapter == "smtp"
    assert config(**RESEND, smtp_host=" ").mail_adapter == "resend"
