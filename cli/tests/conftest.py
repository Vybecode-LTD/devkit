"""A small MechFrame checkout and a site copied from it, for the CLI's tests.

The checkout holds the real schemas and kernel manifest, a few kernel files,
one built module (`demo-shop`), a scaffold (`_later`) and a planned module
(`planned-thing`), so a test can change any of them without touching the repo.
`maker` adds a small site template, two themes and the pins, for `new`;
`site_maker` adds the template's real registries and settings files and the
fixture modules and recipe (`fixtures/README.md`), for `add` and `remove`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from mechframe import layout, lock, source

REPO = source.ROOT
FIXTURES = Path(__file__).parent / "fixtures"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def manifest(module_id: str, **changes: Any) -> dict[str, Any]:
    """The template's manifest, renamed to `module_id` and its names prefixed to match."""
    data = json.loads((REPO / "modules" / "_template" / "module.json").read_text("utf-8"))
    package = module_id.replace("-", "_")
    data["id"] = module_id
    data["name"] = module_id.replace("-", " ").capitalize()
    data["summary"] = f"The {module_id} module, for tests."
    data["use_when"] = [f"A site that needs {module_id}", "A second concrete sentence"]
    data["avoid_when"] = ["A site that sells nothing: use pages instead"]
    data["permissions"] = [
        {
            "key": f"{module_id}.item.manage",
            "description": "Manage items",
            "default_roles": ["admin"],
        }
    ]
    data["notifications"] = []
    data["tables"] = [f"{package}_item"]
    data["routes"] = {"api": f"/api/{module_id}", "public": [], "member": [], "admin": []}
    data["slots"] = []
    data["source"] = {"from": "new", "commit": "none", "license": "proprietary"}
    data.update(changes)
    return data


def add_module(root: Path, module_id: str, **changes: Any) -> Path:
    folder = root / "modules" / module_id
    package = module_id.replace("-", "_")
    write(folder / "module.json", json.dumps(manifest(module_id, **changes), indent=2) + "\n")
    write(folder / "MODULE.md", f"# {module_id}\n")
    write(folder / "CHANGELOG.md", "# Changelog\n")
    write(folder / "backend" / package / "__init__.py", '"""A module for tests."""\n')
    write(folder / "backend" / package / "router.py", "router = None\n")
    write(folder / "migrations" / f"0001_{package}.py", "revision = '0001'\n")
    write(folder / "web" / "module.web.ts", "export default {};\n")
    write(folder / "web" / "module.web.test.ts", "// left out of a site\n")
    write(folder / "tests" / "backend" / "test_it.py", "# left out of a site\n")
    return folder


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A MechFrame checkout: real schemas and kernel manifest, made-up code."""
    root = tmp_path / "mechframe"
    shutil.copytree(REPO / "schema", root / "schema")
    write(root / "kernel" / "kernel.json", (REPO / "kernel" / "kernel.json").read_text("utf-8"))
    write(root / "kernel" / "backend" / "kernel" / "__init__.py", '"""The kernel."""\n')
    write(root / "kernel" / "backend" / "kernel" / "auth" / "sessions.py", "SESSIONS = 1\n")
    write(root / "kernel" / "backend" / "kernel" / "__pycache__" / "x.cpython-312.pyc", "junk")
    write(root / "kernel" / "migrations" / "kernel_0001.py", "revision = 'kernel_0001'\n")
    write(root / "kernel" / "web" / "index.ts", "export {};\n")
    write(root / "kernel" / "web" / "package.json", "{}\n")
    write(root / "kernel" / "web" / "src" / "app" / "mount.ts", "export const mount = 1;\n")
    write(root / "kernel" / "web" / "src" / "app" / "mount.test.tsx", "// left out of a site\n")
    write(root / "kernel" / "tests" / "test_kernel.py", "# left out of a site\n")
    add_module(root, "demo-shop")
    add_module(root, "planned-thing", status="planned")
    write(root / "modules" / "_later" / "module.json", json.dumps(manifest("later")) + "\n")
    write(root / "advisories.json", json.dumps({"advisories": []}, indent=2) + "\n")
    write(root / "catalog.json", "{}\n")
    return root


@pytest.fixture
def site(tmp_path: Path, checkout: Path) -> Path:
    """A site holding the checkout's kernel and `demo-shop`, with its lock."""
    folder = tmp_path / "site"
    kernel_files = layout.copy(checkout, folder, layout.kernel_copies())
    shop_files = layout.copy(checkout, folder, layout.module_copies("demo-shop"))
    data = {
        "mechframe": "0.1.0",
        "spec": "0.1",
        "kernel": {"version": source.kernel_manifest(checkout)["version"], "files": kernel_files},
        "modules": {"demo-shop": {"version": "0.1.0", "added": "2026-11-20", "files": shop_files}},
        "recipe": None,
        "theme": "machined-light",
    }
    lock.write(folder, data, root=checkout)
    return folder


def advisory(**fields: Any) -> dict[str, Any]:
    entry = {
        "id": "MF-2026-0001",
        "module": "kernel",
        "introduced": "0.0.1",
        "fixed": None,
        "severity": "high",
        "summary": "Something the kernel got wrong",
    }
    entry.update(fields)
    return entry


def set_advisories(root: Path, *entries: dict[str, Any]) -> None:
    write(root / "advisories.json", json.dumps({"advisories": list(entries)}, indent=2) + "\n")


REQUIREMENTS = (
    "requirements.in",
    "requirements.txt",
    "requirements-dev.in",
    "requirements-dev.txt",
)


@pytest.fixture
def maker(checkout: Path) -> Path:
    """The checkout with a small site template, two themes and its pins."""
    template = checkout / "templates" / "site"
    write(template / "README.md", "# __SITE_NAME__\n\nMade with MechFrame.\n")
    write(template / "CLAUDE.md", "# CLAUDE.md: __SITE_NAME__\n")
    write(
        template / ".env.example",
        "DEBUG=false\nSITE_NAME=__SITE_NAME__\nCLIENT_IP_HEADER=X-Real-IP\n",
    )
    write(template / "backend" / "app" / "main.py", "app = None\n")
    write(template / "backend" / "app" / "__pycache__" / "main.cpython-312.pyc", "junk")
    write(template / "web" / "index.html", '<html data-theme="__THEME__"></html>\n')
    write(template / ".railway" / "railway.ts", 'const name = "__SITE_NAME__";\n')
    write(template / "web" / "node_modules" / "react" / "index.js", "junk\n")
    write(template / "web" / "dist" / "index.html", "junk\n")
    write(template / ".venv" / "pyvenv.cfg", "junk\n")
    (template / "web" / "logo.png").parent.mkdir(parents=True, exist_ok=True)
    (template / "web" / "logo.png").write_bytes(bytes([137, 80, 78, 71, 0, 255, 254]))
    for theme in ("machined-light", "vibrant-mindz"):
        write(checkout / "themes" / theme / "tokens.css", f'[data-theme="{theme}"] {{}}\n')
        write(checkout / "themes" / theme / "tokens.json", "{}\n")
    for name in REQUIREMENTS:
        write(checkout / name, f"# {name}, pinned\n")
    return checkout


#: The template's files `add` and `remove` write, as `mechframe new` copies them.
SITE_FILES = ("backend/app/modules.py", "web/src/modules.ts", ".env.example", ".railway/railway.ts")


def with_fixtures(root: Path) -> Path:
    """The fixture modules and recipe in the checkout `root`."""
    for folder in (FIXTURES / "modules").iterdir():
        shutil.copytree(folder, root / "modules" / folder.name, dirs_exist_ok=True)
    for recipe in (FIXTURES / "recipes").glob("*.json"):
        write(root / "recipes" / recipe.name, recipe.read_text("utf-8"))
    return root


@pytest.fixture
def site_maker(maker: Path) -> Path:
    """`maker` with the template's real registries and settings files, and the
    fixture modules and recipe."""
    template = maker / "templates" / "site"
    for relative in SITE_FILES:
        target = template / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / "templates" / "site" / relative, target)
    return with_fixtures(maker)


@pytest.fixture
def made(site_maker: Path, tmp_path: Path) -> Path:
    """A kernel-only site from `site_maker`."""
    from mechframe.__main__ import main

    folder = tmp_path / "made"
    assert main(["new", str(folder), "--root", str(site_maker)]) == 0
    return folder


def tree(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, by its path there, with what it holds."""
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }
