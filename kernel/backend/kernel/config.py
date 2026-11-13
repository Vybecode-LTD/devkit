"""The kernel's configuration, from environment variables (pydantic-settings).

Lifted from VybeSite `core/config.py`. A site sets these on its host
(Railway's variables); `.env` is read for local runs only, and the
environment wins over it.

**Refusing to start on unsafe values** (SPEC.md 14.12). Outside DEBUG,
`refuse_unsafe` stops the app on a missing, short or placeholder SECRET_KEY,
on ENCRYPTION_KEYS that aren't Fernet keys, and on a SITE_URL that isn't an
http(s) address or is still a documentation domain. With DEBUG on each
problem is only logged, since local development runs on the defaults.
Problems name the variable, never its value.

**MODULES** lists the modules this deploy may use, comma-separated, or `*`
for every module installed. The admin can switch any of those off at
runtime (`kernel.modules`). A name that isn't installed stops the start, so a
typo never silently leaves a module off.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

SECRET_MIN_BYTES = 32
_PLACEHOLDER_WORDS = (
    "changeme",
    "placeholder",
    "notarealsecret",
    "replaceme",
    "yoursecret",
    "example",
    "secretkey",
)
#: The documentation domains (RFC 2606), which a live site never answers on.
_PLACEHOLDER_DOMAINS = ("example.com", "example.net", "example.org", "example")


class KernelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    debug: bool = False
    site_name: str = "DevKit site"
    site_url: str = "http://localhost:8000"
    database_url: str = "postgresql://devkit:devkit@localhost:5432/devkit"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    #: HMAC key for signed values (links in emails, OAuth state). 32+ random bytes.
    secret_key: str = ""
    #: Fernet keys, comma-separated, newest first: secrets are sealed with the
    #: first and opened with any, so a new key goes in front and the old one
    #: leaves once `kernel.crypto.rotate` has resealed everything.
    encryption_keys: str = ""

    modules: str = "*"

    #: Origins allowed to call the API from a browser, comma-separated. With
    #: DEBUG on they count as the site's own for the same-origin check, so a
    #: Vite dev server on another port can write.
    cors_origins: str = ""
    #: The one header the host's edge writes the visitor's address into, such
    #: as X-Real-IP on Railway. Blank: the connection's address.
    client_ip_header: str = ""
    #: Strict-Transport-Security's max-age, in seconds. 0 sends none (dev).
    hsts_max_age: int = Field(default=0, ge=0)
    #: Ask search engines to leave this copy out (staging). Never on production.
    robots_noindex: bool = False

    #: The largest request body accepted, in bytes; larger is refused with 413.
    #: A module that takes bigger uploads sends them to storage, not here.
    max_body_bytes: int = Field(default=1024 * 1024, ge=1024)

    rate_limit_enabled: bool = True
    #: Where counts live: memory:// for one process, redis://… once a site
    #: runs more than one.
    rate_limit_storage: str = "memory://"

    sentry_dsn: str = ""
    sentry_environment: str = ""
    log_format: Literal["json", "text"] = "json"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def async_database_url(self) -> str:
        from kernel.db import async_database_url

        return async_database_url(self.database_url)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def encryption_key_list(self) -> list[str]:
        return [key.strip() for key in self.encryption_keys.split(",") if key.strip()]


def modules_allowed(config: KernelConfig, installed: set[str]) -> frozenset[str]:
    """The modules MODULES lets this deploy use. Raises ValueError, naming
    them, for names that aren't installed."""
    names = {name.strip().lower() for name in config.modules.split(",") if name.strip()}
    if names == {"*"}:
        return frozenset(installed)
    unknown = sorted(names - installed - {"*"})
    if unknown:
        raise ValueError(
            f"MODULES names {', '.join(unknown)}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not installed. Installed: "
            f"{', '.join(sorted(installed)) or 'none'}."
        )
    return frozenset(names & installed)


def unsafe_secrets(config: KernelConfig) -> list[str]:
    """What is wrong with the secrets, by variable name, never by value."""
    problems = []
    secret = config.secret_key or ""
    squashed = re.sub(r"[^a-z0-9]", "", secret.lower())
    if len(secret.encode("utf-8")) < SECRET_MIN_BYTES:
        problems.append(f"SECRET_KEY is shorter than {SECRET_MIN_BYTES} bytes.")
    elif any(word in squashed for word in _PLACEHOLDER_WORDS) or len(set(secret)) < 10:
        problems.append("SECRET_KEY is a placeholder, not a random secret.")
    keys = config.encryption_key_list
    if not keys:
        problems.append("ENCRYPTION_KEYS is empty.")
    for position, key in enumerate(keys, start=1):
        try:
            Fernet(key.encode("utf-8"))
        except (ValueError, TypeError):
            problems.append(f"ENCRYPTION_KEYS' key {position} is not a valid Fernet key.")
    if len(set(keys)) != len(keys):
        problems.append("ENCRYPTION_KEYS lists the same key twice.")
    return problems


def is_placeholder_domain(name: str) -> bool:
    name = (name or "").strip().lower().rstrip(".")
    return any(name == domain or name.endswith("." + domain) for domain in _PLACEHOLDER_DOMAINS)


def placeholder_addresses(config: KernelConfig) -> list[str]:
    parts = urlsplit((config.site_url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ["SITE_URL is not an http or https address."]
    if is_placeholder_domain(parts.hostname):
        return [f"SITE_URL is a placeholder ({parts.hostname}), not the site's own address."]
    return []


def refuse_unsafe(config: KernelConfig) -> None:
    """Stop the start on unsafe secrets or a placeholder address, unless DEBUG
    is on, when each problem is only logged."""
    secrets_wrong = unsafe_secrets(config)
    problems = secrets_wrong + placeholder_addresses(config)
    if not problems:
        return
    if config.debug:
        for problem in problems:
            log.warning("%s Allowed only because DEBUG is on.", problem)
        return
    fixes = []
    if secrets_wrong:
        fixes.append(
            'Generate SECRET_KEY with python -c "import secrets; print(secrets.token_urlsafe(48))" '
            'and each ENCRYPTION_KEYS key with python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())". Removing a key from ENCRYPTION_KEYS makes '
            "anything sealed with it unreadable."
        )
    raise RuntimeError(
        "Refusing to start: "
        + " ".join(problems)
        + (" " + " ".join(fixes) if fixes else "")
        + " DEBUG=true skips this check, for local development only."
    )


@lru_cache(maxsize=1)
def get_config() -> KernelConfig:
    """The process's configuration, read once."""
    return KernelConfig()


def reset_config() -> None:
    """Read the environment again on the next `get_config()` (tests)."""
    get_config.cache_clear()
