"""The MechFrame checkout this CLI copies from and checks against.

It is always the checkout the CLI's own code sits in (`ROOT`): the CLI never
fetches anything (K5 contract §2). Every function takes the checkout as
`root`, so the CLI's tests can hand it a small one of their own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def package(module_id: str) -> str:
    """A module's Python package: its id with `-` turned into `_` (SPEC.md section 5)."""
    return module_id.replace("-", "_")


def kernel_manifest(root: Path = ROOT) -> dict[str, Any]:
    data: dict[str, Any] = load_json(root / "kernel" / "kernel.json")
    return data


def module_dirs(root: Path = ROOT) -> list[Path]:
    """Every module folder, in id order. Folders starting with `_` are scaffolds
    and the template, not modules (`harness.layout.module_dirs` agrees)."""
    modules = root / "modules"
    if not modules.is_dir():
        return []
    return sorted(
        path
        for path in modules.iterdir()
        if path.is_dir()
        and not path.name.startswith(("_", "."))
        and (path / "module.json").is_file()
    )


def module_manifest(module_id: str, root: Path = ROOT) -> dict[str, Any] | None:
    path = root / "modules" / module_id / "module.json"
    if not path.is_file():
        return None
    data: dict[str, Any] = load_json(path)
    return data


def validator(name: str, root: Path = ROOT) -> Draft202012Validator:
    """The validator for `schema/<name>.schema.json` in the checkout."""
    schema = load_json(root / "schema" / f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_problems(name: str, data: Any, root: Path = ROOT) -> list[str]:
    """Each way `data` fails `schema/<name>.schema.json`, as `where: message`."""
    found = []
    for error in sorted(validator(name, root).iter_errors(data), key=lambda each: list(each.path)):
        where = "/".join(str(part) for part in error.absolute_path) or "(top)"
        found.append(f"{where}: {error.message}")
    return found
