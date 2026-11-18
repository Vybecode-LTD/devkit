"""npm audit, with the advisories the project has accepted for a while
(decision 0015, amended 2026-11-17).

    python -m tools.npm_audit

`npm audit --audit-level=low` fails on any advisory, and npm has no way to
accept one. An advisory with no fixed version yet can't be fixed by an
upgrade, so CI would stay red for every pull request until upstream ships
one. This runs `npm audit --json` and fails on:

- any advisory not listed in `tools/npm_audit_allow.json`;
- a listed one whose `until` date has passed, or lies more than 90 days
  ahead (an allowance is renewed on purpose, never left standing);
- a listed one npm no longer reports, so the list can't outlive its reasons;
- a listed one that reaches the production dependencies (`npm audit --omit=dev`);
- a listed package with a release newer than the entry's `latest`, which may
  carry the fix. npm's own `fixAvailable` can't say: it may name a downgrade of
  a parent (for picomatch, vite 6.2.7). Upgrade if the release fixes it, or set
  `latest` to it on purpose.

Each entry names the advisory (its GHSA id), the package, why it's accepted,
until when, and the package's newest version when it was accepted. Accept
only an advisory with no fixed version that reaches nothing a visitor can
drive (the build and test tools, say), and say so in the pull request.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ALLOW = ROOT / "tools" / "npm_audit_allow.json"
#: The longest an allowance may run from today.
LONGEST = timedelta(days=90)


def advisories(report: Mapping[str, Any]) -> dict[str, set[str]]:
    """The advisories `npm audit --json` names, by id, with the packages each
    is found in. A package flagged only through another (`via` a name) adds
    nothing: its advisory is the other's. Raises ValueError when npm didn't
    report."""
    vulnerabilities = report.get("vulnerabilities")
    if "error" in report or not isinstance(vulnerabilities, Mapping):
        raise ValueError(
            f"npm audit didn't report: {json.dumps(report.get('error', report))[:500]}"
        )
    found: dict[str, set[str]] = {}
    for name, vulnerability in vulnerabilities.items():
        for via in vulnerability.get("via", []):
            if isinstance(via, Mapping):
                ident = str(via.get("url", "")).rstrip("/").rsplit("/", 1)[-1] or str(via["source"])
                found.setdefault(ident, set()).add(str(via.get("name", name)))
    return found


def check(
    report: Mapping[str, Any],
    allowed: Sequence[Mapping[str, Any]],
    today: date,
    *,
    production: Mapping[str, Any] | None = None,
    newest: Mapping[str, str] | None = None,
) -> list[str]:
    """What's wrong, if anything: an advisory not allowed, an allowance
    ended, too long or not needed any more, an entry missing its reason, and,
    when given, an allowed advisory in the `production` report (`npm audit
    --omit=dev`) or a package whose `newest` release is past the entry's."""
    problems = []
    found = advisories(report)
    shipped = advisories(production) if production is not None else {}
    allow: dict[str, Mapping[str, Any]] = {}
    for entry in allowed:
        ident = str(entry.get("id", ""))
        try:
            until = date.fromisoformat(str(entry.get("until", "")))
        except ValueError:
            problems.append(f"{ident or 'An entry'} needs `until`, a date such as 2026-12-31.")
            continue
        if not ident or not str(entry.get("why", "")).strip():
            problems.append(f"{ident or 'An entry'} needs an `id` and a `why`.")
        elif not str(entry.get("package", "")):
            problems.append(f"{ident} needs its `package`.")
        elif until < today:
            problems.append(
                f"{ident}'s allowance ended on {until}: upgrade, or renew it on purpose."
            )
        elif until > today + LONGEST:
            problems.append(f"{ident}'s allowance runs past {today + LONGEST}: 90 days at most.")
        else:
            allow[ident] = entry
            problems += _still_dev_only_and_unfixed(ident, entry, shipped, newest)
    for ident in sorted(found):
        if ident not in allow and ident not in {str(entry.get("id")) for entry in allowed}:
            packages = ", ".join(sorted(found[ident]))
            problems.append(
                f"{ident} ({packages}) isn't allowed: upgrade, or add it to {ALLOW.name} "
                "with a reason and a date."
            )
    for ident in sorted(set(allow) - set(found)):
        problems.append(
            f"{ident} is allowed but npm no longer reports it: remove it from {ALLOW.name}."
        )
    return problems


def _still_dev_only_and_unfixed(
    ident: str,
    entry: Mapping[str, Any],
    shipped: Mapping[str, set[str]],
    newest: Mapping[str, str] | None,
) -> list[str]:
    problems = []
    package = str(entry["package"])
    if ident in shipped:
        packages = ", ".join(sorted(shipped[ident]))
        problems.append(
            f"{ident} reaches the production dependencies ({packages}): an allowance covers "
            "the build and test tools only."
        )
    if newest is not None:
        latest = str(entry.get("latest", ""))
        if not latest:
            problems.append(f"{ident} needs `latest`, the newest {package} when it was allowed.")
        elif newest.get(package) != latest:
            release = newest.get(package)
            problems.append(
                f"{package} {release} is out since {ident} was allowed at {latest}: if it "
                f"fixes the advisory, upgrade and remove the entry; if not, set `latest` to "
                f"{release}."
            )
    return problems


def _newest(npm: str, packages: set[str]) -> dict[str, str]:
    """Each package's newest release on the registry. Raises ValueError when
    npm doesn't answer."""
    found = {}
    for package in sorted(packages):
        result = subprocess.run(  # noqa: S603  (npm itself, the package from our own list)
            [npm, "view", package, "version"], capture_output=True, text=True, cwd=ROOT, check=False
        )
        version = (result.stdout or "").strip()
        if result.returncode != 0 or not version:
            raise ValueError(f"npm view {package} version didn't answer")
        found[package] = version
    return found


def main(argv: Sequence[str] | None = None, *, today: date | None = None) -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm isn't on PATH.", file=sys.stderr)
        return 2
    reports = [
        subprocess.run(  # noqa: S603  (npm itself, a fixed command)
            [npm, "audit", "--json", *extra], capture_output=True, text=True, cwd=ROOT, check=False
        ).stdout
        for extra in ([], ["--omit=dev"])
    ]
    try:
        report, production = (json.loads(text) for text in reports)
        allowed = json.loads(ALLOW.read_text("utf-8"))["allow"]
        packages = {str(entry.get("package", "")) for entry in allowed} - {""}
        problems = check(
            report,
            allowed,
            today or date.today(),
            production=production,
            newest=_newest(npm, packages),
        )
    except (ValueError, KeyError) as error:
        print(f"Couldn't check npm audit: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        accepted = ", ".join(sorted(advisories(report))) or "none"
        print(f"npm audit: nothing but the allowed advisories ({accepted}).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
