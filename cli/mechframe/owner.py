"""`mechframe create-owner <email> [--site <dir>]` (the K5 contract §2; decision 0051).

It runs the site's own `python -m app.owner <email>` with the site's `.venv`
Python and `backend` on the path, in the site's folder, so the owner is made
with the site's settings (its database and SECRET_KEY, from its environment
or `.env`). Its output and exit code are the command's: the one-time link to
set the owner's password, or why it refused.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mechframe import lock
from mechframe.source import ROOT


class Refused(Exception):
    """Nothing ran; the message says why."""


def site_python(site: Path) -> Path:
    """The site's own Python, in its `.venv`."""
    if sys.platform == "win32":
        return site / ".venv" / "Scripts" / "python.exe"
    return site / ".venv" / "bin" / "python"


def create_owner(site: Path, email: str, *, root: Path = ROOT) -> int:
    """Run the site's `app.owner`; its exit code. Raises Refused when it can't."""
    try:
        lock.read(site, root)
    except lock.LockError as error:
        raise Refused("; ".join(error.problems)) from None
    python = site_python(site)
    if not python.is_file():
        raise Refused(
            f"{site} has no .venv yet: make it first, as its README.md says "
            "(py -3.12 -m venv .venv, then pip install --require-hashes from its pins)."
        )
    env = {
        key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "VIRTUAL_ENV")
    }
    env["PYTHONPATH"] = "backend"
    finished = subprocess.run(  # noqa: S603 (the site's own Python, on its own module)
        [str(python), "-m", "app.owner", email], cwd=site, env=env, check=False
    )
    return finished.returncode
