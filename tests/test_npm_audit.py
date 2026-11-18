"""tools.npm_audit: npm audit with an allowlist that can't outlive its reasons."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from typing import Any

import pytest

from tools import npm_audit

TODAY = date(2026, 11, 17)
PICO = "GHSA-fc5q-39xc-vjpf"


def _report(*advisories: tuple[str, str]) -> dict[str, Any]:
    """A report flagging each (package, id), and a package flagged only through the first."""
    vulnerabilities: dict[str, Any] = {}
    for package, ident in advisories:
        via = {"source": 1, "name": package, "url": f"https://github.com/advisories/{ident}"}
        vulnerabilities.setdefault(package, {"via": []})["via"].append(via)
    if advisories:
        vulnerabilities["vite"] = {"via": [advisories[0][0]]}
    return {"auditReportVersion": 2, "vulnerabilities": vulnerabilities}


def _allowed(
    until: str = "2026-12-17", ident: str = PICO, why: str = "No fix yet."
) -> list[dict[str, str]]:
    return [{"id": ident, "package": "picomatch", "until": until, "why": why}]


def test_an_allowed_advisory_passes() -> None:
    assert npm_audit.check(_report(("picomatch", PICO)), _allowed(), TODAY) == []


def test_any_other_advisory_fails() -> None:
    problems = npm_audit.check(
        _report(("picomatch", PICO), ("minimatch", "GHSA-g3hv-75wg-m249")), _allowed(), TODAY
    )
    assert problems == [
        "GHSA-g3hv-75wg-m249 (minimatch) isn't allowed: upgrade, or add it to "
        "npm_audit_allow.json with a reason and a date."
    ]


def test_an_allowance_ends() -> None:
    assert npm_audit.check(_report(("picomatch", PICO)), _allowed("2026-11-16"), TODAY) == [
        f"{PICO}'s allowance ended on 2026-11-16: upgrade, or renew it on purpose."
    ]
    assert npm_audit.check(_report(("picomatch", PICO)), _allowed("2026-11-17"), TODAY) == []


def test_an_allowance_is_ninety_days_at_most() -> None:
    assert npm_audit.check(_report(("picomatch", PICO)), _allowed("2027-02-16"), TODAY) != []
    assert npm_audit.check(_report(("picomatch", PICO)), _allowed("2027-02-15"), TODAY) == []


def test_an_allowance_no_longer_needed_fails() -> None:
    assert npm_audit.check(_report(), _allowed(), TODAY) == [
        f"{PICO} is allowed but npm no longer reports it: remove it from npm_audit_allow.json."
    ]


@pytest.mark.parametrize(
    "entry",
    [
        {"id": PICO, "until": "soon", "why": "x"},
        {"id": PICO, "why": "x"},
        {"id": PICO, "until": "2026-12-01", "why": " "},
        {"until": "2026-12-01", "why": "x"},
    ],
)
def test_an_entry_needs_its_id_reason_and_date(entry: dict[str, str]) -> None:
    problems = npm_audit.check(_report(("picomatch", PICO)), [entry], TODAY)
    assert "needs" in problems[0]
    # A listed id is never also "not allowed"; an entry with no id leaves its advisory unlisted.
    assert len(problems) == (1 if "id" in entry else 2)


@pytest.mark.parametrize("report", [{"error": {"code": "ENOLOCK"}}, {}, {"vulnerabilities": []}])
def test_a_report_npm_didnt_make_is_an_error(report: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="didn't report"):
        npm_audit.advisories(report)


def test_the_projects_list_is_well_formed() -> None:
    listed = json.loads(npm_audit.ALLOW.read_text("utf-8"))["allow"]
    for entry in listed:
        assert set(entry) == {"id", "package", "until", "why"}
        assert entry["id"].startswith("GHSA-")
        date.fromisoformat(entry["until"])


class _Ran:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_main_runs_npm_and_says_what_it_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> _Ran:
        ran.append(command)
        return _Ran(json.dumps(_report(("picomatch", PICO))))

    monkeypatch.setattr(npm_audit.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(npm_audit, "ALLOW", _allow_file(_allowed()))
    assert npm_audit.main([], today=TODAY) == 0
    assert ran == [["/usr/bin/npm", "audit", "--json"]]
    assert PICO in capsys.readouterr().out

    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: _Ran(json.dumps(_report())))
    assert npm_audit.main([], today=TODAY) == 1
    assert "no longer reports" in capsys.readouterr().err

    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: _Ran("not json"))
    assert npm_audit.main([], today=TODAY) == 2


def test_main_needs_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(npm_audit.shutil, "which", lambda name: None)
    assert npm_audit.main([]) == 2


def _allow_file(allowed: list[dict[str, str]]) -> Any:
    class _File:
        name = "npm_audit_allow.json"

        def read_text(self, encoding: str) -> str:
            return json.dumps({"allow": allowed})

    return _File()


def _ci_filter(name: str) -> re.Pattern[str]:
    """The pattern CI's `changes` job uses to decide whether a job runs."""
    workflow = (npm_audit.ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    match = re.search(rf"^\s*{name}=\$\(any '([^']+)'\)", workflow, re.MULTILINE)
    assert match, f"ci.yml has no {name} filter"
    return re.compile(match.group(1))


@pytest.mark.parametrize("path", ["tools/npm_audit.py", "tools/npm_audit_allow.json"])
def test_a_change_to_the_audit_runs_the_web_job(path: str) -> None:
    # The Web job is the one that runs the audit against the real lockfile: a
    # change to the tool or its list must be checked there before it merges.
    assert _ci_filter("web").search(path)


def test_an_unrelated_tool_doesn_t_run_the_web_job() -> None:
    assert not _ci_filter("web").search("tools/progress.py")
