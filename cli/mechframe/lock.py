"""A site's `mechframe.lock.json` (SPEC.md section 13; `schema/lock.schema.json`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mechframe.source import ROOT, schema_problems

NAME = "mechframe.lock.json"


class LockError(Exception):
    """The lock is missing, isn't JSON, or doesn't validate."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def problems(data: Any, root: Path = ROOT) -> list[str]:
    return [f"{NAME}: {problem}" for problem in schema_problems("lock", data, root)]


def read(site: Path, root: Path = ROOT) -> dict[str, Any]:
    path = site / NAME
    try:
        data = json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        raise LockError([f"{NAME}: there's none in {site}; is this a MechFrame site?"]) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LockError([f"{NAME}: can't be read as JSON ({error})"]) from None
    found = problems(data, root)
    if found:
        raise LockError(found)
    checked: dict[str, Any] = data
    return checked


def text(data: dict[str, Any], root: Path = ROOT) -> str:
    """The lock as written: its files in path order, its modules in id order.
    Raises LockError on one that doesn't validate."""
    found = problems(data, root)
    if found:
        raise LockError(found)
    ordered = dict(data)
    ordered["kernel"] = {**data["kernel"], "files": dict(sorted(data["kernel"]["files"].items()))}
    ordered["modules"] = {
        module_id: {**entry, "files": dict(sorted(entry["files"].items()))}
        for module_id, entry in sorted(data["modules"].items())
    }
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def write(site: Path, data: dict[str, Any], root: Path = ROOT) -> None:
    """Write the lock, refusing one that doesn't validate."""
    written = text(data, root)
    site.mkdir(parents=True, exist_ok=True)
    (site / NAME).write_text(written, encoding="utf-8", newline="\n")
