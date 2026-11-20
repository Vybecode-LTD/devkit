"""`mechframe create-owner <email>` (the K5 contract §2; decision 0051): the
site's own `python -m app.owner`, with its `.venv` and `backend` on the path,
its output and exit code passed through. Here the site's `app.owner` is a
stand-in that shows what it was given."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mechframe import owner
from mechframe.__main__ import main

from .conftest import write

STAND_IN = """import os
import sys

print("app.owner got", sys.argv[1:], "with", os.environ.get("PYTHONPATH"), "in", os.getcwd())
sys.exit(3)
"""


def _create(root: Path, site: Path, email: str = "owner@site.test") -> int:
    return main(["create-owner", email, "--site", str(site), "--root", str(root)])


def test_it_runs_the_sites_own_command_and_answers_its_exit(
    site_maker: Path,
    made: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    write(made / "backend" / "app" / "__init__.py", "")
    write(made / "backend" / "app" / "owner.py", STAND_IN)
    monkeypatch.setattr(owner, "site_python", lambda _site: Path(sys.executable))
    monkeypatch.setenv("PYTHONPATH", "somewhere/else")
    assert _create(site_maker, made) == 3
    out = capfd.readouterr().out
    assert "app.owner got ['owner@site.test'] with backend in" in out
    assert str(made) in out


def test_a_site_without_its_venv_is_refused(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _create(site_maker, made) == 2
    assert "has no .venv yet" in capsys.readouterr().err


def test_a_folder_that_isnt_a_site_is_refused(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "plain").mkdir()
    assert _create(site_maker, tmp_path / "plain") == 2
    assert "is this a MechFrame site?" in capsys.readouterr().err


def test_the_sites_python_is_its_venvs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(owner.sys, "platform", "win32")
    assert owner.site_python(tmp_path) == tmp_path / ".venv" / "Scripts" / "python.exe"
    monkeypatch.setattr(owner.sys, "platform", "linux")
    assert owner.site_python(tmp_path) == tmp_path / ".venv" / "bin" / "python"
