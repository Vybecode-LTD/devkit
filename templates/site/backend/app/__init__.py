"""This site's backend (MechFrame's site template, SPEC.md section 4).

Importing `app` puts `backend/modules` on `sys.path`, so each copied module's
package (`backend/modules/<id_>/`) imports by its own name, as the kernel
(`backend/kernel/`) does from `backend/`. Every command runs with `backend`
on the path: `PYTHONPATH=backend` locally (README.md), `/app/backend` in the
Dockerfile, `pythonpath` in pyproject.toml for the tests.

`installed(MODULE_IDS)` builds the modules `app/modules.py` lists, each from
its manifest with `kernel.load_module`, as MechFrame's own harness does.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

BACKEND = Path(__file__).resolve().parent.parent
MODULES = BACKEND / "modules"

if str(MODULES) not in sys.path:
    sys.path.insert(0, str(MODULES))

if TYPE_CHECKING:
    from kernel import InstalledModule


def package(module_id: str) -> str:
    """A module's Python package: its id with `-` turned into `_`."""
    return module_id.replace("-", "_")


def installed(module_ids: Iterable[str]) -> list[InstalledModule]:
    """The modules `module_ids` names, built from their copied manifests."""
    from kernel import load_module

    return [load_module(MODULES / package(each) / "module.json") for each in module_ids]
