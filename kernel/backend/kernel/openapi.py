"""The app's OpenAPI document, as the kernel answers (K4, decision 0042; SPEC.md 7 and 18).

FastAPI's own document says a refused body answers its `HTTPValidationError`.
The kernel answers every error as RFC 9457 problem details instead
(`kernel.errors`), so this document says that: each operation's 422 and its
`default` answer are `application/problem+json` with the `Problem` schema, and
FastAPI's two validation schemas are gone. The harness's test-support routes
are left out: a site never has them.

`by_owner` cuts the document into one per owner, as the repo commits them:
the kernel's paths (`/api/auth`, `/api/kernel`) in `kernel/openapi.json`, and
each module's (`/api/<id>`) in `modules/<id>/openapi.json`, each with only the
schemas its paths use. The web kernel's client is generated from the kernel's,
and a module's `api.ts` from its own (`python -m tools.openapi`).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from kernel.errors import MEDIA_TYPE

#: The kernel's own path prefixes; every other `/api/<id>` is a module's.
KERNEL_PREFIXES = ("/api/auth/", "/api/kernel/")
#: The harness's test support (harness/testing.py): never in a document.
TEST_SUPPORT = "/api/_test"
SCHEMAS = "#/components/schemas/"

PROBLEM: dict[str, Any] = {
    "title": "Problem",
    "description": (
        "RFC 9457 problem details (SPEC 7): `type` is `urn:mechframe:problem:<code>`, "
        "`code` is stable, and field errors are in `errors` by dotted path. "
        "Some problems carry more members, such as `retry_after`."
    ),
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "detail": {"type": "string"},
        "code": {"type": "string"},
        "errors": {
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
    },
    "required": ["type", "title", "status", "detail", "code"],
    "additionalProperties": True,
}

_PROBLEM_CONTENT = {MEDIA_TYPE: {"schema": {"$ref": SCHEMAS + "Problem"}}}


def document(app: FastAPI) -> dict[str, Any]:
    """The app's OpenAPI document, its errors described as problems."""
    spec = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        routes=app.routes,
    )
    paths = {
        path: item
        for path, item in spec.get("paths", {}).items()
        if path.startswith("/api/") and not path.startswith(TEST_SUPPORT)
    }
    for item in paths.values():
        for operation in item.values():
            responses = operation.setdefault("responses", {})
            if "422" in responses:
                responses["422"] = {
                    "description": (
                        "What was sent isn't valid (`kernel.invalid_request`), or the route "
                        "refused it with its own code, such as `auth.password_rejected`"
                    ),
                    "content": copy.deepcopy(_PROBLEM_CONTENT),
                }
            responses["default"] = {
                "description": "A problem (RFC 9457)",
                "content": copy.deepcopy(_PROBLEM_CONTENT),
            }
    spec["paths"] = paths
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    if "Problem" in schemas:
        raise ValueError(
            "A route's model is named Problem, the name of the kernel's error schema "
            "(RFC 9457): rename the model (CodeRabbit on #78)."
        )
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)
    schemas["Problem"] = copy.deepcopy(PROBLEM)
    spec["components"]["schemas"] = dict(sorted(schemas.items()))
    return spec


def install(app: FastAPI) -> None:
    """Serves `document` as the app's OpenAPI (with DEBUG on, at /openapi.json)."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = document(app)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def owner(path: str) -> str:
    """`kernel` for the kernel's paths, else the module id in `/api/<id>/...`."""
    if path.startswith(KERNEL_PREFIXES):
        return "kernel"
    return path.removeprefix("/api/").split("/", 1)[0]


def references(node: Any) -> Iterator[str]:
    """Every `$ref` under `node`."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from references(value)
    elif isinstance(node, list):
        for value in node:
            yield from references(value)


def _used(schemas: Mapping[str, Any], start: Any) -> set[str]:
    """The schemas `start` refers to, and those they refer to in turn."""
    seen: set[str] = set()
    waiting = [ref.removeprefix(SCHEMAS) for ref in references(start)]
    while waiting:
        name = waiting.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        waiting.extend(ref.removeprefix(SCHEMAS) for ref in references(schemas[name]))
    return seen


def by_owner(
    spec: Mapping[str, Any], titles: Mapping[str, tuple[str, str]]
) -> dict[str, dict[str, Any]]:
    """One document per owner that has paths, by owner. `titles` gives each
    owner's `(title, version)`; an owner missing from it keeps the app's."""
    schemas: Mapping[str, Any] = spec.get("components", {}).get("schemas", {})
    grouped: dict[str, dict[str, Any]] = {}
    for path, item in spec.get("paths", {}).items():
        grouped.setdefault(owner(path), {})[path] = item
    made: dict[str, dict[str, Any]] = {}
    for name, paths in grouped.items():
        title, version = titles.get(name, (spec["info"]["title"], spec["info"]["version"]))
        used = _used(schemas, paths)
        made[name] = {
            "openapi": spec["openapi"],
            "info": {"title": title, "version": version},
            "paths": dict(paths),
            "components": {"schemas": {key: schemas[key] for key in sorted(used)}},
        }
    return made


def dumped(spec: Mapping[str, Any]) -> str:
    """The text a document is committed as: two-space JSON, one newline at the end."""
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
