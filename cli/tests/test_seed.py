"""`mechframe seed [--site <dir>]` (hook 4, decision 0052): the site's own
`python -m app.seed`, run as `create-owner` runs `app.owner`, with its
`.venv` and `backend` on the path and the caller's environment (where
MECHFRAME_ALLOW_SEED is or isn't), its output and exit code passed through.
Here the site's `app.seed` is a stand-in that shows what it was given."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mechframe import owner
from mechframe.__main__ import main

from .conftest import write

STAND_IN = """import os
import sys

print("app.seed got", sys.argv[1:], "with", os.environ.get("PYTHONPATH"),
      "allowed", os.environ.get("MECHFRAME_ALLOW_SEED"), "in", os.getcwd())
sys.exit(4)
"""


def _seed(root: Path, site: Path) -> int:
    return main(["seed", "--site", str(site), "--root", str(root)])


def test_it_runs_the_sites_own_command_and_answers_its_exit(
    site_maker: Path,
    made: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    write(made / "backend" / "app" / "__init__.py", "")
    write(made / "backend" / "app" / "seed.py", STAND_IN)
    monkeypatch.setattr(owner, "site_python", lambda _site: Path(sys.executable))
    monkeypatch.setenv("PYTHONPATH", "somewhere/else")
    monkeypatch.setenv("MECHFRAME_ALLOW_SEED", "1")
    assert _seed(site_maker, made) == 4
    out = capfd.readouterr().out
    assert "app.seed got [] with backend allowed 1 in" in out
    assert str(made) in out


def test_a_site_without_its_venv_is_refused(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _seed(site_maker, made) == 2
    assert "has no .venv yet" in capsys.readouterr().err


def test_a_folder_that_isnt_a_site_is_refused(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "plain").mkdir()
    assert _seed(site_maker, tmp_path / "plain") == 2
    assert "is this a MechFrame site?" in capsys.readouterr().err
