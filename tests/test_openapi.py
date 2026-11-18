"""Every API route's answer is typed, and the committed OpenAPI specs are current
(K4, decision 0042; SPEC.md 7 and 18).

The web kernel's client is generated from `kernel/openapi.json`, so a route
whose answer is `dict[str, Any]` would leave the client blind to what comes
back. Every answer is an `Answer` model that refuses keys it doesn't name, and
every JSON answer goes out through it: a dict a route returns is checked by
FastAPI, and a response a route builds for its cookies or headers goes through
`kernel.answers.answer`. So an answer can't drift from its model without a
test seeing a 500.
"""

from __future__ import annotations

import ast
import json
import types
from pathlib import Path
from typing import Annotated, Any, Union, get_args, get_origin

import httpx
import pytest
from fastapi import FastAPI
from jsonschema import Draft202012Validator
from pydantic import ValidationError

import kernel
from harness.layout import backend_dirs
from kernel import openapi as documents
from kernel.answers import Answer, answer
from tools import openapi

ROOT = Path(__file__).resolve().parent.parent


def _typed(answer: Any) -> bool:
    """An `Answer` model, or a union of them (an answer with a `status` that says which)."""
    if isinstance(answer, type) and issubclass(answer, Answer):
        return True
    if get_origin(answer) is Annotated:
        return _typed(get_args(answer)[0])
    if get_origin(answer) in (Union, types.UnionType):
        return all(_typed(arg) for arg in get_args(answer))
    return False


def _app() -> FastAPI:
    return openapi.build_app()


def test_every_api_route_declares_a_typed_answer() -> None:
    untyped = [
        f"{','.join(sorted(route.methods))} {path}"
        for path, route in openapi.api_routes(_app())
        if route.status_code != 204 and not _typed(route.response_model)
    ]
    assert untyped == []


def test_a_204_route_declares_no_body() -> None:
    bodied = [
        path
        for path, route in openapi.api_routes(_app())
        if route.status_code == 204 and route.response_model is not None
    ]
    assert bodied == []


#: The only files that may build a JSONResponse: `answer` itself, and problems.
RAW_JSON_ALLOWED = {"kernel/answers.py", "kernel/errors.py"}


def _builds_json(source: str) -> bool:
    """Whether code builds a JSON response other than through `answer`: it
    imports JSONResponse under any name, reaches it as an attribute, or makes
    a response whose `media_type` is JSON (cubic on #78: a text search missed
    aliases and a plain Response)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == "JSONResponse" for alias in node.names
        ):
            return True
        if isinstance(node, ast.Attribute) and node.attr == "JSONResponse":
            return True
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                value = keyword.value
                if (
                    keyword.arg == "media_type"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and "json" in value.value
                ):
                    return True
    return False


def _raw_json(roots: list[Path]) -> list[str]:
    """Each backend file under `roots` that builds a JSON response itself."""
    found = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            name = path.relative_to(root).as_posix()
            if name not in RAW_JSON_ALLOWED and _builds_json(path.read_text("utf-8")):
                found.append(name)
    return found


def test_routes_build_json_only_through_answer() -> None:
    """A route that sets cookies or headers builds its JSON with `answer`, so
    it's checked against its model too; only problems are built elsewhere.
    The kernel's backend and every module's (CodeRabbit on #78)."""
    assert _raw_json(backend_dirs()) == []


def test_the_json_guard_reads_a_module_s_backend_too(tmp_path: Path) -> None:
    kernel_dir, module_dir = tmp_path / "kernel" / "backend", tmp_path / "blog" / "backend"
    (kernel_dir / "kernel").mkdir(parents=True)
    (kernel_dir / "kernel" / "errors.py").write_text(
        "from starlette.responses import JSONResponse", encoding="utf-8"
    )
    (module_dir / "blog").mkdir(parents=True)
    (module_dir / "blog" / "router.py").write_text(MODULE_ROUTE_OUTSIDE_ANSWER, encoding="utf-8")
    assert _raw_json([kernel_dir, module_dir]) == ["blog/router.py"]


#: A module's route as the guard must catch it: a declared model, and an
#: answer built by hand with a key the model doesn't name (CodeRabbit on #78).
MODULE_ROUTE_OUTSIDE_ANSWER = """from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kernel import Answer

router = APIRouter()


class Posts(Answer):
    items: list[str]


@router.get("/posts", response_model=Posts)
async def posts() -> JSONResponse:
    return JSONResponse({"items": [], "drafts": ["unpublished"]})
"""


async def test_a_route_that_builds_its_own_json_escapes_its_model_and_answer_stops_it() -> None:
    """Why the guard exists: FastAPI never checks a response a route builds,
    so the undeclared key goes out; built with `answer`, it can't."""
    namespace: dict[str, Any] = {}
    exec(compile(MODULE_ROUTE_OUTSIDE_ANSWER, "router.py", "exec"), namespace)  # noqa: S102
    app = FastAPI()
    app.include_router(namespace["router"], prefix="/api/blog")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://mechframe.test"
    ) as client:
        leaked = (await client.get("/api/blog/posts")).json()
    assert leaked == {"items": [], "drafts": ["unpublished"]}

    posts = namespace["Posts"]
    checked = FastAPI()

    @checked.get("/api/blog/posts", response_model=posts)
    async def through_answer() -> Any:
        return answer(posts, {"items": [], "drafts": ["unpublished"]})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=checked), base_url="https://mechframe.test"
    ) as client:
        with pytest.raises(ValidationError, match="drafts"):
            await client.get("/api/blog/posts")


@pytest.mark.parametrize(
    "source",
    [
        "from fastapi.responses import JSONResponse as Out",
        "from fastapi import responses; responses.JSONResponse({})",
        "from fastapi import Response; Response(b'{}', media_type='application/json')",
        "Response(b'{}', media_type='application/problem+json')",
    ],
)
def test_the_json_guard_sees_through_an_alias_or_a_plain_response(source: str) -> None:
    assert _builds_json(source)


def test_the_json_guard_lets_other_answers_be() -> None:
    assert not _builds_json("from fastapi.responses import Response, HTMLResponse")
    assert not _builds_json("Response(status_code=204)")
    assert not _builds_json("FileResponse(path, media_type=kind)")
    assert not _builds_json("HTMLResponse(text, media_type='text/html')")


def test_the_committed_specs_are_current() -> None:
    assert openapi.main(["--check"]) == 0


def test_the_kernel_spec_holds_only_the_kernel_s_paths() -> None:
    spec = openapi.specs()["kernel/openapi.json"]
    paths = list(spec["paths"])
    assert paths
    assert all(path.startswith(("/api/auth/", "/api/kernel/")) for path in paths)
    assert not any(path.startswith("/api/_test") for path in paths)
    assert spec["info"]["title"] == "MechFrame kernel"
    assert spec["info"]["version"] == kernel.__version__


def test_problems_are_documented_as_problem_json() -> None:
    """FastAPI documents its own 422 shape; the kernel answers RFC 9457 problems.
    Every operation's 422 and `default` say so. (A status a route answers with
    a model of its own, as the health check's 503, stays that model.)"""
    spec = openapi.specs()["kernel/openapi.json"]
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    problem = schemas["Problem"]
    assert set(problem["required"]) >= {"type", "title", "status", "detail", "code"}
    seen = 0
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            responses = operation["responses"]
            assert "default" in responses, (method, path)
            for status in ("422", "default"):
                if status in responses:
                    seen += 1
                    content = responses[status]["content"]
                    assert content == {
                        "application/problem+json": {
                            "schema": {"$ref": "#/components/schemas/Problem"}
                        }
                    }, (method, path, status)
    assert seen > len(spec["paths"])
    # A 422 is a refused body or a route's own refusal, such as auth.password_rejected.
    sign_up = spec["paths"]["/api/auth/sign-up"]["post"]["responses"]["422"]
    assert "kernel.invalid_request" in sign_up["description"]
    assert "own code" in sign_up["description"]
    health = spec["paths"]["/api/kernel/health"]["get"]["responses"]["503"]
    assert health["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Health"
    }


def test_every_component_is_used_and_every_reference_resolves() -> None:
    spec = openapi.specs()["kernel/openapi.json"]
    text = json.dumps(spec)
    schemas = spec["components"]["schemas"]
    for name in schemas:
        assert f'"#/components/schemas/{name}"' in text, f"{name} is never used"
    for ref in openapi.references(spec):
        assert ref.removeprefix("#/components/schemas/") in schemas, ref


def test_a_sign_in_answer_is_one_of_two_shapes() -> None:
    spec = openapi.specs()["kernel/openapi.json"]
    ok = spec["paths"]["/api/auth/sign-in"]["post"]["responses"]["200"]
    schema = ok["content"]["application/json"]["schema"]
    assert schema["discriminator"]["propertyName"] == "status"
    assert sorted(schema["discriminator"]["mapping"]) == ["second_factor", "signed_in"]


def test_an_answer_refuses_a_key_it_doesn_t_name() -> None:
    spec = openapi.specs()["kernel/openapi.json"]
    user = spec["components"]["schemas"]["UserView"]
    assert user["additionalProperties"] is False
    validator = Draft202012Validator(user)
    good = {
        "id": "6f1c2b9e-0a43-4c55-9d0c-6a7e2f1b3c4d",
        "email": "a@mechframe.test",
        "roles": ["member"],
        "permissions": [],
        "verified": True,
        "second_factor": False,
    }
    assert validator.is_valid(good)
    assert not validator.is_valid({**good, "password_hash": "x"})


def test_check_finds_a_stale_or_left_over_file(tmp_path: Path) -> None:
    assert openapi.main([], root=tmp_path) == 0
    assert (tmp_path / "kernel" / "openapi.json").exists()
    assert openapi.main(["--check"], root=tmp_path) == 0

    (tmp_path / "kernel" / "openapi.json").write_text("{}\n", encoding="utf-8")
    assert openapi.main(["--check"], root=tmp_path) == 1
    openapi.main([], root=tmp_path)

    gone = tmp_path / "modules" / "gone" / "openapi.json"
    gone.parent.mkdir(parents=True)
    gone.write_text("{}\n", encoding="utf-8")
    assert openapi.main(["--check"], root=tmp_path) == 1
    openapi.main([], root=tmp_path)
    assert not gone.exists()
    assert openapi.main(["--check"], root=tmp_path) == 0


def test_a_module_owns_its_paths_and_the_kernel_its_own() -> None:
    assert documents.owner("/api/blog/posts/{id}") == "blog"
    assert documents.owner("/api/print-on-demand/orders") == "print-on-demand"
    assert documents.owner("/api/auth/sign-in") == "kernel"
    assert documents.owner("/api/kernel/modules") == "kernel"


def test_each_owner_s_document_holds_only_the_schemas_its_paths_use() -> None:
    ref = "#/components/schemas/"
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "A site", "version": "1.2.3"},
        "paths": {
            "/api/blog/posts": {"get": {"responses": {"200": {"$ref": ref + "Posts"}}}},
            "/api/kernel/modules": {"get": {"responses": {"200": {"$ref": ref + "ModulesOn"}}}},
        },
        "components": {
            "schemas": {
                "Posts": {"properties": {"items": {"items": {"$ref": ref + "Post"}}}},
                "Post": {"type": "object"},
                "ModulesOn": {"type": "object"},
                "Unused": {"type": "object"},
            }
        },
    }
    made = documents.by_owner(spec, {"kernel": ("MechFrame kernel", "0.1.0")})
    assert sorted(made) == ["blog", "kernel"]
    assert list(made["blog"]["components"]["schemas"]) == ["Post", "Posts"]
    assert list(made["kernel"]["components"]["schemas"]) == ["ModulesOn"]
    assert made["kernel"]["info"] == {"title": "MechFrame kernel", "version": "0.1.0"}
    # An owner with no title of its own keeps the app's.
    assert made["blog"]["info"] == {"title": "A site", "version": "1.2.3"}


def test_the_app_serves_the_same_document_and_builds_it_once() -> None:
    app = _app()
    first = app.openapi()
    assert app.openapi() is first
    assert first == documents.document(app)


def test_a_route_model_named_problem_is_refused() -> None:
    """The kernel's error schema is `Problem`: a route's model of that name
    would be replaced by it in the document (CodeRabbit on #78)."""

    class Problem(Answer):
        summary: str

    app = FastAPI()

    @app.get("/api/blog/odd", response_model=Problem)
    async def odd() -> dict[str, str]:  # pragma: no cover - never called
        return {"summary": "x"}

    with pytest.raises(ValueError, match="named Problem"):
        documents.document(app)


def test_marking_notices_read_takes_ids_or_all_true_and_nothing_else() -> None:
    spec = openapi.specs()["kernel/openapi.json"]
    body = spec["paths"]["/api/kernel/notifications/read"]["post"]["requestBody"]
    schema = body["content"]["application/json"]["schema"]
    shapes = [ref["$ref"].removeprefix("#/components/schemas/") for ref in schema["anyOf"]]
    assert sorted(shapes) == ["ReadAll", "ReadSome"]
    schemas = spec["components"]["schemas"]
    validators = [Draft202012Validator(schemas[name]) for name in shapes]

    def takes(sent: dict[str, Any]) -> bool:
        return any(validator.is_valid(sent) for validator in validators)

    assert takes({"all": True})
    assert takes({"ids": ["6f1c2b9e-0a43-4c55-9d0c-6a7e2f1b3c4d"]})
    assert takes({"all": True, "ids": None})
    assert not takes({})
    assert not takes({"all": False})
    assert not takes({"ids": []})
    assert not takes({"ids": ["a"] * 101})
    assert not takes({"ids": ["a"], "all": True})


def test_a_spec_saved_in_another_encoding_is_stale_not_an_error(tmp_path: Path) -> None:
    openapi.main([], root=tmp_path)
    spec = tmp_path / "kernel" / "openapi.json"
    spec.write_text(spec.read_text(encoding="utf-8"), encoding="utf-16")
    assert openapi.main(["--check"], root=tmp_path) == 1
    assert openapi.main([], root=tmp_path) == 0
    assert openapi.main(["--check"], root=tmp_path) == 0
