"""SPEC.md 14.13: a route with no declared access fails the route audit.

The audit itself is `/api/_test/routes`' `undeclared` list; the case of a
route that does lack one is a unit test (kernel/tests/test_app.py).
"""

from __future__ import annotations

from .conftest import Api


async def test_no_route_lacks_a_declared_access(api: Api) -> None:
    assert (await api.http.get("/api/_test/routes")).json()["undeclared"] == []
