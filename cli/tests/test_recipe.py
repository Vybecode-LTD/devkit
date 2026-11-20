"""`mechframe new <dir> --recipe <id>` (the K5 contract §2 and §4 item 4): the
kernel's site, then `add` for each of the recipe's modules, in the order their
`requires` need, or nothing at all."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mechframe import check, lock, modules
from mechframe.__main__ import main

from .conftest import write


def _new(root: Path, folder: Path, *extra: str) -> int:
    return main(["new", str(folder), "--root", str(root), *extra])


def _recipe(root: Path, recipe_id: str, module_ids: list[str]) -> None:
    data = {
        "id": recipe_id,
        "name": recipe_id.capitalize(),
        "fits": ["A site made for the CLI's tests"],
        "modules": module_ids,
        "settings": {},
        "theme": "machined-light",
    }
    write(root / "recipes" / f"{recipe_id}.json", json.dumps(data, indent=2) + "\n")


def test_a_recipe_adds_its_modules_in_the_order_they_need(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "notebook"
    assert _new(site_maker, folder, "--recipe", "fixture-notebook") == 0
    out = capsys.readouterr().out
    data = lock.read(folder, site_maker)
    assert data["recipe"] == "fixture-notebook"
    assert sorted(data["modules"]) == ["fixture-notes", "fixture-pins"]
    assert data["theme"] == "vibrant-mindz"  # the recipe's
    report = check.check(folder, root=site_maker)
    assert report.exit_code() == 0, report.lines()
    assert "with fixture-notes 0.1.0, fixture-pins 0.1.0" in out
    assert "auth.signup_mode: closed" in out  # its settings, for Admin, Settings
    assert "FIXTURE_NOTES_FEED_URL (required)" in out


def test_a_theme_given_wins_over_the_recipes(site_maker: Path, tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    assert (
        _new(site_maker, folder, "--recipe", "fixture-notebook", "--theme", "machined-light") == 0
    )
    assert lock.read(folder, site_maker)["theme"] == "machined-light"


def _refused(root: Path, folder: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> str:
    capsys.readouterr()
    assert _new(root, folder, *extra) == 2
    assert not folder.exists()  # nothing written
    return capsys.readouterr().err


def test_a_recipe_naming_modules_not_built_lists_them(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _recipe(site_maker, "later-site", ["fixture-notes", "planned-thing", "no-such-thing"])
    err = _refused(site_maker, tmp_path / "later", capsys, "--recipe", "later-site")
    assert (
        "later-site needs modules this checkout hasn't built: planned-thing, no-such-thing" in err
    )


def test_an_unknown_recipe_lists_the_recipes(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = _refused(site_maker, tmp_path / "x", capsys, "--recipe", "no-such-recipe")
    assert "There's no recipe no-such-recipe. The recipes: fixture-notebook." in err


def test_a_recipe_without_a_module_one_of_its_needs_is_refused(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _recipe(site_maker, "pins-alone", ["fixture-pins"])
    err = _refused(site_maker, tmp_path / "pins", capsys, "--recipe", "pins-alone")
    assert "fixture-pins needs fixture-notes, which pins-alone doesn't have." in err


def test_a_recipe_holding_two_that_conflict_is_refused(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _recipe(site_maker, "rivals", ["fixture-notes", "fixture-pins", "fixture-rival"])
    err = _refused(site_maker, tmp_path / "rivals", capsys, "--recipe", "rivals")
    assert "fixture-pins and fixture-rival can't be in one site" in err


def test_a_recipe_that_doesnt_validate_is_refused(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(site_maker / "recipes" / "broken.json", json.dumps({"id": "broken"}) + "\n")
    err = _refused(site_maker, tmp_path / "broken", capsys, "--recipe", "broken")
    assert "recipes/broken.json doesn't validate" in err


def test_a_failure_in_an_add_takes_the_whole_site_away(
    site_maker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = modules.add
    calls: list[str] = []

    def failing(site: Path, module_id: str, **kwargs: object) -> modules.Added:
        calls.append(module_id)
        if len(calls) == 2:
            raise OSError("the disk is full")
        return real(site, module_id, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(modules, "add", failing)
    folder = tmp_path / "half"
    with pytest.raises(OSError, match="the disk is full"):
        main(["new", str(folder), "--root", str(site_maker), "--recipe", "fixture-notebook"])
    assert calls == ["fixture-notes", "fixture-pins"]
    assert not folder.exists()
