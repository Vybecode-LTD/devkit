"""Every error is RFC 9457 problem details with a stable code (SPEC.md section 7)."""

from __future__ import annotations

import logging

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from kernel.errors import MEDIA_TYPE, Problem, install_handlers


class Body(BaseModel):
    email: str
    count: int


def app() -> FastAPI:
    application = FastAPI()
    install_handlers(application)

    @application.get("/missing-post")
    async def missing() -> None:
        raise Problem("blog.post_not_found", 404, "There's no post at that address.")

    @application.post("/things")
    async def things(body: Body) -> dict[str, int]:
        return {"count": body.count}

    @application.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret detail: postgres://user:pw@db")

    @application.get("/conflict")
    async def conflict() -> None:
        raise Problem(
            "blog.slug_taken",
            409,
            "That address is taken.",
            errors={"slug": ["Taken."]},
            extra={"suggestion": "my-post-2"},
            headers={"X-Hint": "1"},
        )

    return application


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app(), raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="https://devkit.test")


async def test_a_problem(client: httpx.AsyncClient) -> None:
    response = await client.get("/missing-post")
    assert response.status_code == 404
    assert response.headers["content-type"] == MEDIA_TYPE
    assert response.json() == {
        "type": "urn:devkit:problem:blog.post_not_found",
        "title": "Not Found",
        "status": 404,
        "detail": "There's no post at that address.",
        "code": "blog.post_not_found",
    }


async def test_errors_extra_and_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/conflict")
    body = response.json()
    assert (response.status_code, body["code"], body["errors"], body["suggestion"]) == (
        409,
        "blog.slug_taken",
        {"slug": ["Taken."]},
        "my-post-2",
    )
    assert response.headers["x-hint"] == "1"


async def test_routing_errors(client: httpx.AsyncClient) -> None:
    response = await client.get("/nowhere")
    assert (response.status_code, response.json()["code"], response.json()["detail"]) == (
        404,
        "kernel.not_found",
        "",
    )
    response = await client.delete("/things")
    assert (response.status_code, response.json()["code"]) == (405, "kernel.method_not_allowed")


async def test_validation_errors_by_field(client: httpx.AsyncClient) -> None:
    response = await client.post("/things", json={"count": "many"})
    body = response.json()
    assert (response.status_code, body["code"]) == (422, "kernel.invalid_request")
    assert set(body["errors"]) == {"body.email", "body.count"}
    assert response.headers["content-type"] == MEDIA_TYPE


async def test_unexpected_errors_say_nothing(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="kernel.errors"):
        response = await client.get("/boom")
    assert response.status_code == 500
    assert response.json()["code"] == "kernel.internal_error"
    assert "secret" not in response.text
    assert "postgres" not in response.text
    assert caplog.records[0].getMessage() == "unhandled error on GET /boom"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("NotACode", 400), "isn't a problem code"),
        (("blog.ok", 200), "4xx or 5xx"),
    ],
)
def test_bad_problems_are_refused(args: tuple[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Problem(*args)


def test_extra_cant_overwrite_the_shape() -> None:
    with pytest.raises(ValueError, match="extra can't set code, status"):
        Problem("blog.x", 400, extra={"status": 200, "code": "y"})
