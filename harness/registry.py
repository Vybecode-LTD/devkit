"""The modules in this repo, as the harness's app is built from them.

A site lists its modules in `backend/app/modules.py`, written by
`mechframe add` (SPEC.md section 12), and builds each from its manifest with
`kernel.load_module`. The harness finds them instead, by the repo's layout
(`harness.layout.module_dirs`), and builds them the same way, so a module
the harness runs is the module a site runs (K5 contract §2).
"""

from __future__ import annotations

import harness  # noqa: F401  (puts the kernel and modules on sys.path)
from harness.layout import module_dirs
from kernel.modules import InstalledModule, load_module


def discover() -> list[InstalledModule]:
    """Every built module in this repo, in id order."""
    return [load_module(folder / "module.json") for folder in module_dirs()]
