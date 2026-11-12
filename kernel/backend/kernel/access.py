"""Every route declares who may call it (SPEC.md section 7, 14.13).

A route is **public** (`Depends(public)`), for **members** (`current_user`,
K2) or behind a **permission** (`require_permission(key)`, K2). `undeclared`
lists the API routes that declare none; a test fails on any, so a route can't
ship open by accident.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

#: Marks set by the access dependencies; K2 adds member and permission.
ACCESS_MARK = "__devkit_access__"


def public() -> None:
    """Anyone may call this route, signed in or not."""


setattr(public, ACCESS_MARK, "public")


def access_of(call: Callable[..., Any]) -> str | None:
    return getattr(call, ACCESS_MARK, None)


def _declared(dependant: Dependant) -> list[str]:
    found: list[str] = []
    stack = [dependant]
    while stack:
        dependant = stack.pop()
        if dependant.call is not None and (mark := access_of(dependant.call)):
            found.append(mark)
        stack.extend(dependant.dependencies)
    return found


def undeclared(app: FastAPI) -> list[str]:
    """`METHOD /path` for each API route that declares no access."""
    missing: list[str] = []
    # FastAPI keeps included routers whole; iter_route_contexts walks them with
    # their prefixes and router-level dependencies applied.
    for context in iter_route_contexts(app.routes):
        if not isinstance(context.original_route, APIRoute) or not (context.path or "").startswith(
            "/api/"
        ):
            continue
        if not _declared(context.dependant):
            missing.extend(f"{method} {context.path}" for method in sorted(context.methods or ()))
    return missing
