"""Logging: structured JSON on a host, plain lines locally (SPEC.md section 7).

Lifted from VybeSite `core/log_streams.py`, plus JSON. Routine lines go to
stdout and warnings and worse to stderr, so a host that colours stderr red
(Railway does) shows only what needs reading.

Every line passes through `kernel.redact` first, a backstop that takes out
the shapes of addresses, queries, IPs and tokens a caller let slip; nothing
in the kernel logs a password, code or secret on purpose. uvicorn's access
line names each visitor's address, so it is turned down to warnings, and
`AccessLog` writes the request line instead: method, route template, status
and milliseconds, on `kernel.access`. httpx logs every URL it fetches at
INFO (the Pwned Passwords range among them), so it is kept to warnings.

    LOG_FORMAT=json   {"time": "...", "level": "INFO", "logger": "...", "message": "...", ...}
    LOG_FORMAT=text   2026-11-12 17:40:01 INFO kernel.app: message
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kernel.redact import clean, clean_text

#: Attributes every LogRecord has; anything else a caller passed in `extra`.
_STANDARD = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "taskName",
    "color_message",  # uvicorn's copy of the message with terminal colours
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": clean_text(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                line[key] = clean(
                    value if isinstance(value, str | int | float | bool) else str(value)
                )
        if record.exc_info and record.exc_info[0] is not None:
            line["error"] = record.exc_info[0].__name__
            line["traceback"] = clean_text("".join(traceback.format_exception(*record.exc_info)))
        return json.dumps(line, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        return clean_text(super().format(record))


class _Below(logging.Filter):
    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.level


_MARK = "_devkit_handler"


def configure(log_format: str = "json", level: str = "INFO") -> None:
    """Route the root logger to stdout and stderr, in the chosen format.
    Safe to call again: the kernel's own handlers are replaced, not added."""
    formatter: logging.Formatter = JsonFormatter() if log_format == "json" else TextFormatter()
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(handler)
    routine = logging.StreamHandler(sys.stdout)
    routine.addFilter(_Below(logging.WARNING))
    serious = logging.StreamHandler(sys.stderr)
    serious.setLevel(logging.WARNING)
    for handler in (routine, serious):
        handler.setFormatter(formatter)
        setattr(handler, _MARK, True)
        root.addHandler(handler)
    root.setLevel(level)
    # uvicorn's own handlers would print everything twice; its access line names
    # each visitor's address, so it is kept to warnings.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


access = logging.getLogger("kernel.access")
NO_ROUTE = "(no route)"


def _template(scope: Scope) -> str:
    """The route's full path template, never the path itself, so ids and
    tokens in a URL stay out of the log."""
    if scope.get("route") is None:
        return NO_ROUTE
    from kernel.ratelimit import route_name  # the one place that knows full paths

    return route_name(Request(scope)).split(" ", 1)[1]


class AccessLog:
    """One INFO line per HTTP request: `GET /api/shop/items/{item_id} 200 3ms`,
    with `method`, `route`, `status` and `ms` as fields in JSON. The kernel adds
    it outermost, so it times everything and sees the final status."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_noting_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_noting_status)
        finally:
            ms = round((time.perf_counter() - started) * 1000)
            route = _template(scope)
            access.info(
                "%s %s %d %dms",
                scope["method"],
                route,
                status,
                ms,
                extra={"method": scope["method"], "route": route, "status": status, "ms": ms},
            )
