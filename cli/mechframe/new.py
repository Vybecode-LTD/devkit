"""`mechframe new <dir>`: a kernel-only site (K5 contract §2 and §4 item 2).

In one go, or not at all:

1. Refuses a folder that isn't empty, an unknown theme and a name that
   can't be a site's, before writing anything.
2. Copies `templates/site/` (its build output left behind: `node_modules`,
   `dist`, caches, a `.venv`), then this checkout's pinned requirements.
3. Writes the site's name and theme in: `__SITE_NAME__` in every text file
   (quoted for dotenv in `.env.example`, escaped inside a TypeScript or JSON
   string), `__THEME__` in `web/index.html`, and
   the theme's `tokens.css` as `web/src/theme/tokens.css`.
4. Copies the kernel (`mechframe.layout`) and writes `mechframe.lock.json`.

A run holds its folder from its first write (a folder it makes, or a claim
file in an empty one), so two runs never write to one site. A failure
half-way removes what it wrote: a folder it made goes, and an
empty folder it was given is emptied again. `--recipe` joins with `add` (#93).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from mechframe import __version__, layout, lock
from mechframe.source import ROOT, kernel_manifest

TEMPLATE = "templates/site"
#: This checkout's pins, which a site installs as they are (`--require-hashes`).
REQUIREMENTS = (
    "requirements.in",
    "requirements.txt",
    "requirements-dev.in",
    "requirements-dev.txt",
)
DEFAULT_THEME = "machined-light"
NAME_MARK = "__SITE_NAME__"
THEME_MARK = "__THEME__"
MAX_NAME = 100
#: The file a run holds an empty folder by while it writes the site there.
CLAIM = ".mechframe-new"
#: What a copy of the template leaves behind wherever it is: build output and caches.
LEFT_OUT = frozenset(
    {
        "node_modules",
        "dist",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "test-results",
        "playwright-report",
        "coverage",
    }
)


class Refused(Exception):
    """`new` won't make this site; the message says why."""


@dataclass(frozen=True)
class Made:
    site: Path
    name: str
    theme: str
    lock: dict[str, Any]


def themes(root: Path = ROOT) -> list[str]:
    """Every theme in the checkout: a folder of `themes/` with its `tokens.css`."""
    folder = root / "themes"
    if not folder.is_dir():
        return []
    return sorted(path.name for path in folder.iterdir() if (path / "tokens.css").is_file())


def checked_name(name: str) -> str:
    """The site's name, trimmed: one line of at most 100 characters."""
    trimmed = name.strip()
    if not trimmed or len(trimmed) > MAX_NAME or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise Refused(
            f"{name!r} can't be the site's name: one line of 1 to {MAX_NAME} characters, "
            "with no tabs or other control characters."
        )
    return trimmed


def env_value(text: str) -> str:
    """`text` as a double-quoted dotenv value: a backslash and a quote escaped."""
    escaped = text.replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"')
    return f'"{escaped}"'


def template_files(root: Path = ROOT) -> list[tuple[Path, str]]:
    """Every file of the template, with its path in the site."""
    template = root / TEMPLATE
    found: list[tuple[Path, str]] = []
    for path in sorted(template.rglob("*")):
        relative = PurePosixPath(path.relative_to(template).as_posix())
        if path.is_file() and not any(part in LEFT_OUT for part in relative.parts[:-1]):
            found.append((path, str(relative)))
    return found


def _refusals(site: Path, theme: str, root: Path) -> None:
    if site.exists() and not site.is_dir():
        raise Refused(f"{site} is a file: give a folder that's empty or not there yet.")
    if site.is_dir() and any(site.iterdir()):
        raise Refused(f"{site} isn't empty: give a folder that's empty or not there yet.")
    known = themes(root)
    if theme not in known:
        raise Refused(f"There's no theme {theme}. The themes: {', '.join(known) or 'none'}.")
    if not (root / TEMPLATE).is_dir():
        raise Refused(f"This checkout has no {TEMPLATE}/.")


def _write_in(path: Path, relative: str, name: str, theme: str) -> None:
    """The site's name and theme in place of the template's marks."""
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return  # a picture or a font: no marks
    if NAME_MARK not in text and THEME_MARK not in text:
        return
    if relative == ".env.example":
        shown = env_value(name)
    elif relative.endswith((".ts", ".tsx", ".js", ".json")):
        shown = json.dumps(name, ensure_ascii=False)[1:-1]  # inside a "..." string
    else:
        shown = name
    path.write_bytes(text.replace(NAME_MARK, shown).replace(THEME_MARK, theme).encode("utf-8"))


def _copy_template(site: Path, name: str, theme: str, root: Path) -> None:
    for source, relative in template_files(root):
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        _write_in(target, relative, name, theme)
    for requirement in REQUIREMENTS:
        shutil.copyfile(root / requirement, site / requirement)
    tokens = site / "web" / "src" / "theme" / "tokens.css"
    tokens.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "themes" / theme / "tokens.css", tokens)


def _undo(site: Path, made_folder: bool) -> None:
    if made_folder:
        shutil.rmtree(site, ignore_errors=True)
        return
    for path in site.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _claim(site: Path, made_folder: bool) -> Path:
    """This run's hold on `site`, taken atomically: the folder made here, or the
    claim file made in an empty one, so two runs never write to one site or undo
    each other's (CodeRabbit on #92). Raises Refused when another run has it."""
    taken = f"{site} was taken by another run of mechframe new meanwhile: give a folder of its own."
    try:
        site.mkdir(parents=True, exist_ok=not made_folder)
        claim = site / CLAIM
        claim.open("x").close()
    except FileExistsError:
        raise Refused(taken) from None
    if [path.name for path in site.iterdir()] != [CLAIM]:
        claim.unlink()
        raise Refused(taken)
    return claim


def new(site: Path, *, name: str, theme: str = DEFAULT_THEME, root: Path = ROOT) -> Made:
    """Make the site in `site`. Raises Refused before writing anything."""
    name = checked_name(name)
    _refusals(site, theme, root)
    made_folder = not site.exists()
    claim = _claim(site, made_folder)
    try:
        _copy_template(site, name, theme, root)
        manifest = kernel_manifest(root)
        files = layout.copy(root, site, layout.kernel_copies())
        data: dict[str, Any] = {
            "mechframe": __version__,
            "spec": manifest["spec"],
            "kernel": {"version": manifest["version"], "files": files},
            "modules": {},
            "recipe": None,
            "theme": theme,
        }
        lock.write(site, data, root=root)
        claim.unlink()
    except BaseException:
        _undo(site, made_folder)
        raise
    return Made(site, name, theme, data)


def next_steps(made: Made) -> list[str]:
    """What to run next, in the site's folder (its README.md has the rest)."""
    return [
        f"Made {made.name} in {made.site}, with the kernel {made.lock['kernel']['version']} "
        f"and the theme {made.theme}.",
        "",
        "Next, in that folder (README.md has the rest):",
        "  py -3.12 -m venv .venv",
        "  .venv/Scripts/python.exe -m pip install --require-hashes "
        "-r requirements.txt -r requirements-dev.txt",
        "  copy .env.example to .env, and fill in DATABASE_URL, SECRET_KEY and ENCRYPTION_KEYS",
        '  $env:PYTHONPATH = "backend"',
        "  .venv/Scripts/python.exe -m app.migrations upgrade",
        "  cd web; npm ci; npm run build; cd ..",
        "  .venv/Scripts/python.exe -m pytest backend/tests",
        f"  and from MechFrame's checkout: python -m mechframe check --site {made.site}",
    ]
