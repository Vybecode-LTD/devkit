"""The modules in this repo, as the harness's app is built from them.

A site lists its modules in `backend/app/modules.py`, written by
`devkit add` (SPEC.md section 12). The harness finds them instead, by the
fixed layout (SPEC.md section 4):

- `backend/<id_>/router.py`'s `router`, mounted at /api/<id>;
- `backend/<id_>/schemas.py`'s `Settings`, the module's settings model;
- `backend/<id_>/__init__.py`'s `CSP`, the hosts it adds while it's on, as
  (directive, https origin) pairs.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any

import harness  # noqa: F401  (puts the kernel and modules on sys.path)
from harness.layout import module_dirs
from kernel.modules import InstalledModule, Manifest


def _attribute(module_name: str, attribute: str) -> Any:
    if importlib.util.find_spec(module_name) is None:
        return None
    return getattr(importlib.import_module(module_name), attribute, None)


def discover() -> list[InstalledModule]:
    found = []
    for folder in module_dirs():
        manifest = Manifest.from_file(folder / "module.json")
        package = manifest.package
        if importlib.util.find_spec(package) is None:
            found.append(InstalledModule(manifest))
            continue
        found.append(
            InstalledModule(
                manifest,
                router=_attribute(f"{package}.router", "router"),
                settings=_attribute(f"{package}.schemas", "Settings"),
                csp=tuple(_attribute(package, "CSP") or ()),
            )
        )
    return found
