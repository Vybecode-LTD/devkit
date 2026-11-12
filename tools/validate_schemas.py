"""Checks every manifest in the repo against `schema/`, plus the rules a JSON
Schema can't say (SPEC.md sections 4, 5 and 10).

    python -m tools.validate_schemas          # exit 1 and a line per problem

What it checks:
- every `modules/*/module.json` (the template included) against
  `module.schema.json`; every `recipes/*.json` against `recipe.schema.json`;
  `kernel/kernel.json` against `kernel.schema.json`; `catalog.json` and
  `advisories.json` parse;
- a module's folder is named by its id (the template excepted), its backend
  package is the id with `-` turned into `_`, every table it owns starts with
  that package name and `_`, and every permission key with its id and `.`;
- every module a recipe names that isn't in `modules/` yet is reported as
  planned, not as a problem, while the modules are being built.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    planned: set[str] = field(default_factory=set)
    checked: int = 0

    def problem(self, path: Path, root: Path, message: str) -> None:
        self.problems.append(f"{path.relative_to(root).as_posix()}: {message}")


def _load(path: Path, root: Path, report: Report) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        report.problem(path, root, f"can't be read as JSON ({error})")
        return None


def _validator(root: Path, name: str) -> Draft202012Validator:
    schema = json.loads((root / "schema" / name).read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _against(
    validator: Draft202012Validator, data: Any, path: Path, root: Path, report: Report
) -> bool:
    report.checked += 1
    errors = list(validator.iter_errors(data))
    if not errors:
        return True
    error = best_match(errors)
    where = "/".join(str(part) for part in error.absolute_path) or "(top)"
    more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
    report.problem(path, root, f"{where}: {error.message}{more}")
    return False


def _module_rules(manifest: dict[str, Any], folder: Path, root: Path, report: Report) -> None:
    module_id: str = manifest["id"]
    package = module_id.replace("-", "_")
    path = folder / "module.json"
    if not folder.name.startswith("_") and folder.name != module_id:
        report.problem(path, root, f"the folder is {folder.name!r} but the id is {module_id!r}")
    backend = folder / "backend"
    if backend.is_dir() and not (backend / package).is_dir():
        report.problem(path, root, f"the backend package should be backend/{package}/")
    for table in manifest["tables"]:
        if not table.startswith(f"{package}_"):
            report.problem(path, root, f"table {table!r} should start with {package}_")
    for permission in manifest["permissions"]:
        if not permission["key"].startswith(f"{module_id}."):
            report.problem(
                path, root, f"permission {permission['key']!r} should start with {module_id}."
            )
    for notice in manifest["notifications"]:
        if not notice["key"].startswith(f"{module_id}."):
            report.problem(
                path, root, f"notification {notice['key']!r} should start with {module_id}."
            )


def check(root: Path = ROOT) -> Report:
    report = Report()
    modules = _validator(root, "module.schema.json")
    recipes = _validator(root, "recipe.schema.json")
    kernel = _validator(root, "kernel.schema.json")
    _validator(root, "lock.schema.json")  # the schema itself must be valid

    known: set[str] = set()
    for path in sorted((root / "modules").glob("*/module.json")):
        manifest = _load(path, root, report)
        if manifest is None or not _against(modules, manifest, path, root, report):
            continue
        _module_rules(manifest, path.parent, root, report)
        if not path.parent.name.startswith("_"):
            known.add(manifest["id"])

    for path in sorted((root / "recipes").glob("*.json")):
        recipe = _load(path, root, report)
        if recipe is None or not _against(recipes, recipe, path, root, report):
            continue
        if recipe["id"] != path.stem:
            report.problem(path, root, f"the file is {path.name!r} but the id is {recipe['id']!r}")
        report.planned |= {name for name in recipe["modules"] if name not in known}

    kernel_path = root / "kernel" / "kernel.json"
    data = _load(kernel_path, root, report)
    if data is not None:
        _against(kernel, data, kernel_path, root, report)

    for name in ("catalog.json", "advisories.json"):
        _load(root / name, root, report)
    return report


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0]).resolve() if argv else ROOT
    report = check(root)
    for line in report.problems:
        print(line)
    if report.planned:
        print(f"planned, not built yet: {', '.join(sorted(report.planned))}")
    verdict = "FAILED" if report.problems else "ok"
    print(f"{report.checked} files checked, {len(report.problems)} problems: {verdict}")
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
