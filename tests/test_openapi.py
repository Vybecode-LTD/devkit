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

import json
import types
from pathlib import Path
from typing import Annotated, Any, Union, get_args, get_origin

from fastapi import FastAPI
from jsonschema import Draft202012Validator

import kernel
from kernel import openapi as documents
from kernel.answers import Answer
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


def test_routes_build_json_only_through_answer() -> None:
    """A route that sets cookies or headers builds its JSON with `answer`, so
    it's checked against its model too; only problems are built elsewhere."""
    allowed = {"answers.py", "errors.py"}
    base = Path(kernel.__file__).parent
    offenders = sorted(
        str(path.relative_to(base))
        for path in base.rglob("*.py")
        if path.name not in allowed and "JSONResponse(" in path.read_text(encoding="utf-8")
    )
    assert offenders == []


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
