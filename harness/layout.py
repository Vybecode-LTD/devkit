"""Where things are in the DevKit repo, for the harness, the tools and tests.

A site keeps the same names under `backend/` (SPEC.md section 4); the CLI's
site template (K5) gets its own copy of this file.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KERNEL = ROOT / "kernel"
MODULES = ROOT / "modules"
SCHEMA = ROOT / "schema"
RECIPES = ROOT / "recipes"


def module_dirs() -> list[Path]:
    """Every module folder, in id order. Folders starting with `_` are not
    modules (`_template` is the starting point for one)."""
    if not MODULES.is_dir():
        return []
    return sorted(
        path
        for path in MODULES.iterdir()
        if path.is_dir()
        and not path.name.startswith(("_", "."))
        and (path / "module.json").is_file()
    )


def migration_dirs() -> list[Path]:
    """The kernel's migrations, then each module's that has any."""
    found = [KERNEL / "migrations"]
    found += [path / "migrations" for path in module_dirs() if (path / "migrations").is_dir()]
    return found


def backend_dirs() -> list[Path]:
    """The folders that go on sys.path: the kernel's backend, then each module's."""
    return [KERNEL / "backend"] + [
        path / "backend" for path in module_dirs() if (path / "backend").is_dir()
    ]
