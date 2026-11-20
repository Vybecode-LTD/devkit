"""`mechframe new <dir> [--recipe <id>]`: a site, with the kernel and a recipe's
modules (K5 contract §2, and §4 items 2 and 4).

In one go, or not at all:

1. Refuses a folder that isn't empty, an unknown theme, a name that can't
   be a site's, and a recipe that can't make one from this checkout (one
   that doesn't validate, a module not built, a requirement it lacks, two
   that conflict), before writing anything.
2. Copies `templates/site/` (its build output left behind: `node_modules`,
   `dist`, caches, a `.venv`), then this checkout's pinned requirements.
3. Writes the site's name and theme in: `__SITE_NAME__` in every text file
   (quoted for dotenv in `.env.example`, escaped inside a TypeScript or JSON
   string), `__THEME__` in `web/index.html`, and
   the theme's `tokens.css` as `web/src/theme/tokens.css`.
4. Copies the kernel (`mechframe.layout`) and writes `mechframe.lock.json`.
5. With a recipe, runs `add` for each of its modules, each after those it
   requires (`mechframe.modules`). The theme is the recipe's unless one is
   given, and the recipe's settings are printed for Admin, Settings.

A run holds its folder from its first write (a folder it makes, or a claim
file in an empty one), so two runs never write to one site. A failure
half-way removes what it wrote: a folder it made goes, and an
empty folder it was given is emptied again, a recipe's modules too.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from mechframe import __version__, layout, lock, modules
from mechframe.source import ROOT, kernel_manifest, schema_problems

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
class Recipe:
    id: str
    theme: str
    settings: dict[str, Any]
    #: its modules, each after every module it requires
    modules: list[str]


@dataclass(frozen=True)
class Made:
    site: Path
    name: str
    theme: str
    lock: dict[str, Any]
    recipe: Recipe | None = None
    added: tuple[modules.Added, ...] = ()


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


def recipes(root: Path = ROOT) -> list[str]:
    folder = root / "recipes"
    return sorted(path.stem for path in folder.glob("*.json")) if folder.is_dir() else []


def load_recipe(recipe_id: str, root: Path = ROOT) -> Recipe:
    """The checkout's recipe, its modules in the order `add` needs them. Raises
    Refused on one that can't make a site from this checkout."""
    path = root / "recipes" / f"{recipe_id}.json"
    if recipe_id not in recipes(root):
        raise Refused(
            f"There's no recipe {recipe_id}. The recipes: {', '.join(recipes(root)) or 'none'}."
        )
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as error:
        raise Refused(f"recipes/{recipe_id}.json can't be read as JSON ({error}).") from None
    problems = schema_problems("recipe", data, root)
    if problems:
        raise Refused(f"recipes/{recipe_id}.json doesn't validate: " + "; ".join(problems))
    wanted: list[str] = list(data["modules"])
    have = set(modules.built(root))
    missing = [each for each in wanted if each not in have]
    if missing:
        raise Refused(
            f"{recipe_id} needs modules this checkout hasn't built: {', '.join(missing)}."
        )
    try:
        manifests = {each: modules.checked_manifest(each, root) for each in wanted}
    except modules.Refused as refusal:
        raise Refused(str(refusal)) from None
    for each in wanted:
        for other in manifests[each]["conflicts"]:
            if other in manifests:
                raise Refused(f"{each} and {other} can't be in one site: they conflict.")
        for other in manifests[each]["requires"].get("modules", {}):
            if other not in manifests:
                raise Refused(f"{each} needs {other}, which {recipe_id} doesn't have.")
    ordered: list[str] = []

    def visit(module_id: str, path: tuple[str, ...]) -> None:
        if module_id in ordered:
            return
        if module_id in path:
            loop = " -> ".join([*path, module_id])
            raise Refused(f"{recipe_id}'s modules require each other in a loop: {loop}.")
        for other in sorted(manifests[module_id]["requires"].get("modules", {})):
            visit(other, (*path, module_id))
        ordered.append(module_id)

    for each in wanted:
        visit(each, ())
    return Recipe(recipe_id, data["theme"], dict(data["settings"]), ordered)


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
    try:
        alone = [path.name for path in site.iterdir()] == [CLAIM]
    except BaseException:
        # Only what this call made goes: its claim, and the folder if it made it,
        # so a retry isn't refused (CodeRabbit on #92).
        claim.unlink(missing_ok=True)
        if made_folder:
            site.rmdir()
        raise
    if not alone:
        claim.unlink()
        raise Refused(taken)
    return claim


def new(
    site: Path,
    *,
    name: str,
    theme: str | None = None,
    recipe: str | None = None,
    root: Path = ROOT,
) -> Made:
    """Make the site in `site`. Raises Refused before writing anything."""
    name = checked_name(name)
    chosen = load_recipe(recipe, root) if recipe is not None else None
    theme = theme or (chosen.theme if chosen else DEFAULT_THEME)
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
            "recipe": chosen.id if chosen else None,
            "theme": theme,
        }
        lock.write(site, data, root=root)
        added = tuple(
            modules.add(site, each, root=root) for each in (chosen.modules if chosen else [])
        )
        claim.unlink()
    except BaseException:
        _undo(site, made_folder)
        raise
    return Made(site, name, theme, lock.read(site, root), chosen, added)


def next_steps(made: Made) -> list[str]:
    """What to run next, in the site's folder (its README.md has the rest)."""
    found = [
        f"Made {made.name} in {made.site}, with the kernel {made.lock['kernel']['version']} "
        f"and the theme {made.theme}."
    ]
    if made.recipe is not None:
        versions = ", ".join(f"{each.id} {each.version}" for each in made.added)
        found.append(f"The recipe {made.recipe.id} added its modules, with {versions}.")
        needed = [setting for each in made.added for setting in each.settings]
        if needed:
            found += ["", "Their settings, to set in .env and in Railway's variables:"]
            found += [modules.setting_line(setting) for setting in needed]
        if made.recipe.settings:
            found += ["", "The recipe's settings, for Admin, Settings once the site runs:"]
            found += [f"  {key}: {value}" for key, value in sorted(made.recipe.settings.items())]
    return [
        *found,
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
