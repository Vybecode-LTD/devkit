"""Codex's review of #91: the installed CLI brings what it imports, and a
version the lock's schema lets through but semver doesn't is a refusal, not a crash."""

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


def test_a_lock_version_semver_refuses_is_a_refusal(
    site: Path, checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = lock.read(site, root=checkout)
    data["modules"]["demo-shop"]["version"] = "0.1.0-01"  # the schema's pattern allows it
    lock.write(site, data, root=checkout)
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
    assert any(
        f"MF-2026-0001's {field}" in problem and "0.1.0-01" in problem
        for problem in report.problems
    )
    assert report.advisories == []
