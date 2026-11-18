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
- a listed one npm no longer reports, so the list can't outlive its reasons.

Each entry names the advisory (its GHSA id), the package, why it's accepted
and until when. Accept only an advisory with no fixed version that reaches
nothing a visitor can drive (the build and test tools, say), and say so in
the pull request.
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
    report: Mapping[str, Any], allowed: Sequence[Mapping[str, Any]], today: date
) -> list[str]:
    """What's wrong, if anything: an advisory not allowed, an allowance
    ended, too long or not needed any more, or an entry missing its reason."""
    problems = []
    found = advisories(report)
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
        elif until < today:
            problems.append(
                f"{ident}'s allowance ended on {until}: upgrade, or renew it on purpose."
            )
        elif until > today + LONGEST:
            problems.append(f"{ident}'s allowance runs past {today + LONGEST}: 90 days at most.")
        else:
            allow[ident] = entry
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


def main(argv: Sequence[str] | None = None, *, today: date | None = None) -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm isn't on PATH.", file=sys.stderr)
        return 2
    result = subprocess.run(  # noqa: S603  (npm itself, a fixed command)
        [npm, "audit", "--json"], capture_output=True, text=True, cwd=ROOT, check=False
    )
    try:
        report = json.loads(result.stdout)
        allowed = json.loads(ALLOW.read_text("utf-8"))["allow"]
        problems = check(report, allowed, today or date.today())
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
