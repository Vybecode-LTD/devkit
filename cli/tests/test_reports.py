"""The edges of `check` and its report, the lock, the catalog and versions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mechframe import catalog, check, layout, lock, source, versions
from mechframe.__main__ import main

from .conftest import add_module, advisory, set_advisories, write


def test_a_refused_check_prints_why_and_exits_2(
    tmp_path: Path, checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check", "--site", str(tmp_path / "nowhere"), "--root", str(checkout)]) == 2
    printed = capsys.readouterr().out
    assert "there's none in" in printed
    assert "Result: refused (exit 2)" in printed


def test_the_report_names_advisories_and_modules_the_checkout_lacks(
    site: Path, checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    set_advisories(checkout, advisory(fixed="0.9.0"), advisory(id="MF-2026-0002", severity="low"))
    data = lock.read(site, root=checkout)
    data["modules"]["gone"] = {"version": "0.1.0", "added": "2026-11-20", "files": {}}
    lock.write(site, data, root=checkout)
    assert main(["check", "--site", str(site), "--root", str(checkout)]) == 1
    printed = capsys.readouterr().out
    assert "Not in this checkout: gone" in printed
    assert "MF-2026-0001 (high) kernel, fixed in 0.9.0: Something the kernel got wrong" in printed
    assert "MF-2026-0002 (low) kernel, no fix yet" in printed
    assert "Result: failed: an open high or critical advisory" in printed


def test_a_clean_report_says_it_passed(
    site: Path, checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check", "--site", str(site), "--root", str(checkout)]) == 0
    printed = capsys.readouterr().out
    assert "Copies: kernel " in printed
    assert "demo-shop 0.1.0" in printed
    assert "Advisories: none open" in printed
    assert printed.rstrip().endswith("Result: passed")


def test_a_copied_manifest_that_isn_t_json_is_refused(site: Path, checkout: Path) -> None:
    write(site / "backend" / "kernel" / "kernel.json", "{not json")
    report = check.check(site, root=checkout)
    assert any(
        problem.startswith("backend/kernel/kernel.json: can't be read")
        for problem in report.problems
    )
    assert report.exit_code() == 2


def test_a_checkout_s_bad_advisories_file_is_refused(site: Path, checkout: Path) -> None:
    set_advisories(checkout, advisory(severity="severe"))
    report = check.check(site, root=checkout)
    assert any("advisories.json in the checkout" in problem for problem in report.problems)
    assert report.exit_code() == 2


def test_a_lock_that_isn_t_json_is_refused(site: Path, checkout: Path) -> None:
    (site / lock.NAME).write_text("{not json", "utf-8")
    with pytest.raises(lock.LockError, match="can't be read as JSON"):
        lock.read(site, root=checkout)


def test_a_lock_that_doesn_t_validate_isn_t_written(tmp_path: Path, checkout: Path) -> None:
    with pytest.raises(lock.LockError) as refused:
        lock.write(tmp_path, {"mechframe": "0.1.0"}, root=checkout)
    assert refused.value.problems
    assert not (tmp_path / lock.NAME).exists()


def test_a_module_without_web_or_migrations_copies_what_it_has(
    tmp_path: Path, checkout: Path
) -> None:
    folder = add_module(checkout, "bare-one")
    for name in ("web", "migrations"):
        for path in sorted((folder / name).rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (folder / name).rmdir()
    (folder / "CHANGELOG.md").unlink()
    taken = [target for _, target in layout.files(checkout, layout.module_copies("bare-one"))]
    assert taken == [
        "backend/modules/bare_one/__init__.py",
        "backend/modules/bare_one/router.py",
        "backend/modules/bare_one/module.json",
        "backend/modules/bare_one/MODULE.md",
    ]
    assert layout.site_files(tmp_path / "empty", layout.module_copies("bare-one")) == []


def test_a_missing_catalog_is_stale(checkout: Path) -> None:
    (checkout / "catalog.json").unlink()
    assert catalog.stale(checkout)


def test_a_checkout_without_modules_has_none(tmp_path: Path) -> None:
    assert source.module_dirs(tmp_path) == []
    assert source.module_manifest("anything", tmp_path) is None


def test_a_version_prints_as_written_and_compares_only_with_versions() -> None:
    assert str(versions.parse("0.1.0-dev.0")) == "0.1.0-dev.0"
    assert str(versions.parse("1.2.3")) == "1.2.3"
    assert versions.parse("1.2.3").__lt__("1.2.4") is NotImplemented


def test_the_catalog_entry_keeps_the_manifest_s_words(checkout: Path) -> None:
    entry = next(each for each in catalog.build(checkout)["modules"] if each["id"] == "demo-shop")
    manifest = json.loads((checkout / "modules" / "demo-shop" / "module.json").read_text("utf-8"))
    assert entry == {field: manifest[field] for field in catalog.FIELDS}
