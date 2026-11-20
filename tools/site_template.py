"""Keep the site template's web package on MechFrame's versions (K5 contract §4 item 2).

    python -m tools.site_template           write templates/site/web/package.json and its lockfile
    python -m tools.site_template --check   exit 1 if either is behind the root's

The template's `web/package.json` holds the root's dependencies, dev
dependencies, overrides and engines exactly, since the copied kernel is
built and tested with them. Its `package-lock.json` is made by npm from the
root's lockfile (so every version npm can keep, it keeps), in a folder of its
own, with no install scripts and nothing installed: `--package-lock-only`.
Writing it needs npm and the registry; `--check` needs neither, and compares
the package and each direct dependency's locked version with the root's.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "templates" / "site" / "web"
SHARED = ("engines", "dependencies", "devDependencies", "overrides")
NOTE = (
    "dependencies, devDependencies, overrides and engines are MechFrame's own, at its exact "
    "versions: the copied kernel is built and tested with them. `python -m tools.site_template` "
    "writes them in MechFrame; a site changes them only with MechFrame's."
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def package(root: Path = ROOT) -> dict[str, Any]:
    """The template's package.json, from the root's."""
    found: dict[str, Any] = _json(root / "package.json")
    return {
        "name": "site-web",
        "private": True,
        "version": "0.0.0",
        "description": (
            "This site's web app: MechFrame's kernel, its modules' bindings and the site's own pages."
        ),
        "type": "module",
        "engines": found["engines"],
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
            "test": "vitest run",
            "lint": "eslint . --max-warnings=0",
            "typecheck": "tsc -p tsconfig.json",
            "e2e": "playwright test",
        },
        "dependencies": found["dependencies"],
        "devDependencies": found["devDependencies"],
        "overrides": found["overrides"],
        "//": [NOTE, *found.get("//", [])],
    }


def _text(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def problems(root: Path = ROOT, web: Path = WEB) -> list[str]:
    """What's behind the root's: the package, or a direct dependency's locked version."""
    found: list[str] = []
    try:
        if _json(web / "package.json") != package(root):
            found.append("templates/site/web/package.json is behind the root's package.json.")
        locked = _json(web / "package-lock.json")["packages"]
    except (OSError, ValueError, KeyError) as error:
        return [*found, f"templates/site/web can't be read ({type(error).__name__})."]
    ours = _json(root / "package-lock.json")["packages"]
    wanted = package(root)
    top = locked.get("", {})
    for group in ("dependencies", "devDependencies"):
        if top.get(group) != wanted[group]:
            found.append(f"templates/site/web/package-lock.json's {group} aren't the package's.")
        for name in wanted[group]:
            key = f"node_modules/{name}"
            have = locked.get(key, {}).get("version")
            if have != ours.get(key, {}).get("version"):
                found.append(f"{name} is locked at {have} in the template, not the root's version.")
    return found


def write(root: Path = ROOT, web: Path = WEB, npm: str | None = None) -> None:
    """Write the template's package.json, and its lockfile with npm."""
    text = _text(package(root))
    (web / "package.json").write_text(text, encoding="utf-8", newline="\n")
    npm = npm or shutil.which("npm") or "npm"
    with tempfile.TemporaryDirectory() as scratch:
        folder = Path(scratch)
        (folder / "package.json").write_text(text, encoding="utf-8", newline="\n")
        # The root's lockfile without its workspaces: the template has none.
        seed = _json(root / "package-lock.json")
        seed["packages"] = {
            key: value
            for key, value in seed["packages"].items()
            if key == "" or (key.startswith("node_modules/") and not value.get("link"))
        }
        (folder / "package-lock.json").write_text(_text(seed), encoding="utf-8", newline="\n")
        shutil.copyfile(web / ".npmrc", folder / ".npmrc")
        subprocess.run(  # noqa: S603 (npm, on a package this tool just wrote)
            [npm, "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=folder,
            check=True,
        )
        made = _json(folder / "package-lock.json")
    made["name"] = "site-web"
    made["packages"][""]["name"] = "site-web"
    (web / "package-lock.json").write_text(_text(made), encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    if argv not in ([], ["--check"]):
        print("usage: python -m tools.site_template [--check]")
        return 2
    if not argv:
        write()
    found = problems()
    for problem in found:
        print(problem)
    if found:
        print("Run `python -m tools.site_template` to write them again.")
        return 1
    print("The site template's web package is MechFrame's.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
