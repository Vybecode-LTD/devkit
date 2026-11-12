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


def test_main_exits_one_on_a_problem(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(repo, status="beta")
    assert main([str(repo)]) == 1
    assert "FAILED" in capsys.readouterr().out
