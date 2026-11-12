"""One error shape for every API: RFC 9457 problem details (SPEC.md section 7).

    raise Problem("blog.post_not_found", 404, "There's no post at that address.")

answers `application/problem+json`:

    {"type": "urn:devkit:problem:blog.post_not_found", "title": "Not Found",
     "status": 404, "detail": "There's no post at that address.",
     "code": "blog.post_not_found"}

`code` is stable: front ends and tests match on it, never on `detail`, which
is a sentence for people and may be reworded. Field errors go in `errors`, a
map of field path to messages. Extra members (such as a save conflict's
fields) go in `extra`.

The handlers turn FastAPI's own errors into the same shape: a 404 or 405
from routing, a request that fails validation (422, `kernel.invalid_request`,
with `errors`), and anything unexpected (500, `kernel.internal_error`, whose
details stay in the log and the error tracker, never in the answer).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)

MEDIA_TYPE = "application/problem+json"
TYPE_PREFIX = "urn:devkit:problem:"
CODE = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9_]*$")
_RESERVED = frozenset({"type", "title", "status", "detail", "code", "errors", "instance"})

_STATUS_CODES = {
    400: "kernel.bad_request",
    401: "kernel.not_signed_in",
    403: "kernel.forbidden",
    404: "kernel.not_found",
    405: "kernel.method_not_allowed",
    409: "kernel.conflict",
    413: "kernel.too_large",
    415: "kernel.unsupported_media_type",
    429: "kernel.rate_limited",
}


class Problem(Exception):
    """An error answered as problem details. `code` is `<module>.<snake_case>`."""

    def __init__(
        self,
        code: str,
        status: int = 400,
        detail: str = "",
        *,
        title: str | None = None,
        errors: Mapping[str, list[str]] | None = None,
        extra: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not CODE.match(code):
            raise ValueError(f"{code!r} isn't a problem code: <module>.<snake_case>.")
        if not 400 <= status <= 599:
            raise ValueError(f"A problem's status is 4xx or 5xx, not {status}.")
        clash = _RESERVED & set(extra or {})
        if clash:
            raise ValueError(f"extra can't set {', '.join(sorted(clash))}.")
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail
        self.title = title or HTTPStatus(status).phrase
        self.errors = dict(errors or {})
        self.extra = dict(extra or {})
        self.headers = dict(headers or {})

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": TYPE_PREFIX + self.code,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }
        if self.errors:
            body["errors"] = self.errors
        body.update(self.extra)
        return body

    def response(self) -> JSONResponse:
        return JSONResponse(
            jsonable_encoder(self.body()),
            status_code=self.status,
            media_type=MEDIA_TYPE,
            headers=self.headers or None,
        )


def _field(location: tuple[Any, ...] | list[Any]) -> str:
    """A validation error's location as a dotted path: ("body", "email") is
    "body.email"."""
    return ".".join(str(part) for part in location) or "body"


async def _problem(_request: Request, error: Exception) -> JSONResponse:
    return cast(Problem, error).response()


async def _http(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    code = _STATUS_CODES.get(error.status_code, f"kernel.http_{error.status_code}")
    detail = error.detail if isinstance(error.detail, str) else ""
    if detail == HTTPStatus(error.status_code).phrase:
        detail = ""
    return Problem(code, error.status_code, detail, headers=error.headers).response()


async def _invalid(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    errors: dict[str, list[str]] = {}
    for item in error.errors():
        errors.setdefault(_field(item.get("loc", ())), []).append(str(item.get("msg", "")))
    return Problem(
        "kernel.invalid_request", 422, "Some of what was sent isn't valid.", errors=errors
    ).response()


async def _unexpected(request: Request, error: Exception) -> JSONResponse:
    log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=error)
    return Problem(
        "kernel.internal_error", 500, "Something went wrong on our side. Try again in a moment."
    ).response()


def install_handlers(app: FastAPI) -> None:
    """Answer every error from `app` as problem details."""
    app.add_exception_handler(Problem, _problem)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(RequestValidationError, _invalid)
    app.add_exception_handler(Exception, _unexpected)
