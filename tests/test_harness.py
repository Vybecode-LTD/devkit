"""The harness finds the modules in the repo by their fixed layout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from harness import migrations, registry


def _module(root: Path, module_id: str, files: dict[str, str]) -> Path:
    folder = root / "modules" / module_id
    package = folder / "backend" / module_id.replace("-", "_")
    package.mkdir(parents=True)
    manifest = {
        "id": module_id,
        "name": module_id.title(),
        "version": "0.1.0",
        "requires": {"kernel": "^0.1", "modules": {}},
    }
    (folder / "module.json").write_text(json.dumps(manifest), "utf-8")
    for name, body in files.items():
        (package / name).write_text(body, "utf-8")
    return folder


def test_discover(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    full = _module(
        tmp_path,
        "test-gallery",
        {
            "__init__.py": 'CSP = [("frame-src", "https://player.test")]\n',
            "router.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
            "schemas.py": "from pydantic import BaseModel\nclass Settings(BaseModel):\n    size: int = 3\n",
        },
    )
    bare = tmp_path / "modules" / "test-bare"
    bare.mkdir(parents=True)
    (bare / "module.json").write_text(
        json.dumps({"id": "test-bare", "name": "Bare", "version": "0.1.0", "requires": {}}), "utf-8"
    )
    monkeypatch.setattr(registry, "module_dirs", lambda: [bare, full])
    monkeypatch.syspath_prepend(str(full / "backend"))
    try:
        found = {module.id: module for module in registry.discover()}
    finally:
        for name in [n for n in sys.modules if n.startswith("test_gallery")]:
            del sys.modules[name]
    assert found["test-bare"].router is None
    gallery = found["test-gallery"]
    assert gallery.router is not None
    assert gallery.settings is not None
    assert gallery.settings().model_dump() == {"size": 3}
    assert gallery.csp == (("frame-src", "https://player.test"),)


def test_the_migrations_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert migrations.main([]) == 2
    assert "usage:" in capsys.readouterr().out
    assert migrations.main(["heads"]) == 0
    out = capsys.readouterr().out
    assert "Rev: kernel_" in out
    assert "(head)" in out
