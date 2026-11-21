"""The repo's manifests validate, and the checker catches what it should."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.validate_schemas import ROOT, check, main


def test_the_repo_validates() -> None:
    report = check()
    assert report.problems == []
    assert report.checked >= 9


def test_main_exits_zero_on_the_repo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "0 problems: ok" in capsys.readouterr().out


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of the repo's schemas, recipes and kernel manifest, with one module."""
    for name in ("schema", "recipes"):
        shutil.copytree(ROOT / name, tmp_path / name)
    (tmp_path / "kernel").mkdir()
    shutil.copy(ROOT / "kernel" / "kernel.json", tmp_path / "kernel" / "kernel.json")
    for name in ("catalog.json", "advisories.json"):
        shutil.copy(ROOT / name, tmp_path / name)
    manifest = json.loads((ROOT / "modules" / "_template" / "module.json").read_text("utf-8"))
    manifest["id"] = "print-on-demand"
    manifest["tables"] = ["print_on_demand_order"]
    manifest["permissions"] = [
        {
            "key": "print-on-demand.order.manage",
            "description": "Manage orders",
            "default_roles": ["admin"],
        }
    ]
    manifest["notifications"] = []
    folder = tmp_path / "modules" / "print-on-demand"
    (folder / "backend" / "print_on_demand").mkdir(parents=True)
    (folder / "module.json").write_text(json.dumps(manifest), "utf-8")
    return tmp_path


def _edit(repo: Path, **changes: object) -> None:
    path = repo / "modules" / "print-on-demand" / "module.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest.update(changes)
    path.write_text(json.dumps(manifest), "utf-8")


def test_a_good_module_passes(repo: Path) -> None:
    report = check(repo)
    assert report.problems == []
    assert "print-on-demand" not in report.planned


def test_a_schema_error_is_named(repo: Path) -> None:
    _edit(repo, status="beta")
    (problem,) = check(repo).problems
    assert problem.startswith("modules/print-on-demand/module.json: status:")


def test_a_table_outside_the_prefix_fails(repo: Path) -> None:
    _edit(repo, tables=["orders"])
    assert check(repo).problems == [
        "modules/print-on-demand/module.json: table 'orders' should start with print_on_demand_"
    ]


def test_a_permission_outside_the_id_fails(repo: Path) -> None:
    _edit(
        repo,
        permissions=[
            {"key": "shop.order.manage", "description": "Manage orders", "default_roles": []}
        ],
    )
    assert (
        "permission 'shop.order.manage' should start with print-on-demand."
        in check(repo).problems[0]
    )


def test_the_backend_package_uses_underscores(repo: Path) -> None:
    folder = repo / "modules" / "print-on-demand" / "backend"
    (folder / "print_on_demand").rename(folder / "print-on-demand")
    assert check(repo).problems == [
        "modules/print-on-demand/module.json: the backend package should be backend/print_on_demand/"
    ]


def test_the_folder_must_match_the_id(repo: Path) -> None:
    (repo / "modules" / "print-on-demand").rename(repo / "modules" / "pod")
    assert "the folder is 'pod' but the id is 'print-on-demand'" in check(repo).problems[0]


def test_unreadable_json_is_a_problem(repo: Path) -> None:
    (repo / "recipes" / "minimal.json").write_text("{not json", "utf-8")
    assert check(repo).problems[0].startswith("recipes/minimal.json: can't be read as JSON")


def test_an_advisory_is_checked_against_its_schema(repo: Path) -> None:
    entry = {
        "id": "MF-2026-0001",
        "module": "kernel",
        "introduced": "0.1.0",
        "fixed": None,
        "severity": "high",
        "summary": "Something the kernel got wrong",
    }
    path = repo / "advisories.json"
    path.write_text(json.dumps({"advisories": [entry]}), "utf-8")
    assert check(repo).problems == []
    path.write_text(json.dumps({"advisories": [{**entry, "severity": "severe"}]}), "utf-8")
    (problem,) = check(repo).problems
    assert problem.startswith("advisories.json: advisories/0/severity")


def test_advisories_that_are_json_null_are_checked_not_skipped(repo: Path) -> None:
    (repo / "advisories.json").write_text("null", "utf-8")
    (problem,) = check(repo).problems
    assert problem.startswith("advisories.json: (top)")


def test_a_version_semver_refuses_fails_the_schema(repo: Path) -> None:
    _edit(repo, version="0.1.0-01")  # semver: no leading zero in a numeric pre-release part
    assert any("version" in problem for problem in check(repo).problems)


def test_main_exits_one_on_a_problem(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(repo, status="beta")
    assert main([str(repo)]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_the_kernel_declares_only_its_own_permissions(repo: Path) -> None:
    path = repo / "kernel" / "kernel.json"
    data = json.loads(path.read_text("utf-8"))
    data["permissions"].append(
        {"key": "blog.post.edit", "description": "Not the kernel's", "default_roles": []}
    )
    path.write_text(json.dumps(data), "utf-8")
    assert any("kernel.json" in problem for problem in check(repo).problems)


@pytest.mark.parametrize("taken", ["auth", "kernel", "site"])
def test_a_module_may_not_take_the_kernels_own_ids(taken: str) -> None:
    """`site` is the key of the site's own pages and links (decision 0048), as
    `auth` and `kernel` are the kernel's routes and branch."""
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "schema" / "module.schema.json").read_text("utf-8"))
    manifest = json.loads((ROOT / "modules" / "_template" / "module.json").read_text("utf-8"))
    manifest["id"] = taken
    errors = list(Draft202012Validator(schema).iter_errors(manifest))
    assert any(list(error.absolute_path) == ["id"] for error in errors)


# --- content_types (decision 0052: the lifecycle, taxonomy and search hooks) -----------

_DESIGN = {"key": "print-on-demand.design", "label": "Design", "lifecycle": True}


def test_content_types_are_optional_and_pass_with_the_modules_own_keys(repo: Path) -> None:
    _edit(repo, content_types=[_DESIGN, {"key": "print-on-demand.mockup", "label": "Mockup"}])
    assert check(repo).problems == []


def test_a_content_type_outside_the_id_fails(repo: Path) -> None:
    _edit(repo, content_types=[{"key": "shop.product", "label": "Product"}])
    assert check(repo).problems == [
        "modules/print-on-demand/module.json: content type 'shop.product' should start with "
        "print-on-demand."
    ]


def test_a_content_type_listed_twice_fails(repo: Path) -> None:
    _edit(repo, content_types=[_DESIGN, {**_DESIGN, "label": "Again"}])
    assert check(repo).problems == [
        "modules/print-on-demand/module.json: content type 'print-on-demand.design' is "
        "listed twice"
    ]


@pytest.mark.parametrize(
    ("entry", "where"),
    [
        ({"key": "print-on-demand.design"}, "content_types/0"),
        ({"key": "print-on-demand", "label": "Design"}, "content_types/0/key"),
        ({**_DESIGN, "lifecycle": "yes"}, "content_types/0/lifecycle"),
        ({**_DESIGN, "colour": "red"}, "content_types/0"),
    ],
)
def test_a_content_type_breaking_the_schema_is_named(
    repo: Path, entry: dict[str, object], where: str
) -> None:
    _edit(repo, content_types=[entry])
    (problem,) = check(repo).problems
    assert problem.startswith(f"modules/print-on-demand/module.json: {where}:")


# --- vocabularies (decision 0052, hook 2: taxonomy) --------------------------------------

_TOPICS = {"key": "topics", "label": "Topics", "hierarchical": True}


def test_vocabularies_pass_and_a_content_type_takes_its_modules_own(repo: Path) -> None:
    _edit(
        repo,
        vocabularies=[_TOPICS, {"key": "styles", "label": "Styles"}],
        content_types=[{**_DESIGN, "taxonomy": ["topics", "styles"]}],
    )
    assert check(repo).problems == []


def test_a_content_type_taking_a_vocabulary_its_module_lacks_fails(repo: Path) -> None:
    _edit(repo, vocabularies=[_TOPICS], content_types=[{**_DESIGN, "taxonomy": ["tags"]}])
    assert check(repo).problems == [
        "modules/print-on-demand/module.json: content type 'print-on-demand.design' takes "
        "'tags', which its vocabularies don't declare"
    ]


def test_a_vocabulary_listed_twice_fails(repo: Path) -> None:
    _edit(repo, vocabularies=[_TOPICS, {**_TOPICS, "label": "Again"}])
    assert check(repo).problems == [
        "modules/print-on-demand/module.json: vocabulary 'topics' is listed twice"
    ]


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"vocabularies": [{"key": "Topics", "label": "Topics"}]}, "vocabularies/0/key"),
        ({"vocabularies": [{"key": "topics"}]}, "vocabularies/0"),
        ({"vocabularies": [{**_TOPICS, "hierarchical": "yes"}]}, "vocabularies/0/hierarchical"),
        ({"vocabularies": [{**_TOPICS, "colour": "red"}]}, "vocabularies/0"),
        ({"content_types": [{**_DESIGN, "taxonomy": "topics"}]}, "content_types/0/taxonomy"),
        (
            {"vocabularies": [_TOPICS], "content_types": [{**_DESIGN, "taxonomy": ["topics"] * 2}]},
            "content_types/0/taxonomy",
        ),
    ],
)
def test_a_vocabulary_breaking_the_schema_is_named(
    repo: Path, changes: dict[str, object], where: str
) -> None:
    _edit(repo, **changes)
    (problem,) = check(repo).problems
    assert problem.startswith(f"modules/print-on-demand/module.json: {where}:")
