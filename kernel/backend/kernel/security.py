"""The security middleware every site runs (SPEC.md section 15).

Lifted from VybeSite `middleware/security_headers.py`, `same_origin.py` and
`www_redirect.py`. All three are pure ASGI middleware, so a streamed or file
response passes through untouched. `create_app` adds them so that
SecurityHeaders is outermost: a redirect or a refusal carries its headers too.

**Content-Security-Policy, enforced.** Scripts, styles and fonts from this
origin only, with no inline script or style; images from this origin, any
https host and data: URIs; requests to this origin; frames from this origin;
no plugins; forms post here; nothing frames us. A module that needs another
host (an embed's player, a payment provider) adds it with `csp.allow(...)`,
and the host is in the policy only while that module is on.

**Always:** `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`
and a `Permissions-Policy` denying the camera, microphone and geolocation.
**HSTS** once HSTS_MAX_AGE is set, on https requests only; `max-age` alone,
never `includeSubDomains` or `preload`. **`X-Robots-Tag: noindex`** while
ROBOTS_NOINDEX is set (staging). A header a route sets itself is left alone.

**Writes come only from the site itself** (SameOriginWrites; CSRF, SPEC.md
14.5). A POST, PUT, PATCH or DELETE under /api/ is refused 403
(`kernel.cross_site_write`) when `Sec-Fetch-Site` is present and isn't
same-origin, or `Origin` is present and isn't the site's. A request with
neither isn't a browser's and carries nobody's cookie, so it passes. Incoming
webhooks (`/api/<module>/webhooks/…`) are exempt: they are signature-checked
instead.

**One address** (WwwRedirect). `www.` and SITE_URL's host gets a 301 to the
same path and query on SITE_URL.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kernel.errors import Problem

log = logging.getLogger(__name__)

# --- Content-Security-Policy ----------------------------------------------------

_BASE: dict[str, list[str]] = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'"],
    "font-src": ["'self'"],
    "img-src": ["'self'", "data:", "https:"],
    "connect-src": ["'self'"],
    "frame-src": ["'self'"],
    "media-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
}
#: The directives a module may add a host to. Never style-src: no inline style.
OPENABLE = frozenset(
    {"script-src", "img-src", "connect-src", "frame-src", "media-src", "form-action", "font-src"}
)
_HOST_SOURCE = re.compile(r"^https://(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)+(:\d{1,5})?$")


@dataclass
class ContentSecurityPolicy:
    """The site's policy, plus the hosts modules add while they're on."""

    _extra: list[tuple[str, str, str | None]] = field(default_factory=list)

    def allow(self, directive: str, source: str, *, module: str | None = None) -> None:
        """Add `source`, an https origin such as https://player.vimeo.com, to
        `directive`, while `module` is on (always, for None)."""
        if directive not in OPENABLE:
            raise ValueError(f"Modules can't add hosts to {directive}.")
        if not _HOST_SOURCE.match(source):
            raise ValueError(f"{source!r} isn't an https origin, such as https://js.stripe.com.")
        entry = (directive, source, module)
        if entry not in self._extra:
            self._extra.append(entry)

    def render(self, modules_on: Iterable[str] = ()) -> str:
        on = set(modules_on)
        directives = {name: list(sources) for name, sources in _BASE.items()}
        for directive, source, module in self._extra:
            if (module is None or module in on) and source not in directives[directive]:
                directives[directive].append(source)
        return "; ".join(f"{name} {' '.join(sources)}" for name, sources in directives.items())


_ALWAYS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("X-Frame-Options", "DENY"),
)


class SecurityHeaders:
    def __init__(
        self,
        app: ASGIApp,
        *,
        policy: ContentSecurityPolicy,
        modules_on: Callable[[], Iterable[str]],
        hsts_max_age: int = 0,
        noindex: bool = False,
    ) -> None:
        self.app = app
        self.policy = policy
        self.modules_on = modules_on
        self.hsts_max_age = hsts_max_age
        self.noindex = noindex

    def headers_for(self, scope: Scope) -> list[tuple[str, str]]:
        extra = [*_ALWAYS, ("Content-Security-Policy", self.policy.render(self.modules_on()))]
        if self.hsts_max_age > 0 and scope.get("scheme") == "https":
            extra.append(("Strict-Transport-Security", f"max-age={self.hsts_max_age}"))
        if self.noindex:
            extra.append(("X-Robots-Tag", "noindex"))
        return extra

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = self.headers_for(scope)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in extra:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --- same-origin writes -------------------------------------------------------------

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_WEBHOOK = re.compile(r"^/api/[a-z][a-z0-9-]*/webhooks/")
_DEFAULT_PORTS = {"http": 80, "https": 443}


def origin_of(url: str) -> str:
    """scheme://host[:port], lowercased, a scheme's own port dropped (a
    browser never writes it in Origin)."""
    parts = urlsplit(url.strip().lower())
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme):
        host = f"{host}:{port}"
    return f"{parts.scheme}://{host}"


def _clip(value: str | None) -> str:
    return "none" if value is None else repr(value[:200])


class SameOriginWrites:
    def __init__(self, app: ASGIApp, *, origins: Iterable[str]) -> None:
        self.app = app
        self.origins = frozenset(origin_of(origin) for origin in origins)

    def refuses(self, scope: Scope) -> bool:
        if scope.get("method") not in UNSAFE:
            return False
        path = scope.get("path", "")
        if not path.startswith("/api/") or _WEBHOOK.match(path):
            return False
        headers = Headers(scope=scope)
        fetch_site = headers.get("sec-fetch-site")
        origin = headers.get("origin")
        foreign = (fetch_site is not None and fetch_site.strip().lower() != "same-origin") or (
            origin is not None and origin_of(origin) not in self.origins
        )
        if foreign:
            log.warning(
                "refused %s %s from another site: Sec-Fetch-Site %s, Origin %s; this site is %s",
                scope.get("method"),
                path,
                _clip(fetch_site),
                _clip(origin),
                ", ".join(sorted(self.origins)),
            )
        return foreign

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.refuses(scope):
            problem = Problem(
                "kernel.cross_site_write", 403, "This request didn't come from this site."
            )
            await problem.response()(scope, receive, send)
            return
        await self.app(scope, receive, send)


# --- www. to the site's address ----------------------------------------------------


def apex_for(host: str, site_url: str) -> str | None:
    """SITE_URL without a trailing slash, when `host` is `www.` and SITE_URL's
    host; else None."""
    site = (urlsplit(site_url).hostname or "").lower()
    asked = host.lower().split(":", 1)[0].rstrip(".")
    return site_url.rstrip("/") if site and asked == f"www.{site}" else None


def same_address(apex: str, scope: Scope) -> str:
    raw = scope.get("raw_path") or quote(scope["path"]).encode()
    path = raw.decode("latin-1")
    if not path.startswith("/"):
        path = "/"  # only a proxy's absolute-form target, which no browser sends
    query = scope.get("query_string", b"").decode("latin-1")
    return f"{apex}{path}?{query}" if query else f"{apex}{path}"


class WwwRedirect:
    def __init__(self, app: ASGIApp, *, site_url: str) -> None:
        self.app = app
        self.site_url = site_url

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            apex = apex_for(Headers(scope=scope).get("host", ""), self.site_url)
            if apex:
                response = RedirectResponse(same_address(apex, scope), status_code=301)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
