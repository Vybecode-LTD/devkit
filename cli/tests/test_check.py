"""`mechframe check`: what a site edited, what is behind, which advisories are open (SPEC 12, 13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mechframe import check, lock
from mechframe.__main__ import main

from .conftest import advisory, set_advisories, write


def run(site: Path, checkout: Path) -> check.Report:
    return check.check(site, root=checkout)


def test_an_unedited_site_is_clean(site: Path, checkout: Path) -> None:
    report = run(site, checkout)
    assert report.problems == []
    assert (report.edited, report.missing, report.added) == ([], [], [])
    assert report.behind == []
    assert report.advisories == []
    assert report.exit_code() == 0


def test_the_copy_leaves_out_tests_caches_and_web_package_files(site: Path) -> None:
    files = set(lock.read(site)["kernel"]["files"]) | set(
        lock.read(site)["modules"]["demo-shop"]["files"]
    )
    assert "backend/kernel/auth/sessions.py" in files
    assert "backend/kernel/kernel.json" in files
    assert "backend/migrations/kernel/kernel_0001.py" in files
    assert "web/src/kernel/src/app/mount.ts" in files
    assert "backend/modules/demo_shop/router.py" in files
    assert "backend/modules/demo_shop/module.json" in files
    assert "backend/migrations/demo-shop/0001_demo_shop.py" in files
    assert "web/src/modules/demo-shop/module.web.ts" in files
    left_out = [name for name in files if "test" in name or "__pycache__" in name]
    assert left_out == []
    assert "web/src/kernel/package.json" not in files


def test_check_names_an_edited_a_missing_and_an_added_file(site: Path, checkout: Path) -> None:
    write(site / "backend" / "kernel" / "auth" / "sessions.py", "SESSIONS = 2\n")
    (site / "web" / "src" / "modules" / "demo-shop" / "module.web.ts").unlink()
    write(site / "backend" / "modules" / "demo_shop" / "extra.py", "EXTRA = 1\n")
    write(site / "backend" / "kernel" / "__pycache__" / "y.cpython-312.pyc", "junk")
    report = run(site, checkout)
    assert report.edited == ["backend/kernel/auth/sessions.py"]
    assert report.missing == ["web/src/modules/demo-shop/module.web.ts"]
    assert report.added == ["backend/modules/demo_shop/extra.py"]
    assert report.exit_code() == 0  # edits are reported, not failures


def test_a_checkout_with_windows_line_endings_reads_as_unedited(site: Path, checkout: Path) -> None:
    target = site / "backend" / "kernel" / "auth" / "sessions.py"
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    assert run(site, checkout).edited == []


def test_check_names_a_copy_behind_the_checkout(site: Path, checkout: Path) -> None:
    path = checkout / "modules" / "demo-shop" / "module.json"
    data = json.loads(path.read_text("utf-8"))
    data["version"] = "0.2.0"
    path.write_text(json.dumps(data), encoding="utf-8")
    report = run(site, checkout)
    assert [(each.id, each.copy, each.latest) for each in report.behind] == [
        ("demo-shop", "0.1.0", "0.2.0")
    ]
    assert report.exit_code() == 0


def test_a_module_the_checkout_doesn_t_have_is_named(site: Path, checkout: Path) -> None:
    data = lock.read(site, root=checkout)
    data["modules"]["gone"] = {"version": "0.1.0", "added": "2026-11-20", "files": {}}
    lock.write(site, data, root=checkout)
    assert run(site, checkout).unknown == ["gone"]


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_an_open_high_advisory_fails_the_check(site: Path, checkout: Path, severity: str) -> None:
    set_advisories(checkout, advisory(severity=severity))
    report = run(site, checkout)
    assert [entry["id"] for entry in report.advisories] == ["MF-2026-0001"]
    assert report.exit_code() == 1


def test_a_low_advisory_is_named_but_passes(site: Path, checkout: Path) -> None:
    set_advisories(
        checkout, advisory(severity="low"), advisory(id="MF-2026-0002", severity="medium")
    )
    report = run(site, checkout)
    assert [entry["id"] for entry in report.advisories] == ["MF-2026-0001", "MF-2026-0002"]
    assert report.exit_code() == 0


def test_only_advisories_for_the_site_s_own_versions_are_open(site: Path, checkout: Path) -> None:
    set_advisories(
        checkout,
        advisory(id="MF-2026-0001", fixed="0.0.2"),  # fixed below the kernel's copy
        advisory(id="MF-2026-0002", introduced="9.0.0"),  # after the copy
        advisory(id="MF-2026-0003", module="not-here"),  # a module the site lacks
        advisory(id="MF-2026-0004", module="demo-shop", introduced="0.1.0", fixed="0.1.1"),
    )
    assert [entry["id"] for entry in run(site, checkout).advisories] == ["MF-2026-0004"]


def test_a_missing_or_invalid_lock_is_refused(site: Path, checkout: Path) -> None:
    path = site / lock.NAME
    data = json.loads(path.read_text("utf-8"))
    data["kernel"]["files"]["backend/kernel/x.py"] = "md5:nope"
    path.write_text(json.dumps(data), encoding="utf-8")
    report = run(site, checkout)
    assert report.problems
    assert report.exit_code() == 2
    path.unlink()
    assert run(site, checkout).exit_code() == 2


def test_a_copied_manifest_that_doesn_t_validate_is_refused(site: Path, checkout: Path) -> None:
    path = site / "backend" / "modules" / "demo_shop" / "module.json"
    data = json.loads(path.read_text("utf-8"))
    del data["summary"]
    path.write_text(json.dumps(data), encoding="utf-8")
    report = run(site, checkout)
    assert any("module.json" in problem for problem in report.problems)
    assert report.exit_code() == 2


def test_the_command_prints_a_report_or_json(
    site: Path, checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(site / "backend" / "kernel" / "auth" / "sessions.py", "SESSIONS = 2\n")
    assert main(["check", "--site", str(site), "--root", str(checkout)]) == 0
    printed = capsys.readouterr().out
    assert "Edited: backend/kernel/auth/sessions.py" in printed
    assert main(["check", "--site", str(site), "--root", str(checkout), "--json"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["edited"] == ["backend/kernel/auth/sessions.py"]
    assert answer["exit"] == 0
