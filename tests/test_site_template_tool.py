"""tools/site_template.py: the template's web package held to the root's. Its
writing needs npm and the registry, so the repo's own run is the check here
(`--check`), with a copy whose versions drift to see it fail."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools import site_template


@pytest.fixture
def copy(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    web = root / "templates" / "site" / "web"
    web.mkdir(parents=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(site_template.ROOT / name, root / name)
        shutil.copyfile(site_template.WEB / name, web / name)
    return root, web


def _edit(path: Path, change: dict[str, object]) -> None:
    data = json.loads(path.read_text("utf-8"))
    data.update(change)
    path.write_text(json.dumps(data), "utf-8")


def test_the_repos_template_is_current() -> None:
    assert site_template.problems() == []
    assert site_template.main(["--check"]) == 0


def test_a_root_dependency_bumped_leaves_the_template_behind(copy: tuple[Path, Path]) -> None:
    root, web = copy
    found = json.loads((root / "package.json").read_text("utf-8"))
    found["dependencies"]["react"] = "99.0.0"
    (root / "package.json").write_text(json.dumps(found), "utf-8")
    problems = site_template.problems(root, web)
    assert "templates/site/web/package.json is behind the root's package.json." in problems


def test_a_lockfile_at_another_version_is_named(copy: tuple[Path, Path]) -> None:
    root, web = copy
    lock = json.loads((web / "package-lock.json").read_text("utf-8"))
    lock["packages"]["node_modules/react"]["version"] = "18.0.0"
    (web / "package-lock.json").write_text(json.dumps(lock), "utf-8")
    assert site_template.problems(root, web) == [
        "react is locked at 18.0.0 in the template, not the root's version."
    ]


def test_an_unreadable_template_is_a_problem(copy: tuple[Path, Path]) -> None:
    root, web = copy
    (web / "package-lock.json").write_text("{not json", "utf-8")
    (problem,) = site_template.problems(root, web)
    assert problem.startswith("templates/site/web can't be read")


def test_the_package_keeps_the_roots_notes(copy: tuple[Path, Path]) -> None:
    root, _web = copy
    _edit(root / "package.json", {"//": ["a note"]})
    assert site_template.package(root)["//"] == [site_template.NOTE, "a note"]


def test_an_unknown_argument_is_refused() -> None:
    assert site_template.main(["--write"]) == 2


def test_write_makes_both_files_from_the_roots(
    copy: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """npm stood in for: it's handed the root's lockfile without its workspaces,
    and its answer is written back under the template's name."""
    root, web = copy
    shutil.copyfile(site_template.WEB / ".npmrc", web / ".npmrc")
    (web / "package.json").write_text("{}", "utf-8")
    seen: dict[str, object] = {}

    def npm(command: list[str], *, cwd: Path, check: bool) -> None:
        seen["command"] = command
        seed = json.loads((cwd / "package-lock.json").read_text("utf-8"))
        seen["keys"] = [
            key for key in seed["packages"] if key and not key.startswith("node_modules/")
        ]
        seen["links"] = [key for key, value in seed["packages"].items() if value.get("link")]
        seed["packages"][""] = {
            **json.loads((cwd / "package.json").read_text("utf-8")),
            "name": "probe",
        }
        (cwd / "package-lock.json").write_text(json.dumps(seed), "utf-8")

    monkeypatch.setattr(site_template.subprocess, "run", npm)
    site_template.write(root, web, npm="npm")
    assert seen["command"] == [
        "npm",
        "install",
        "--package-lock-only",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
    ]
    assert seen["keys"] == []
    assert seen["links"] == []
    assert json.loads((web / "package.json").read_text("utf-8")) == site_template.package(root)
    lock = json.loads((web / "package-lock.json").read_text("utf-8"))
    assert (lock["name"], lock["packages"][""]["name"]) == ("site-web", "site-web")
    assert site_template.problems(root, web) == []


def test_main_writes_then_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    written: list[bool] = []
    monkeypatch.setattr(site_template, "write", lambda: written.append(True))
    monkeypatch.setattr(site_template, "problems", lambda: ["react is locked at 1.0.0."])
    assert site_template.main([]) == 1
    assert written == [True]
    out = capsys.readouterr().out
    assert "react is locked at 1.0.0." in out
    assert "Run `python -m tools.site_template`" in out
