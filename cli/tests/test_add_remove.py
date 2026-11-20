"""`mechframe add` and `remove` (SPEC.md section 12; the K5 contract §2, §4 item 4
and §7; decision 0050), on the fixture modules in `cli/tests/fixtures/`:

- `fixture-notes`: two settings, a migration and a web binding;
- `fixture-pins`: requires `fixture-notes ^0.1`, conflicts with `fixture-rival`,
  one setting and a web binding, no migrations;
- `fixture-rival`: a backend package alone.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from dotenv import dotenv_values

from mechframe import check, lock, modules, registries, settings
from mechframe.__main__ import main

from .conftest import tree, write


def _run(root: Path, *argv: str) -> int:
    return main([*argv, "--root", str(root)])


def _add(root: Path, site: Path, module_id: str) -> int:
    return _run(root, "add", module_id, "--site", str(site))


def _remove(root: Path, site: Path, module_id: str) -> int:
    return _run(root, "remove", module_id, "--site", str(site))


def _clean(root: Path, site: Path) -> None:
    report = check.check(site, root=root)
    assert report.exit_code() == 0, report.lines()
    assert (report.edited, report.missing, report.added) == ([], [], [])


def _railway(site: Path) -> set[str]:
    return settings.listed((site / settings.RAILWAY).read_text("utf-8"))


def test_add_copies_the_module_and_writes_every_file_that_lists_it(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert _add(site_maker, made, "fixture-notes") == 0
    out = capsys.readouterr().out
    assert (made / "backend/modules/fixture_notes/router.py").is_file()
    assert (made / "backend/modules/fixture_notes/module.json").is_file()
    assert (made / "backend/migrations/fixture-notes/0001_fixture_notes_note.py").is_file()
    assert (made / "web/src/modules/fixture-notes/module.web.ts").is_file()
    assert 'MODULE_IDS: tuple[str, ...] = ("fixture-notes",)' in (
        made / registries.PYTHON
    ).read_text("utf-8")
    web = (made / registries.WEB).read_text("utf-8")
    assert 'import fixtureNotesModule from "./modules/fixture-notes/module.web";' in web
    assert "export const modules: ModuleDefinition[] = [fixtureNotesModule];" in web
    env = dotenv_values(made / settings.ENV)
    assert env["FIXTURE_NOTES_FEED_URL"] == ""
    assert env["FIXTURE_NOTES_PAGE_SIZE"] == ""
    assert {"FIXTURE_NOTES_FEED_URL", "FIXTURE_NOTES_PAGE_SIZE"} <= _railway(made)
    entry = lock.read(made, site_maker)["modules"]["fixture-notes"]
    assert entry["version"] == "0.1.0"
    assert entry["added"] == date.today().isoformat()
    assert "backend/modules/fixture_notes/router.py" in entry["files"]
    _clean(site_maker, made)
    assert "FIXTURE_NOTES_FEED_URL (required)" in out
    assert "-m app.migrations upgrade fixture-notes@head" in out
    assert "-m pytest backend/tests" in out


def test_every_setting_is_in_both_files_after_each_add(site_maker: Path, made: Path) -> None:
    """An apply deletes a variable `railway.ts` doesn't list (decision 0048)."""
    for module_id in ("fixture-notes", "fixture-pins"):
        assert _add(site_maker, made, module_id) == 0
        example = set(dotenv_values(made / settings.ENV))
        assert sorted(example - _railway(made)) == []
        _clean(site_maker, made)


def test_a_module_with_no_migrations_or_web_binding_has_neither_line(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert _add(site_maker, made, "fixture-rival") == 0
    out = capsys.readouterr().out
    assert "app.migrations upgrade" not in out
    assert "Its settings" not in out
    assert "fixtureRival" not in (made / registries.WEB).read_text("utf-8")
    assert '"fixture-rival"' in (made / registries.PYTHON).read_text("utf-8")
    _clean(site_maker, made)


def test_the_registries_list_every_module_in_id_order(site_maker: Path, made: Path) -> None:
    for module_id in ("fixture-rival", "fixture-notes"):
        assert _add(site_maker, made, module_id) == 0
    python = (made / registries.PYTHON).read_text("utf-8")
    assert 'MODULE_IDS: tuple[str, ...] = ("fixture-notes", "fixture-rival")' in python


def _refused(
    root: Path, site: Path, module_id: str, capsys: pytest.CaptureFixture[str], *argv: str
) -> str:
    capsys.readouterr()
    before = tree(site)
    assert _run(root, *(argv or ("add",)), module_id, "--site", str(site)) == 2
    assert tree(site) == before  # nothing written
    return capsys.readouterr().err


def test_add_refuses_a_module_already_there(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _add(site_maker, made, "fixture-notes") == 0
    assert "is in the site already" in _refused(site_maker, made, "fixture-notes", capsys)


def test_add_refuses_a_module_the_checkout_hasnt_built(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = _refused(site_maker, made, "no-such-thing", capsys)
    assert "no module no-such-thing" in err
    assert "fixture-notes" in err  # the ones it has
    assert "isn't built yet" in _refused(site_maker, made, "planned-thing", capsys)
    assert "can't be a module's id" in _refused(site_maker, made, "_later", capsys)


def test_add_refuses_a_missing_requirement_and_names_it(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = _refused(site_maker, made, "fixture-pins", capsys)
    assert "fixture-pins needs fixture-notes ^0.1: run `mechframe add fixture-notes` first." in err


def test_add_refuses_a_conflict_either_way(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _add(site_maker, made, "fixture-notes") == 0
    assert _add(site_maker, made, "fixture-rival") == 0
    assert "conflict" in _refused(site_maker, made, "fixture-pins", capsys)
    assert _remove(site_maker, made, "fixture-rival") == 0
    assert _add(site_maker, made, "fixture-pins") == 0
    # the conflict is pins', so the rival is refused by what the site holds
    assert "fixture-rival and fixture-pins can't be in one site" in _refused(
        site_maker, made, "fixture-rival", capsys
    )


def _manifest(root: Path, module_id: str, **changes: object) -> None:
    path = root / "modules" / module_id / "module.json"
    data = json.loads(path.read_text("utf-8"))
    data.update(changes)
    write(path, json.dumps(data, indent=2) + "\n")


def test_add_refuses_a_version_the_site_doesnt_meet(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _manifest(site_maker, "fixture-notes", requires={"kernel": "^9.0", "modules": {}})
    assert "needs the kernel ^9.0; the site's is 0.1.0-dev.0" in _refused(
        site_maker, made, "fixture-notes", capsys
    )
    _manifest(site_maker, "fixture-notes", requires={"kernel": "^0.1", "modules": {}})
    assert _add(site_maker, made, "fixture-notes") == 0
    _manifest(
        site_maker,
        "fixture-pins",
        requires={"kernel": "^0.1", "modules": {"fixture-notes": "^0.2"}},
    )
    assert "the site has fixture-notes 0.1.0" in _refused(site_maker, made, "fixture-pins", capsys)
    _manifest(
        site_maker, "fixture-pins", requires={"kernel": "^0.1", "modules": {"fixture-notes": "0.x"}}
    )
    assert "isn't a semver range" in _refused(site_maker, made, "fixture-pins", capsys)


def test_add_refuses_a_setting_the_site_sets_already(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    taken = {"name": "SITE_URL", "required": True, "description": "Where the notes link to"}
    _manifest(site_maker, "fixture-rival", env=[taken])
    assert "fixture-rival reads SITE_URL, which the site sets already." in _refused(
        site_maker, made, "fixture-rival", capsys
    )


def test_add_refuses_files_already_where_the_module_goes(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(made / "web/src/modules/fixture-notes/stray.ts", "export {};\n")
    err = _refused(site_maker, made, "fixture-notes", capsys)
    assert (
        "web/src/modules/fixture-notes is in the site, but fixture-notes isn't in its lock" in err
    )


def test_add_refuses_a_manifest_that_doesnt_validate(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _manifest(site_maker, "fixture-rival", status="finished")
    assert "module.json doesn't validate" in _refused(site_maker, made, "fixture-rival", capsys)


def test_add_and_remove_refuse_a_folder_that_isnt_a_site(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "plain").mkdir()
    for command in ("add", "remove"):
        err = _refused(site_maker, tmp_path / "plain", "fixture-notes", capsys, command)
        assert "is this a MechFrame site?" in err


def test_add_refuses_while_another_run_writes(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(made / modules.BUSY, "")
    assert "Another mechframe add or remove" in _refused(site_maker, made, "fixture-notes", capsys)


def test_a_failure_half_way_puts_every_file_back(
    site_maker: Path, made: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = tree(made)

    def broken(*_: object) -> str:
        raise OSError("the disk is full")

    monkeypatch.setattr(registries, "web", broken)
    with pytest.raises(OSError, match="the disk is full"):
        modules.add(made, "fixture-notes", root=site_maker)
    assert tree(made) == before
    assert not (made / "web/src/modules").exists() or not any((made / "web/src/modules").iterdir())


def test_remove_takes_the_code_and_keeps_the_tables_and_the_typed_settings(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _add(site_maker, made, "fixture-notes") == 0
    capsys.readouterr()
    assert _remove(site_maker, made, "fixture-notes") == 0
    out = capsys.readouterr().out
    assert not (made / "backend/modules/fixture_notes").exists()
    assert not (made / "web/src/modules/fixture-notes").exists()
    assert (made / "backend/migrations/fixture-notes/0001_fixture_notes_note.py").is_file()
    assert "fixture-notes" not in (made / registries.PYTHON).read_text("utf-8")
    assert "fixtureNotes" not in (made / registries.WEB).read_text("utf-8")
    assert "fixture-notes" not in lock.read(made, site_maker)["modules"]
    env = dotenv_values(made / settings.ENV)
    assert "FIXTURE_NOTES_FEED_URL" not in env
    assert "# FIXTURE_NOTES_FEED_URL=" in (made / settings.ENV).read_text("utf-8")
    assert {"FIXTURE_NOTES_FEED_URL", "FIXTURE_NOTES_PAGE_SIZE"} <= _railway(made)
    _clean(site_maker, made)
    assert "its tables, in the database" in out
    assert "backend/migrations/fixture-notes/" in out
    assert "preserve()" in out


def test_remove_names_the_files_the_site_had_edited_or_added(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _add(site_maker, made, "fixture-notes") == 0
    write(made / "backend/modules/fixture_notes/router.py", "router = None  # edited\n")
    write(made / "web/src/modules/fixture-notes/extra.ts", "export {};\n")
    capsys.readouterr()
    assert _remove(site_maker, made, "fixture-notes") == 0
    out = capsys.readouterr().out
    assert "Edited here, and gone with it: backend/modules/fixture_notes/router.py" in out
    assert "Added here, and gone with it: web/src/modules/fixture-notes/extra.ts" in out


def test_remove_refuses_while_another_module_needs_it(
    site_maker: Path, made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _add(site_maker, made, "fixture-notes") == 0
    assert _add(site_maker, made, "fixture-pins") == 0
    err = _refused(site_maker, made, "fixture-notes", capsys, "remove")
    assert "fixture-pins needs fixture-notes: remove it first." in err
    assert "isn't in the site" in _refused(site_maker, made, "fixture-rival", capsys, "remove")


def test_a_module_added_again_after_a_remove_is_whole(site_maker: Path, made: Path) -> None:
    assert _add(site_maker, made, "fixture-notes") == 0
    railway = (made / settings.RAILWAY).read_text("utf-8")
    assert _remove(site_maker, made, "fixture-notes") == 0
    assert _add(site_maker, made, "fixture-notes") == 0
    assert dotenv_values(made / settings.ENV)["FIXTURE_NOTES_FEED_URL"] == ""
    assert (made / settings.RAILWAY).read_text("utf-8") == railway  # no line twice
    _clean(site_maker, made)


def test_a_later_version_with_a_new_setting_joins_its_group(made: Path) -> None:
    script = (made / settings.RAILWAY).read_text("utf-8").replace("\r\n", "\n")
    once = settings.railway_with(script, "fixture-notes", ["A_ONE"])
    twice = settings.railway_with(once, "fixture-notes", ["A_ONE", "A_TWO"])
    lines = twice.split("\n")
    at = lines.index("      // fixture-notes")
    assert lines[at + 1 : at + 3] == ["      A_ONE: preserve(),", "      A_TWO: preserve(),"]


def test_a_crlf_site_keeps_its_line_endings(site_maker: Path, made: Path) -> None:
    for relative in (settings.ENV, settings.RAILWAY, registries.PYTHON, registries.WEB):
        path = made / relative
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert _add(site_maker, made, "fixture-notes") == 0
    for relative in (settings.ENV, settings.RAILWAY, registries.PYTHON, registries.WEB):
        data = (made / relative).read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n"), relative


@pytest.mark.parametrize("command", ["add", "remove"])
def test_a_run_holds_the_site_from_its_first_read(
    command: str, site_maker: Path, made: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs that overlap can't both read the old lock (Codex on #94): one
    starting while another reads is refused, so neither writes over the other."""
    if command == "remove":
        assert _add(site_maker, made, "fixture-notes") == 0
    real = modules._lock
    overlapped: list[str] = []

    def overlapping(site: Path, root: Path) -> dict[str, object]:
        if not overlapped:
            overlapped.append(command)
            with pytest.raises(modules.Refused, match="Another mechframe add or remove"):
                modules.add(site, "fixture-rival", root=root)
        return real(site, root)

    monkeypatch.setattr(modules, "_lock", overlapping)
    if command == "add":
        modules.add(made, "fixture-notes", root=site_maker)
    else:
        modules.remove(made, "fixture-notes", root=site_maker)
    assert overlapped == [command]
    assert "fixture-rival" not in lock.read(made, site_maker)["modules"]
    assert not (made / "backend/modules/fixture_rival").exists()
    _clean(site_maker, made)


def test_add_and_remove_refuse_a_site_that_isnt_there(
    site_maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for command in ("add", "remove"):
        err = _refused(site_maker, tmp_path / "nowhere", "fixture-notes", capsys, command)
        assert "isn't a folder: is this a MechFrame site?" in err
    assert not (tmp_path / "nowhere").exists()
