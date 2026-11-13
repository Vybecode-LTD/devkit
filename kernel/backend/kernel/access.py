"""Every route declares who may call it (SPEC.md section 7, 14.13).

A route is **public** (`Depends(public)`), for **members** (`current_user`,
K2) or behind a **permission** (`require_permission(key)`, K2). `undeclared`
lists every API route under /api/ whose access is missing or can't be right;
a test fails on any, so a route can't ship open by accident:

- an HTTP or WebSocket route that declares nothing;
- an admin route (a path segment `admin`) whose only mark is `public`, often
  from a router-level dependency;
- `public` beside another mark, which can't both hold;
- an app mounted under /api/, whose routes can't be audited at all.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIWebSocketRoute, iter_route_contexts
from starlette.routing import Mount

#: Marks set by the access dependencies; K2 adds member and permission.
ACCESS_MARK = "__devkit_access__"
#: Set by `require_recent_auth` (K2), so the step-up routes can be listed.
STEP_UP_MARK = "__devkit_step_up__"


def public() -> None:
    """Anyone may call this route, signed in or not."""


setattr(public, ACCESS_MARK, "public")


def access_of(call: Callable[..., Any]) -> str | None:
    return getattr(call, ACCESS_MARK, None)


def needs_step_up(dependant: Dependant) -> bool:
    """Whether any dependency of a route asks for a recent sign-in."""
    stack = [dependant]
    while stack:
        dependant = stack.pop()
        if dependant.call is not None and getattr(dependant.call, STEP_UP_MARK, False):
            return True
        stack.extend(dependant.dependencies)
    return False


def _declared(dependant: Dependant) -> list[str]:
    found: list[str] = []
    stack = [dependant]
    while stack:
        dependant = stack.pop()
        if dependant.call is not None and (mark := access_of(dependant.call)):
            found.append(mark)
        stack.extend(dependant.dependencies)
    return found


def _problem(path: str, marks: list[str]) -> str | None:
    """What's wrong with these marks on this path, or None."""
    kinds = set(marks)
    if "public" in kinds and len(kinds) > 1:
        return "public beside " + ", ".join(sorted(kinds - {"public"}))
    if kinds == {"public"} and "admin" in path.split("/"):
        return "an admin route can't be public"
    return None


def undeclared(app: FastAPI) -> list[str]:
    """`METHOD /path`, with the reason when one helps, for each API route whose
    access is missing or can't be right. Sorted."""
    found: list[str] = []
    # FastAPI keeps included routers whole; iter_route_contexts walks them with
    # their prefixes and router-level dependencies applied.
    for context in iter_route_contexts(app.routes):
        path = context.path or ""
        if not path.startswith("/api/") and path != "/api":
            continue
        route = context.original_route
        if isinstance(route, Mount):
            found.append(f"MOUNT {path} (a mounted app under /api can't declare access)")
            continue
        if isinstance(route, APIWebSocketRoute):
            methods = ["WEBSOCKET"]
        elif isinstance(route, APIRoute):
            methods = sorted(context.methods or ())
        else:
            continue
        marks = _declared(context.dependant)
        reason = None if not marks else _problem(path, marks)
        if marks and reason is None:
            continue
        suffix = f" ({reason})" if reason else ""
        found.extend(f"{method} {path}{suffix}" for method in methods)
    return sorted(found)
