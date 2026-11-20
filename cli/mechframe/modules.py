"""`mechframe add <id>` and `mechframe remove <id>` (SPEC.md section 12; the
K5 contract §2 and §4 item 4; decision 0050).

`add` runs SPEC 12's steps 1 to 5. It checks the module against the lock (its
`requires` and `conflicts`, the kernel's version, settings no one else sets)
and writes nothing on a refusal. Then it copies the module, writes both
registries, its settings into `.env.example` and `.railway/railway.ts`, and
its version and hashes into the lock. It prints steps 6 and 7 (migrations,
tests) for the site's own Python to run.

`remove` refuses while another module requires its module. It removes the
module's code (its backend package with its manifest, and its web folder),
its registry entries and its lock entry, and comments its settings out. It
keeps the module's tables and, so the database's version stays known to
Alembic, its migrations in `backend/migrations/<id>/`; its `railway.ts`
lines stay too, so an apply keeps what the owner typed into Railway.

Each runs whole or not at all: a failure half-way puts every file back. A run
holds the site by `.mechframe-busy` from its first read to its last write,
so two that overlap never plan from the same old lock.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from mechframe import layout, lock, ranges, registries, settings
from mechframe.hashes import digest
from mechframe.source import ROOT, load_json, module_dirs, module_manifest, package, schema_problems

BUSY = ".mechframe-busy"
_ID = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


class Refused(Exception):
    """`add` or `remove` won't do it; the message says why. Nothing was written."""


@dataclass
class Journal:
    """Every file a run changes, with what it held, so `undo` puts each back."""

    before: dict[Path, bytes | None] = field(default_factory=dict)
    folders: list[Path] = field(default_factory=list)

    def _keep(self, path: Path) -> None:
        if path not in self.before:
            self.before[path] = path.read_bytes() if path.is_file() else None

    def _parents(self, path: Path) -> None:
        missing = [parent for parent in path.parents if not parent.exists()]
        self.folders += reversed(missing)
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, path: Path, data: bytes) -> None:
        self._keep(path)
        self._parents(path)
        path.write_bytes(data)

    def copy(self, source: Path, target: Path) -> None:
        self._keep(target)
        self._parents(target)
        shutil.copyfile(source, target)

    def delete(self, path: Path) -> None:
        self._keep(path)
        path.unlink()

    def undo(self) -> None:
        for path, data in reversed(list(self.before.items())):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        for folder in reversed(self.folders):
            with suppress(OSError):  # not empty, or gone already
                folder.rmdir()


@contextmanager
def _busy(site: Path) -> Iterator[None]:
    """This run's hold on the site, from its first read to its last write, so
    two runs that overlap can't both plan from the old lock (Codex on #94)."""
    if not site.is_dir():
        raise Refused(f"{site} isn't a folder: is this a MechFrame site?")
    claim = site / BUSY
    try:
        claim.open("x").close()
    except FileExistsError:
        raise Refused(
            f"Another mechframe add or remove is writing to {site}. If none is, "
            f"one stopped half-way: delete {BUSY} there and run it again."
        ) from None
    try:
        yield
    finally:
        claim.unlink(missing_ok=True)


@dataclass(frozen=True)
class Added:
    site: Path
    id: str
    version: str
    files: int
    settings: list[dict[str, Any]]
    migrations: bool


@dataclass(frozen=True)
class Removed:
    site: Path
    id: str
    files: int
    edited: list[str]
    added: list[str]
    migrations: bool
    railway: list[str]


def _lock(site: Path, root: Path) -> dict[str, Any]:
    try:
        return lock.read(site, root)
    except lock.LockError as error:
        raise Refused("; ".join(error.problems)) from None


def built(root: Path = ROOT) -> list[str]:
    """Every module this checkout has built: not a scaffold, not planned."""
    found = []
    for folder in module_dirs(root):
        data = load_json(folder / "module.json")
        if data.get("status") != "planned":
            found.append(folder.name)
    return found


def checked_manifest(module_id: str, root: Path = ROOT) -> dict[str, Any]:
    """The checkout's manifest for a module it has built. Raises Refused."""
    if not _ID.match(module_id):
        raise Refused(f"{module_id!r} can't be a module's id.")
    known = built(root)
    data = module_manifest(module_id, root)
    if data is None or module_id not in [folder.name for folder in module_dirs(root)]:
        listed = ", ".join(known) or "none yet"
        raise Refused(f"This checkout has no module {module_id}. Its modules: {listed}.")
    if data.get("status") == "planned":
        listed = ", ".join(known) or "none yet"
        raise Refused(f"{module_id} isn't built yet: it's planned. Built: {listed}.")
    problems = schema_problems("module", data, root)
    if problems:
        raise Refused(f"modules/{module_id}/module.json doesn't validate: " + "; ".join(problems))
    return data


def _site_manifest(site: Path, module_id: str) -> dict[str, Any]:
    """A module's manifest as the site has it (its copy), else nothing."""
    path = site / "backend" / "modules" / package(module_id) / "module.json"
    try:
        data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data


def _meets(version: str, written: str, what: str) -> bool:
    try:
        return ranges.satisfies(version, written)
    except ranges.RangeError as error:
        raise Refused(f"{what}: {error}") from None


def _text(site: Path, relative: str) -> tuple[str, str]:
    """A site file's text with LF line endings, and its own line ending."""
    path = site / relative
    try:
        raw = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise Refused(
            f"{relative} is missing from {site}: is it a site `mechframe new` made?"
        ) from None
    ending = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), ending


def _plan_add(site: Path, data: dict[str, Any], module_id: str, root: Path) -> dict[str, Any]:
    """Every refusal `add` makes, before it writes anything."""
    installed = data["modules"]
    if module_id in installed:
        raise Refused(
            f"{module_id} {installed[module_id]['version']} is in the site already. "
            "Upgrading a module waits for its second version."
        )
    manifest = checked_manifest(module_id, root)
    needs = manifest["requires"]
    kernel = data["kernel"]["version"]
    if not _meets(kernel, needs["kernel"], f"{module_id}'s requires.kernel"):
        raise Refused(f"{module_id} needs the kernel {needs['kernel']}; the site's is {kernel}.")
    for other, written in sorted(needs.get("modules", {}).items()):
        if other not in installed:
            raise Refused(
                f"{module_id} needs {other} {written}: run `mechframe add {other}` first."
            )
        have = installed[other]["version"]
        if not _meets(have, written, f"{module_id}'s requires.modules.{other}"):
            raise Refused(f"{module_id} needs {other} {written}; the site has {other} {have}.")
    clashes = sorted(set(manifest["conflicts"]) & set(installed))
    clashes += sorted(
        other
        for other in installed
        if module_id in _site_manifest(site, other).get("conflicts", []) and other not in clashes
    )
    if clashes:
        raise Refused(f"{module_id} and {', '.join(clashes)} can't be in one site: they conflict.")
    env, _ = _text(site, settings.ENV)
    taken = settings.active(env, outside=module_id)
    for other in installed:
        taken |= {each["name"] for each in _site_manifest(site, other).get("env", [])}
    shared = sorted({each["name"] for each in manifest["env"]} & taken)
    if shared:
        raise Refused(f"{module_id} reads {', '.join(shared)}, which the site sets already.")
    for each in layout.module_copies(module_id):
        if each.folder and each.target.startswith("backend/migrations/"):
            continue  # a `remove` keeps a module's migrations
        if (site / each.target).exists():
            raise Refused(
                f"{each.target} is in the site, but {module_id} isn't in its lock: "
                "move it away, or put back the lock that had it."
            )
    return manifest


def _bound(site: Path, module_ids: list[str]) -> list[str]:
    """The modules whose web binding the site has."""
    return [
        each
        for each in module_ids
        if (site / "web" / "src" / "modules" / each / "module.web.ts").is_file()
    ]


def _write_registries(journal: Journal, site: Path, module_ids: list[str]) -> None:
    for relative, text in (
        (registries.PYTHON, registries.python(module_ids)),
        (registries.WEB, registries.web(_bound(site, module_ids))),
    ):
        path = site / relative
        journal.write(path, registries.encoded(text, registries.newline(path)))


def _write_lock(journal: Journal, site: Path, data: dict[str, Any], root: Path) -> None:
    journal.write(site / lock.NAME, lock.text(data, root).encode("utf-8"))


def add(site: Path, module_id: str, *, root: Path = ROOT, today: date | None = None) -> Added:
    """Add the module to the site. Raises Refused, having written nothing."""
    with _busy(site):
        return _add(site, module_id, root, today)


def _add(site: Path, module_id: str, root: Path, today: date | None) -> Added:
    data = _lock(site, root)
    manifest = _plan_add(site, data, module_id, root)
    env, env_ending = _text(site, settings.ENV)
    script, script_ending = _text(site, settings.RAILWAY)
    try:
        new_env = settings.env_with(env, module_id, manifest["env"])
        new_script = settings.railway_with(
            script, module_id, [each["name"] for each in manifest["env"]]
        )
    except settings.SettingsError as error:
        raise Refused(str(error)) from None
    journal = Journal()
    try:
        copied: dict[str, str] = {}
        for source, target in layout.files(root, layout.module_copies(module_id)):
            journal.copy(source, site / target)
            copied[target] = digest(site / target)
        data["modules"][module_id] = {
            "version": manifest["version"],
            "added": (today or date.today()).isoformat(),
            "files": dict(sorted(copied.items())),
        }
        _write_registries(journal, site, sorted(data["modules"]))
        journal.write(site / settings.ENV, registries.encoded(new_env, env_ending))
        journal.write(site / settings.RAILWAY, registries.encoded(new_script, script_ending))
        _write_lock(journal, site, data, root)
    except BaseException:
        journal.undo()
        raise
    has_migrations = any(target.startswith(f"backend/migrations/{module_id}/") for target in copied)
    return Added(
        site, module_id, manifest["version"], len(copied), list(manifest["env"]), has_migrations
    )


def _module_folders(module_id: str) -> list[str]:
    """What `remove` takes away: the module's code, not its migrations."""
    return [f"backend/modules/{package(module_id)}", f"web/src/modules/{module_id}"]


def remove(site: Path, module_id: str, *, root: Path = ROOT) -> Removed:
    """Remove the module from the site, keeping its tables. Raises Refused, having written nothing."""
    with _busy(site):
        return _remove(site, module_id, root)


def _remove(site: Path, module_id: str, root: Path) -> Removed:
    data = _lock(site, root)
    installed = data["modules"]
    if module_id not in installed:
        raise Refused(
            f"{module_id} isn't in the site. Its modules: {', '.join(sorted(installed)) or 'none'}."
        )
    needing = sorted(
        other
        for other in installed
        if other != module_id
        and module_id in _site_manifest(site, other).get("requires", {}).get("modules", {})
    )
    if needing:
        raise Refused(
            f"{', '.join(needing)} {'needs' if len(needing) == 1 else 'need'} {module_id}: remove {'it' if len(needing) == 1 else 'them'} first."
        )
    env, env_ending = _text(site, settings.ENV)
    script, _ = _text(site, settings.RAILWAY)
    entry = installed[module_id]
    recorded: dict[str, str] = entry["files"]
    edited = sorted(
        path
        for path, hashed in recorded.items()
        if (site / path).is_file() and digest(site / path) != hashed
    )
    going: list[Path] = []
    added: list[str] = []
    for folder in _module_folders(module_id):
        top = site / folder
        if not top.is_dir():
            continue
        for path in sorted(top.rglob("*")):
            if not path.is_file():
                continue
            going.append(path)
            inside = PurePosixPath(path.relative_to(top).as_posix())
            relative = f"{folder}/{inside}"
            if relative not in recorded and not layout.left_out(inside):
                added.append(relative)
    kept = [
        name
        for name in (each["name"] for each in _site_manifest(site, module_id).get("env", []))
        if name in settings.listed(script)
    ]
    journal = Journal()
    try:
        for path in going:
            journal.delete(path)
        for folder in _module_folders(module_id):
            top = site / folder
            if top.is_dir():
                shutil.rmtree(top)  # only folders are left: every file went above
        del installed[module_id]
        _write_registries(journal, site, sorted(installed))
        journal.write(
            site / settings.ENV,
            registries.encoded(settings.env_without(env, module_id), env_ending),
        )
        _write_lock(journal, site, data, root)
    except BaseException:
        journal.undo()
        raise
    migrations = (site / "backend" / "migrations" / module_id).is_dir()
    return Removed(site, module_id, len(going), edited, added, migrations, kept)


def setting_line(setting: dict[str, Any]) -> str:
    """One setting as `add` prints it: its name, whether it's required, what it is."""
    need = " (required)" if setting["required"] else ""
    return f"  {setting['name']}{need}: {' '.join(str(setting['description']).split())}"


def added_lines(made: Added) -> list[str]:
    """What `add` prints: steps 4, 6 and 7 of SPEC 12."""
    found = [
        f"Added {made.id} {made.version} to {made.site}: {made.files} files, both registries, "
        f"{settings.ENV}, {settings.RAILWAY} and the lock."
    ]
    if made.settings:
        found += ["", "Its settings, to set in .env and in Railway's variables:"]
        found += [setting_line(each) for each in made.settings]
    found += ["", "Next, in the site's folder:", '  $env:PYTHONPATH = "backend"']
    if made.migrations:
        found.append(f"  .venv/Scripts/python.exe -m app.migrations upgrade {made.id}@head")
    found += [
        "  .venv/Scripts/python.exe -m pytest backend/tests",
        "  cd web; npm run typecheck; npm test; cd ..",
    ]
    return found


def removed_lines(gone: Removed) -> list[str]:
    """What `remove` prints: what went, and what stayed."""
    found = [
        f"Removed {gone.id} from {gone.site}: {gone.files} files, its registry entries and its lock entry."
    ]
    if gone.edited:
        found.append(f"  Edited here, and gone with it: {', '.join(gone.edited)}")
    if gone.added:
        found.append(f"  Added here, and gone with it: {', '.join(gone.added)}")
    found += ["Kept:", "  its tables, in the database"]
    if gone.migrations:
        found.append(
            f"  its migrations, in backend/migrations/{gone.id}/, so the database's version stays known"
        )
    found.append(f"  its settings, commented out in {settings.ENV}")
    if gone.railway:
        found.append(
            f"  its settings in {settings.RAILWAY} as preserve(), so an apply keeps what was "
            "typed into Railway: delete those lines to have the next apply remove them"
        )
    return found
