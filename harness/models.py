"""Imports every model in the repo, so `Base.metadata` holds every table.

Alembic's autogenerate and the model checks compare the database against
this. A module's models live in `backend/<id_>/models.py` (SPEC.md section 4).
"""

from __future__ import annotations

import importlib
import importlib.util
import json

from harness.layout import module_dirs


def package_name(module_id: str) -> str:
    """A module id as its Python package: hyphens become underscores."""
    return module_id.replace("-", "_")


def load_all() -> list[str]:
    """Import the kernel's models and every module's. Returns what was imported."""
    loaded = []
    for name in ["kernel.models"] + [
        f"{package_name(json.loads((path / 'module.json').read_text('utf-8'))['id'])}.models"
        for path in module_dirs()
    ]:
        if importlib.util.find_spec(name.rsplit(".", 1)[0]) is None:
            continue
        if importlib.util.find_spec(name) is None:
            continue
        importlib.import_module(name)
        loaded.append(name)
    return loaded
