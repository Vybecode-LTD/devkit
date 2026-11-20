"""`mechframe check`: a site against its lock and this checkout (SPEC.md sections 12 and 13).

- The lock validates, and so do the copied `kernel.json` and each `module.json`.
- Each recorded file: edited or missing; each file in a copied folder the lock
  doesn't record: added.
- Each copy's version against the checkout's: behind, or not in this checkout.
- Every open advisory in `advisories.json` for the site's versions (the K5
  contract's change 1).

Edits and versions behind are reported, not failures. It exits 2 when the
lock or a copied manifest doesn't validate, 1 on an open high or critical
advisory, and 0 otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mechframe import layout, lock, versions
from mechframe.hashes import digest
from mechframe.source import (
    ROOT,
    kernel_manifest,
    load_json,
    module_manifest,
    package,
    schema_problems,
)

FAILING = frozenset({"high", "critical"})


@dataclass(frozen=True)
class Behind:
    id: str
    copy: str
    latest: str


@dataclass
class Report:
    site: Path
    problems: list[str] = field(default_factory=list)
    edited: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    behind: list[Behind] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    advisories: list[dict[str, Any]] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)

    def exit_code(self) -> int:
        if self.problems:
            return 2
        return 1 if any(entry["severity"] in FAILING for entry in self.advisories) else 0

    def as_json(self) -> dict[str, Any]:
        return {
            "site": str(self.site),
            "problems": self.problems,
            "versions": self.versions,
            "edited": self.edited,
            "missing": self.missing,
            "added": self.added,
            "behind": [
                {"id": each.id, "copy": each.copy, "latest": each.latest} for each in self.behind
            ],
            "not_in_checkout": self.unknown,
            "advisories": self.advisories,
            "exit": self.exit_code(),
        }

    def lines(self) -> list[str]:
        def listed(label: str, items: list[str]) -> str:
            return f"{label}: {', '.join(items) if items else 'none'}"

        found = [f"mechframe check: {self.site}"]
        if self.problems:
            found += ["Refused, nothing else checked:" if not self.versions else "Refused:"]
            found += [f"  {problem}" for problem in self.problems]
            return [*found, "Result: refused (exit 2)"]
        copies = [f"{name} {version}" for name, version in self.versions.items()]
        found += [
            f"Copies: {', '.join(copies)}",
            listed("Edited", self.edited),
            listed("Missing", self.missing),
            listed("Added", self.added),
            listed(
                "Behind", [f"{each.id} {each.copy} (latest {each.latest})" for each in self.behind]
            ),
        ]
        if self.unknown:
            found.append(listed("Not in this checkout", self.unknown))
        if self.advisories:
            found.append("Advisories:")
            for entry in self.advisories:
                fix = f"fixed in {entry['fixed']}" if entry["fixed"] else "no fix yet"
                found.append(
                    f"  {entry['id']} ({entry['severity']}) {entry['module']}, {fix}: {entry['summary']}"
                )
        else:
            found.append("Advisories: none open")
        verdict = "failed: an open high or critical advisory" if self.exit_code() else "passed"
        return [*found, f"Result: {verdict}"]


def _manifest_problems(site: Path, data: dict[str, Any], root: Path) -> list[str]:
    found = []
    targets = [("kernel", "backend/kernel/kernel.json")]
    targets += [
        ("module", f"backend/modules/{package(module_id)}/module.json")
        for module_id in data["modules"]
    ]
    for schema, target in targets:
        path = site / target
        if not path.is_file():
            continue  # the hashes name it as missing
        try:
            manifest = load_json(path)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            found.append(f"{target}: can't be read as JSON ({error})")
            continue
        found += [f"{target}: {problem}" for problem in schema_problems(schema, manifest, root)]
    return found


def _files(report: Report, site: Path, recorded: dict[str, str], copies: list[layout.Copy]) -> None:
    for target, expected in recorded.items():
        path = site / target
        if not path.is_file():
            report.missing.append(target)
            continue
        try:
            found = digest(path)
        except OSError as error:  # a refusal, never a traceback (CodeRabbit on #91)
            report.problems.append(f"{target}: can't be read ({error.strerror or error})")
            continue
        if found != expected:
            report.edited.append(target)
    report.added += [target for target in layout.site_files(site, copies) if target not in recorded]


def _semver(report: Report, what: str, text: str) -> versions.Version | None:
    """`text` as a version, or a problem naming `what`: the schemas' patterns let
    through a few versions semver refuses, such as `0.1.0-01` (Codex on #91)."""
    try:
        return versions.parse(text)
    except ValueError:
        report.problems.append(f"{what} {text!r} isn't a semver version")
        return None


def _affected(
    copy: versions.Version, introduced: versions.Version, fixed: versions.Version | None
) -> bool:
    return not copy < introduced and (fixed is None or copy < fixed)


def check(site: Path, root: Path = ROOT) -> Report:
    report = Report(site=site)
    try:
        data = lock.read(site, root)
    except lock.LockError as error:
        report.problems = error.problems
        return report
    report.versions = {"kernel": data["kernel"]["version"]} | {
        module_id: entry["version"] for module_id, entry in sorted(data["modules"].items())
    }
    report.problems = _manifest_problems(site, data, root)

    _files(report, site, data["kernel"]["files"], layout.kernel_copies())
    for module_id, entry in sorted(data["modules"].items()):
        _files(report, site, entry["files"], layout.module_copies(module_id))
    report.edited.sort()
    report.missing.sort()
    report.added.sort()

    latest = {"kernel": kernel_manifest(root)["version"]}
    for module_id in data["modules"]:
        manifest = module_manifest(module_id, root)
        if manifest is None:
            report.unknown.append(module_id)
        else:
            latest[module_id] = manifest["version"]
    copies = {
        name: _semver(report, f"{lock.NAME}: {name}'s version", version)
        for name, version in report.versions.items()
    }
    for name, version in report.versions.items():
        newest = (
            _semver(report, f"The checkout's {name} version", latest[name])
            if name in latest
            else None
        )
        copy = copies[name]
        if copy is not None and newest is not None and copy < newest:
            report.behind.append(Behind(name, version, latest[name]))

    advisories = load_json(root / "advisories.json")
    problems = schema_problems("advisories", advisories, root)
    if problems:
        report.problems += [f"advisories.json in the checkout: {problem}" for problem in problems]
        return report
    # The schema's pattern is semver's own grammar, so these parse (CodeRabbit on #91).
    for entry in advisories["advisories"]:
        copy = copies.get(entry["module"])
        if copy is None:
            continue
        introduced = versions.parse(entry["introduced"])
        fixed = versions.parse(entry["fixed"]) if entry["fixed"] else None
        if _affected(copy, introduced, fixed):
            report.advisories.append(entry)
    return report
