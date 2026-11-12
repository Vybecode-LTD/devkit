"""Error tracking: an error nobody expected reaches whoever runs the site.

Lifted from VybeSite `core/error_tracking.py`. Through Sentry's SDK, only when
SENTRY_DSN is set (Sentry's hosted service, or a self-hosted GlitchTip, which
speaks the same protocol). Blank, nothing is set up and nothing is sent.
Errors only: no traces or profiles. A route's deliberate 5xx is said to the
person and is no event.

**Nothing private leaves the site:**
- no request body, cookie, Authorization header or client address; only the
  headers in `_HEADERS`; no query string;
- no local variables in a stack frame and no lines of source around it;
- never uvicorn's access line;
- `kernel.redact` on every string in an event. The protocol's own
  identifiers (event id, release, trace ids) go back as they were.

**Tracking never takes the site down:** a DSN that can't be used is logged by
its kind of fault, never its value, and the process carries on untracked.
"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from kernel.config import KernelConfig
from kernel.redact import clean

log = logging.getLogger(__name__)

_HEADERS = frozenset({"user-agent", "content-type", "content-length", "host"})
_PROTOCOL = (
    "event_id",
    "release",
    "dist",
    "environment",
    "server_name",
    "timestamp",
    "platform",
    "level",
)
_TRACE_IDS = ("trace_id", "span_id", "parent_span_id")


def _path_only(url: str) -> str:
    return url.split("?", 1)[0].split("#", 1)[0]


def scrub(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sentry's `before_send`: the event with nothing private left in it."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = _path_only(request["url"])
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                name: value for name, value in headers.items() if name.lower() in _HEADERS
            }
    event.pop("user", None)
    kept = {key: event[key] for key in _PROTOCOL if key in event}
    trace = (event.get("contexts") or {}).get("trace") or {}
    cleaned: dict[str, Any] = clean(event)
    cleaned.update(kept)
    if isinstance(trace, dict) and trace:
        cleaned["contexts"]["trace"].update({key: trace[key] for key in _TRACE_IDS if key in trace})
    return cleaned


def scrub_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sentry's `before_breadcrumb`: a breadcrumb's words and data, redacted."""
    cleaned: dict[str, Any] = clean(crumb)
    data = cleaned.get("data")
    if isinstance(data, dict):
        for key in ("http.query", "http.fragment"):
            if data.get(key):
                data[key] = "[redacted]"
    return cleaned


def init(config: KernelConfig, process: str, *, transport: Any = None) -> bool:
    """Set up error tracking for `process` ("web", "worker") when SENTRY_DSN
    is set. True when it's on."""
    dsn = config.sentry_dsn.strip()
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger
    from sentry_sdk.integrations.starlette import StarletteIntegration

    try:
        sentry_sdk.init(
            dsn=dsn,
            transport=transport,
            environment=config.sentry_environment.strip() or "production",
            release=os.environ.get("RAILWAY_GIT_COMMIT_SHA") or None,
            server_name=process,
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            include_source_context=False,
            traces_sample_rate=None,
            before_send=cast(Any, scrub),  # dicts in, dicts out; Sentry's Event is a TypedDict
            before_breadcrumb=cast(Any, scrub_breadcrumb),
            integrations=[
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
                StarletteIntegration(failed_request_status_codes=set()),
                FastApiIntegration(failed_request_status_codes=set()),
            ],
        )
    except Exception as error:  # tracking must never stop the process
        log.error(
            "SENTRY_DSN can't be used (%s), so error tracking is off. Copy it again from "
            "the project's Client Keys page.",
            type(error).__name__,
        )
        return False
    ignore_logger("uvicorn.access")
    sentry_sdk.set_tag("process", process)
    return True
