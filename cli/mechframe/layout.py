"""Where the kernel and each module land in a site (K5 contract §2, SPEC.md section 4).

| From the checkout | To the site |
| --- | --- |
| `kernel/backend/kernel/`, `kernel/kernel.json` | `backend/kernel/` |
| `kernel/migrations/` | `backend/migrations/kernel/` |
| `kernel/web/` | `web/src/kernel/` |
| `modules/<id>/backend/<id_>/`, its `module.json`, `MODULE.md`, `CHANGELOG.md` | `backend/modules/<id_>/` |
| `modules/<id>/migrations/` | `backend/migrations/<id>/` |
| `modules/<id>/web/` | `web/src/modules/<id>/` |

Tests, caches and the web folders' own package files stay behind: MechFrame's
CI tests the kernel and its modules, and a site's `web/package.json` is its own.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mechframe.hashes import digest
from mechframe.source import package

#: Folder names a copy leaves out wherever they are.
LEFT_OUT_FOLDERS = frozenset(
    {
        "__pycache__",
        "__tests__",
        "tests",
        "node_modules",
        "dist",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)
#: File endings and names a copy leaves out.
LEFT_OUT_ENDINGS = (".pyc", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
LEFT_OUT_NAMES = frozenset({"package.json", "package-lock.json", "tsconfig.tsbuildinfo"})


@dataclass(frozen=True)
class Copy:
    """One folder or file: `source` in the checkout, `target` in the site, both with `/`."""

    source: str
    target: str
    folder: bool


def left_out(relative: PurePosixPath) -> bool:
    """Whether a file at `relative`, inside a copied folder, stays behind."""
    if any(part in LEFT_OUT_FOLDERS for part in relative.parts[:-1]):
        return True
    return relative.name in LEFT_OUT_NAMES or relative.name.endswith(LEFT_OUT_ENDINGS)


def kernel_copies() -> list[Copy]:
    return [
        Copy("kernel/backend/kernel", "backend/kernel", folder=True),
        Copy("kernel/kernel.json", "backend/kernel/kernel.json", folder=False),
        Copy("kernel/migrations", "backend/migrations/kernel", folder=True),
        Copy("kernel/web", "web/src/kernel", folder=True),
    ]


def module_copies(module_id: str) -> list[Copy]:
    name = package(module_id)
    home = f"modules/{module_id}"
    return [
        Copy(f"{home}/backend/{name}", f"backend/modules/{name}", folder=True),
        Copy(f"{home}/module.json", f"backend/modules/{name}/module.json", folder=False),
        Copy(f"{home}/MODULE.md", f"backend/modules/{name}/MODULE.md", folder=False),
        Copy(f"{home}/CHANGELOG.md", f"backend/modules/{name}/CHANGELOG.md", folder=False),
        Copy(f"{home}/migrations", f"backend/migrations/{module_id}", folder=True),
        Copy(f"{home}/web", f"web/src/modules/{module_id}", folder=True),
    ]


def files(root: Path, copies: list[Copy]) -> list[tuple[Path, str]]:
    """Every file the copies take: its path in the checkout and in the site.
    A source the checkout doesn't have (a module with no web folder) takes nothing."""
    found: list[tuple[Path, str]] = []
    for each in copies:
        source = root / each.source
        if not each.folder:
            if source.is_file():
                found.append((source, each.target))
            continue
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            relative = PurePosixPath(path.relative_to(source).as_posix())
            if path.is_file() and not left_out(relative):
                found.append((path, f"{each.target}/{relative}"))
    return found


def copy(root: Path, site: Path, copies: list[Copy]) -> dict[str, str]:
    """Copy into `site` and answer each copied file's hash, for the lock file."""
    recorded: dict[str, str] = {}
    for source, target in files(root, copies):
        destination = site / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        recorded[target] = digest(destination)
    return dict(sorted(recorded.items()))


def site_files(site: Path, copies: list[Copy]) -> list[str]:
    """Every file now in the site's copied folders that a copy would take."""
    found: list[str] = []
    for each in copies:
        if not each.folder:
            continue
        folder = site / each.target
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            relative = PurePosixPath(path.relative_to(folder).as_posix())
            if path.is_file() and not left_out(relative):
                found.append(f"{each.target}/{relative}")
    return sorted(found)
