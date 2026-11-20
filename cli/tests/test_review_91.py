"""The reviews of #91 (Codex, CodeRabbit): the installed CLI brings what it
imports; a version semver refuses is a refusal everywhere, never a crash; a
recorded file that can't be read is a refusal too."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from mechframe import check, lock, source
from mechframe.__main__ import main

from .conftest import advisory, set_advisories


def test_installing_the_cli_installs_what_it_imports() -> None:
    project = tomllib.loads((source.ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    assert any(need.startswith("jsonschema") for need in project["dependencies"])


def _lock_with(site: Path, version: str) -> None:
    path = site / lock.NAME
    data = json.loads(path.read_text("utf-8"))
    data["modules"]["demo-shop"]["version"] = version
    path.write_text(json.dumps(data), encoding="utf-8")


def test_the_lock_s_schema_refuses_a_version_semver_refuses(site: Path, checkout: Path) -> None:
    data = lock.read(site, root=checkout)
    data["modules"]["demo-shop"]["version"] = "0.1.0-01"
    with pytest.raises(lock.LockError, match=r"0.1.0-01"):
        lock.write(site, data, root=checkout)


def test_a_lock_version_semver_refuses_is_a_refusal(
    site: Path, checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _lock_with(site, "0.1.0-01")
    report = check.check(site, root=checkout)
    assert report.exit_code() == 2
    assert any("demo-shop" in problem and "0.1.0-01" in problem for problem in report.problems)
    assert main(["check", "--site", str(site), "--root", str(checkout), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["exit"] == 2


@pytest.mark.parametrize("field", ["introduced", "fixed"])
def test_an_advisory_version_semver_refuses_is_a_refusal(
    site: Path, checkout: Path, field: str
) -> None:
    set_advisories(checkout, advisory(**{field: "0.1.0-01"}))
    report = check.check(site, root=checkout)
    assert report.exit_code() == 2
    assert any("0.1.0-01" in problem for problem in report.problems)
    assert report.advisories == []


def test_a_checkout_version_semver_refuses_is_a_refusal(site: Path, checkout: Path) -> None:
    path = checkout / "modules" / "demo-shop" / "module.json"
    data = json.loads(path.read_text("utf-8"))
    data["version"] = "0.2.0-01"
    path.write_text(json.dumps(data), encoding="utf-8")
    report = check.check(site, root=checkout)
    assert report.exit_code() == 2
    assert any("checkout's demo-shop" in problem for problem in report.problems)


def test_a_recorded_file_that_can_t_be_read_is_a_refusal(
    site: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = check.digest

    def refuse(path: Path) -> str:
        if path.name == "sessions.py":
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(check, "digest", refuse)
    report = check.check(site, root=checkout)
    assert report.exit_code() == 2
    assert any(
        problem.startswith("backend/kernel/auth/sessions.py: can't be read")
        for problem in report.problems
    )


#: Where the CLI's install is written down for people and agents.
INSTALL_DOCS = (
    "cli/README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "pyproject.toml",
    "cli/mechframe/__init__.py",
)


def test_the_install_fetches_nothing_unpinned() -> None:
    """SPEC 15: Python dependencies are hash-pinned and audited. The CLI's install
    takes them from the pinned requirements and fetches nothing (CodeRabbit on #91)."""
    pins = (source.ROOT / "requirements-dev.txt").read_text("utf-8")
    assert "\nsetuptools==" in pins  # the build backend, for --no-build-isolation
    assert "\njsonschema==" in pins
    for name in INSTALL_DOCS:
        text = (source.ROOT / name).read_text("utf-8")
        assert "pip install -e ." not in text, name
        assert "pip install --no-deps --no-build-isolation -e ." in text, name
