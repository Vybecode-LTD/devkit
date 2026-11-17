"""Each declared event payload as JSON Schema, in `schema/events/` (SPEC.md
section 11, decisions 0004 and 0036).

    python -m tools.event_schemas           # rewrite schema/events/*.schema.json
    python -m tools.event_schemas --check   # exit 1 if one is stale, missing or left over

One file per event and version, `<name>.v<N>.schema.json`, for the kernel's
events (`kernel.events`) and those of every module the harness finds
(`harness.registry`). The files are made, never edited by hand: they keep an
event's contract language-neutral, for a listener in another language or an
outgoing webhook. `tests/test_event_schemas.py` fails when one is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "schema" / "events"
SUFFIX = ".schema.json"


def schemas() -> dict[str, dict[str, Any]]:
    """Every declared payload's schema, by its file name."""
    from harness.registry import discover
    from kernel import events

    models = [
        *events.KERNEL_PAYLOADS,
        *(model for module in discover() for model in module.payloads),
    ]
    made: dict[str, dict[str, Any]] = {}
    for model in models:
        found = events.declaration(model)
        if found is None:  # discovery keeps only declared payloads
            continue
        name, version = found
        file_name = f"{name}.v{version}{SUFFIX}"
        made[file_name] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://devkit.local/schema/events/{file_name}",
            **model.model_json_schema(),
            "title": f"{name} (v{version})",
        }
    return made


def main(argv: list[str] | None = None, *, folder: Path = FOLDER) -> int:
    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    wanted = {
        name: json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        for name, schema in schemas().items()
    }
    wrong: list[str] = []
    for name, text in sorted(wanted.items()):
        path = folder / name
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        if check:
            wrong.append(f"stale or missing: {name}")
        else:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"Wrote schema/events/{name}")
    for path in sorted(folder.glob(f"*{SUFFIX}")):
        if path.name in wanted:
            continue
        if check:
            wrong.append(f"no event declares it: {path.name}")
        else:
            path.unlink()
            print(f"Removed schema/events/{path.name}")
    if wrong:
        print("\n".join(wrong) + "\nRun python -m tools.event_schemas.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
