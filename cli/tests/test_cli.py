"""The CLI runs as `python -m mechframe`, and installed as `mechframe` and `mf`."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from mechframe import source
from mechframe.__main__ import main


def test_python_m_mechframe_runs_from_the_checkout() -> None:
    env = {**os.environ, "PYTHONPATH": str(source.ROOT / "cli")}
    done = subprocess.run(
        [sys.executable, "-m", "mechframe", "--help"],
        capture_output=True,
        text=True,
        env=env,
        cwd=source.ROOT,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "catalog" in done.stdout
    assert "check" in done.stdout


def test_installed_it_answers_to_mechframe_and_mf() -> None:
    project = tomllib.loads((source.ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    assert project["scripts"] == {
        "mechframe": "mechframe.__main__:main",
        "mf": "mechframe.__main__:main",
    }


def test_the_source_is_this_checkout() -> None:
    assert (source.ROOT / "kernel" / "kernel.json").is_file()
    assert Path(__file__).resolve().parents[2] == source.ROOT


def test_a_command_not_built_yet_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["upgrade", "blog"])
    assert stopped.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
