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

**Storage** (`kernel.storage`, decision 0032) is off until its variables are
set. Set in part, it stops the start outside DEBUG, as an unsafe secret does
(`storage_problems`). **Mail** (`kernel.email`, decision 0033) works the same
way: nothing set, no mail; set in part, the start stops (`mail_problems`).
SMTP comes first: SMTP_HOST set means SMTP. Resend is only for a host that
blocks SMTP, where RESEND_API_KEY is set without SMTP_HOST.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

#: secrets.token_urlsafe(32)'s length: 256 bits, if the key is random. A floor,
#: not a proof: a long phrase passes it, so generate the key (see the hint).
SECRET_MIN_LENGTH = 43
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
    site_name: str = "MechFrame site"
    site_url: str = "http://localhost:8000"
    database_url: str = "postgresql://mechframe:mechframe@localhost:5432/mechframe"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    #: HMAC key for signed values (links in emails, OAuth state): 43+ characters,
    #: from secrets.token_urlsafe(48).
    secret_key: str = ""
    #: Fernet keys, comma-separated, newest first: secrets are sealed with the
    #: first and opened with any, so a new key goes in front and the old one
    #: leaves once `kernel.crypto.rotate` has resealed everything.
    encryption_keys: str = ""

    modules: str = "*"
    #: How long each process trusts the switched-off list it read
    #: (kernel.modules): a switch made by another worker reaches this one
    #: within it. 0 reads it on every request.
    modules_cache_seconds: float = Field(default=5.0, ge=0, le=60)

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
    #: The built web app's folder, whose index.html is the shell every public
    #: address answers with (kernel.shell, decision 0041). Unset: the kernel's
    #: minimal shell, with no scripts.
    web_dist: str = ""

    #: The largest request body accepted, in bytes; larger is refused with 413.
    #: A module that takes bigger uploads sends them to storage, not here.
    max_body_bytes: int = Field(default=1024 * 1024, ge=1024)

    #: Argon2id for passwords (kernel.auth.passwords): never below OWASP's
    #: 19 MiB, 2 passes, 1 lane. Raise memory where the host has it.
    argon2_memory_kib: int = Field(default=64 * 1024, ge=19 * 1024)
    argon2_time_cost: int = Field(default=3, ge=2)
    argon2_lanes: int = Field(default=4, ge=1)
    #: How many hashes run at once; each holds ARGON2_MEMORY_KIB while it runs.
    argon2_concurrency: int = Field(default=4, ge=1)

    #: Who may make an account (SPEC.md 14.7, decision 0020): open, invite
    #: (an invite is needed; invites arrive with K2's API keys and invites) or
    #: closed. Closed until a site opens it, so an account nobody meant to
    #: allow can't appear. The site settings (Q6) take it over with their page.
    sign_up_mode: Literal["open", "invite", "closed"] = "closed"

    #: Object storage (kernel.storage, SPEC.md 15, decision 0032): an
    #: S3-compatible store, Cloudflare R2 on a live site. All blank: storage is
    #: off. STORAGE_ENDPOINT_URL is the account's endpoint
    #: (https://<account>.r2.cloudflarestorage.com); a bucket path pasted onto it
    #: is dropped. STORAGE_BUCKET is private: its files are reached only through
    #: signed links. STORAGE_PUBLIC_BUCKET is optional and served to anyone at
    #: STORAGE_PUBLIC_URL (R2: the bucket's custom domain).
    storage_endpoint_url: str = ""
    storage_region: str = "auto"
    storage_access_key_id: str = ""
    storage_secret_access_key: SecretStr = SecretStr("")
    storage_bucket: str = ""
    storage_public_bucket: str = ""
    storage_public_url: str = ""
    #: The largest file `storage.put` takes, in bytes.
    storage_max_bytes: int = Field(default=2 * 1024**3, ge=1)

    #: Jobs (kernel.jobs, decision 0035). JOBS_IN_WEB runs the worker inside
    #: the web process (one service); a site that runs `kernel.worker.serve`
    #: as a service of its own, for heavy jobs such as ffmpeg, sets it false on
    #: the web service. A worker runs up to JOBS_CONCURRENCY jobs at once, looks
    #: for due ones every JOBS_POLL_SECONDS, and on SIGTERM gives the running
    #: ones JOBS_DRAIN_SECONDS before leaving them to their leases.
    jobs_in_web: bool = True
    jobs_concurrency: int = Field(default=4, ge=1, le=32)
    jobs_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    jobs_drain_seconds: float = Field(default=20.0, ge=0, le=600)

    #: The audit log (kernel.audit, decision 0037): `kernel.prune_audit`
    #: removes entries older than this every night. A year by default; at
    #: least 30 days.
    audit_keep_days: int = Field(default=365, ge=30)

    rate_limit_enabled: bool = True
    #: Where counts live: memory:// for one process, redis://… once a site
    #: runs more than one.
    rate_limit_storage: str = "memory://"

    #: Mail (kernel.email, decision 0033), SMTP first: with SMTP_HOST set,
    #: mail goes out through any provider's SMTP (implicit TLS on port 465,
    #: STARTTLS on any other). Only on a host that blocks outbound SMTP, such
    #: as Railway's Hobby plan, set RESEND_API_KEY instead, without SMTP_HOST.
    #: Neither set: nothing is sent (LogMailer). MAIL_FROM is the one address
    #: mail comes from; MAIL_FROM_NAME (default: SITE_NAME) is shown beside it.
    mail_from: str = ""
    mail_from_name: str = ""
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    resend_api_key: SecretStr = SecretStr("")

    sentry_dsn: str = ""
    sentry_environment: str = ""
    log_format: Literal["json", "text"] = "json"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def mail_adapter(self) -> Literal["", "smtp", "resend"]:
        """Which adapter sends mail: SMTP whenever SMTP_HOST is set, Resend
        only when RESEND_API_KEY is set without it, else none."""
        if self.smtp_host.strip():
            return "smtp"
        if self.resend_api_key.get_secret_value().strip():
            return "resend"
        return ""

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
    if "*" in names:
        raise ValueError(
            f"MODULES mixes * with names ({', '.join(sorted(names - {'*'}))}): use * alone for "
            "every installed module, or list the ones this deploy may use."
        )
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
    if len(secret) < SECRET_MIN_LENGTH:
        problems.append(f"SECRET_KEY is shorter than {SECRET_MIN_LENGTH} characters.")
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


def _is_local(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def placeholder_addresses(config: KernelConfig) -> list[str]:
    """What's wrong with SITE_URL. Outside DEBUG it must also be https and
    not a local address: cookies are `__Host-`, and links in mail go there."""
    parts = urlsplit((config.site_url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ["SITE_URL is not an http or https address."]
    if is_placeholder_domain(parts.hostname):
        return [f"SITE_URL is a placeholder ({parts.hostname}), not the site's own address."]
    if config.debug:
        return []
    if parts.scheme != "https":
        return ["SITE_URL must be https outside DEBUG."]
    if _is_local(parts.hostname):
        return [f"SITE_URL is a local address ({parts.hostname}), not the site's own."]
    return []


#: What storage can't run without, by variable name.
_STORAGE_REQUIRED = (
    "STORAGE_ENDPOINT_URL",
    "STORAGE_ACCESS_KEY_ID",
    "STORAGE_SECRET_ACCESS_KEY",
    "STORAGE_BUCKET",
)


def _storage_values(config: KernelConfig) -> dict[str, str]:
    return {
        "STORAGE_ENDPOINT_URL": config.storage_endpoint_url.strip(),
        "STORAGE_ACCESS_KEY_ID": config.storage_access_key_id.strip(),
        "STORAGE_SECRET_ACCESS_KEY": config.storage_secret_access_key.get_secret_value().strip(),
        "STORAGE_BUCKET": config.storage_bucket.strip(),
        "STORAGE_PUBLIC_BUCKET": config.storage_public_bucket.strip(),
        "STORAGE_PUBLIC_URL": config.storage_public_url.strip(),
    }


def storage_missing(config: KernelConfig) -> list[str]:
    """The variables storage needs that are blank, in order."""
    values = _storage_values(config)
    return [name for name in _STORAGE_REQUIRED if not values[name]]


def _address_problem(name: str, url: str, debug: bool) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return f"{name} is not an http or https address."
    if is_placeholder_domain(parts.hostname):
        return f"{name} is a placeholder ({parts.hostname})."
    if parts.scheme != "https" and not debug:
        return f"{name} must be https outside DEBUG."
    return None


def storage_problems(config: KernelConfig) -> list[str]:
    """What's wrong with the storage variables, by name, never by value.
    None set is fine (storage is off); some set means all of them must be."""
    values = _storage_values(config)
    if not any(values.values()):
        return []
    problems = []
    missing = storage_missing(config)
    if missing:
        problems.append(
            f"Storage is set in part: {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} blank."
        )
    for name in ("STORAGE_ENDPOINT_URL", "STORAGE_PUBLIC_URL"):
        if values[name]:
            problem = _address_problem(name, values[name], config.debug)
            if problem:
                problems.append(problem)
    if bool(values["STORAGE_PUBLIC_BUCKET"]) != bool(values["STORAGE_PUBLIC_URL"]):
        problems.append(
            "STORAGE_PUBLIC_BUCKET and STORAGE_PUBLIC_URL go together: set both or neither."
        )
    if (
        values["STORAGE_PUBLIC_BUCKET"]
        and values["STORAGE_PUBLIC_BUCKET"] == values["STORAGE_BUCKET"]
    ):
        problems.append(
            "STORAGE_BUCKET and STORAGE_PUBLIC_BUCKET name the same bucket: private files would be public."
        )
    return problems


def mail_problems(config: KernelConfig) -> list[str]:
    """What's wrong with the mail variables, by name, never by value.
    Nothing set is fine (no mail is sent); some set means mail needs the rest."""
    from kernel.email import is_address

    sender = config.mail_from.strip()
    login = bool(config.smtp_username.strip()), bool(config.smtp_password.get_secret_value())
    if not config.mail_adapter:
        if sender or any(login):
            return [
                "Mail is set in part: set SMTP_HOST (or, only on a host that blocks SMTP, "
                "RESEND_API_KEY), or nothing is sent."
            ]
        return []
    problems = []
    if not sender:
        problems.append("MAIL_FROM is blank: mail needs the address it comes from.")
    elif not is_address(sender):
        problems.append(
            "MAIL_FROM is not one bare address (no name or angle brackets: MAIL_FROM_NAME holds the name)."
        )
    elif is_placeholder_domain(sender.rpartition("@")[2]):
        problems.append("MAIL_FROM is a placeholder address, not the site's own.")
    if config.mail_adapter == "smtp" and login[0] != login[1]:
        problems.append("SMTP_USERNAME and SMTP_PASSWORD go together: set both or neither.")
    return problems


def refuse_unsafe(config: KernelConfig) -> None:
    """Stop the start on unsafe secrets, a placeholder address, or storage or
    mail set in part, unless DEBUG is on, when each problem is only logged."""
    secrets_wrong = unsafe_secrets(config)
    problems = (
        secrets_wrong
        + placeholder_addresses(config)
        + storage_problems(config)
        + mail_problems(config)
    )
    if not config.debug and not config.client_ip_header.strip():
        log.warning(
            "CLIENT_IP_HEADER is blank, so every visitor counts as the address that "
            "connects. Behind a proxy or a host's edge (Railway), that's the edge: "
            "everyone shares one rate limit. Set it to the header the edge writes "
            "(X-Real-IP on Railway)."
        )
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
