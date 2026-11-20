"""`mechframe catalog`: catalog.json from every built module's manifest (SPEC 17)."""

from __future__ import annotations

import json
from pathlib import Path

from mechframe import catalog, source
from mechframe.__main__ import main

from .conftest import add_module


def test_the_catalog_holds_built_modules_only_with_what_picking_needs(checkout: Path) -> None:
    add_module(checkout, "a-first")
    data = catalog.build(checkout)
    assert [entry["id"] for entry in data["modules"]] == ["a-first", "demo-shop"]
    entry = data["modules"][1]
    assert list(entry) == list(catalog.FIELDS)
    assert entry["use_when"] == ["A site that needs demo-shop", "A second concrete sentence"]
    assert entry["requires"] == {"kernel": "^0.1", "modules": {}}
    assert data["spec"] == source.kernel_manifest(checkout)["spec"]
    assert data["generated_at"] is None


def test_catalog_writes_the_file_and_check_finds_it_current(checkout: Path) -> None:
    assert main(["catalog", "--root", str(checkout)]) == 0
    written = json.loads((checkout / "catalog.json").read_text("utf-8"))
    assert [entry["id"] for entry in written["modules"]] == ["demo-shop"]
    assert main(["catalog", "--check", "--root", str(checkout)]) == 0


def test_check_finds_a_stale_catalog_and_leaves_it_alone(checkout: Path) -> None:
    assert main(["catalog", "--root", str(checkout)]) == 0
    add_module(checkout, "new-one")
    before = (checkout / "catalog.json").read_bytes()
    assert main(["catalog", "--check", "--root", str(checkout)]) == 1
    assert (checkout / "catalog.json").read_bytes() == before


def test_the_repo_s_catalog_is_current() -> None:
    assert main(["catalog", "--check"]) == 0
