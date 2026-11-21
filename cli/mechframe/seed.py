"""`mechframe seed [--site <dir>]` (hook 4, decision 0052).

It runs the site's own `python -m app.seed` as `create-owner` runs
`app.owner`: with the site's `.venv` Python and `backend` on the path, in the
site's folder, with the caller's environment. So it seeds only when
MECHFRAME_ALLOW_SEED=1 is set for the run, and cleared after it, in
PowerShell `$env:MECHFRAME_ALLOW_SEED = "1"; try { mechframe seed } finally { Remove-Item Env:MECHFRAME_ALLOW_SEED }`. Its output and exit code are the command's: what it
seeded, or why it refused.
"""

from __future__ import annotations

from pathlib import Path

from mechframe import owner
from mechframe.source import ROOT


def seed(site: Path, *, root: Path = ROOT) -> int:
    """Run the site's `app.seed`; its exit code. Raises owner.Refused when it can't."""
    return owner.run_in_site(site, "app.seed", [], root=root)
