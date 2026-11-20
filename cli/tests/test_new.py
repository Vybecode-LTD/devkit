"""`mechframe new <dir>` (K5 contract §2 and §4 item 2): a kernel-only site from
`templates/site/`, the kernel, a theme and the lock."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from dotenv import dotenv_values

from mechframe import check, lock, new, source
from mechframe.__main__ import main
from mechframe.hashes import digest

from .conftest import write

REQUIREMENTS = (
    "requirements.in",
    "requirements.txt",
    "requirements-dev.in",
    "requirements-dev.txt",
)


@pytest.fixture
def maker(checkout: Path) -> Path:
    """The checkout with a small site template, two themes and its pins."""
    template = checkout / "templates" / "site"
    write(template / "README.md", "# __SITE_NAME__\n\nMade with MechFrame.\n")
    write(template / "CLAUDE.md", "# CLAUDE.md: __SITE_NAME__\n")
    write(
        template / ".env.example",
        "DEBUG=false\nSITE_NAME=__SITE_NAME__\nCLIENT_IP_HEADER=X-Real-IP\n",
    )
    write(template / "backend" / "app" / "main.py", "app = None\n")
    write(template / "backend" / "app" / "__pycache__" / "main.cpython-312.pyc", "junk")
    write(template / "web" / "index.html", '<html data-theme="__THEME__"></html>\n')
    write(template / ".railway" / "railway.ts", 'const name = "__SITE_NAME__";\n')
    write(template / "web" / "node_modules" / "react" / "index.js", "junk\n")
    write(template / "web" / "dist" / "index.html", "junk\n")
    write(template / ".venv" / "pyvenv.cfg", "junk\n")
    (template / "web" / "logo.png").parent.mkdir(parents=True, exist_ok=True)
    (template / "web" / "logo.png").write_bytes(bytes([137, 80, 78, 71, 0, 255, 254]))
    for theme in ("machined-light", "vibrant-mindz"):
        write(checkout / "themes" / theme / "tokens.css", f'[data-theme="{theme}"] {{}}\n')
        write(checkout / "themes" / theme / "tokens.json", "{}\n")
    for name in REQUIREMENTS:
        write(checkout / name, f"# {name}, pinned\n")
    return checkout


def _new(maker: Path, folder: Path, *extra: str) -> int:
    return main(["new", str(folder), "--root", str(maker), *extra])


def test_a_new_site_holds_the_template_the_kernel_and_its_lock(
    maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "test-site"
    assert _new(maker, folder, "--name", "Test Site") == 0
    data = lock.read(folder, root=maker)
    assert data["modules"] == {}
    assert data["recipe"] is None
    assert data["theme"] == "machined-light"
    assert data["mechframe"] == "0.1.0"
    assert data["kernel"]["version"] == source.kernel_manifest(maker)["version"]
    assert data["spec"] == source.kernel_manifest(maker)["spec"]
    assert sorted(data["kernel"]["files"]) == [
        "backend/kernel/__init__.py",
        "backend/kernel/auth/sessions.py",
        "backend/kernel/kernel.json",
        "backend/migrations/kernel/kernel_0001.py",
        "web/src/kernel/index.ts",
        "web/src/kernel/src/app/mount.ts",
    ]
    for path, recorded in data["kernel"]["files"].items():
        assert digest(folder / path) == recorded
    report = check.check(folder, root=maker)
    assert (report.exit_code(), report.edited, report.missing, report.added) == (0, [], [], [])
    out = capsys.readouterr().out
    assert "Made Test Site in" in out
    assert "-m app.migrations upgrade" in out
    assert "npm ci" in out


def test_the_template_is_copied_without_its_build_output(maker: Path, tmp_path: Path) -> None:
    folder = tmp_path / "site"
    assert _new(maker, folder) == 0
    assert (folder / "backend" / "app" / "main.py").read_text("utf-8") == "app = None\n"
    assert (folder / "web" / "logo.png").read_bytes() == bytes([137, 80, 78, 71, 0, 255, 254])
    for left in ("web/node_modules", "web/dist", ".venv", "backend/app/__pycache__"):
        assert not (folder / left).exists(), left
    for name in REQUIREMENTS:
        assert (folder / name).read_bytes() == (maker / name).read_bytes()


def test_the_name_and_the_theme_are_written_in(maker: Path, tmp_path: Path) -> None:
    folder = tmp_path / "site"
    name = 'The "Corner" Shop \\ Co'
    assert _new(maker, folder, "--name", name, "--theme", "vibrant-mindz") == 0
    assert dotenv_values(folder / ".env.example")["SITE_NAME"] == name
    assert (folder / "README.md").read_text("utf-8").startswith(f"# {name}\n")
    assert (folder / "web" / "index.html").read_text("utf-8") == (
        '<html data-theme="vibrant-mindz"></html>\n'
    )
    assert (folder / "web" / "src" / "theme" / "tokens.css").read_bytes() == (
        maker / "themes" / "vibrant-mindz" / "tokens.css"
    ).read_bytes()
    assert lock.read(folder, root=maker)["theme"] == "vibrant-mindz"
    script = (folder / ".railway" / "railway.ts").read_text("utf-8")
    assert json.loads(script.split(" = ", 1)[1].rstrip(";\n")) == name
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix != ".png":
            text = path.read_text("utf-8")
            assert "__SITE_NAME__" not in text, path
            assert "__THEME__" not in text, path


def test_the_name_defaults_to_the_folders(maker: Path, tmp_path: Path) -> None:
    folder = tmp_path / "corner-shop"
    assert _new(maker, folder) == 0
    assert dotenv_values(folder / ".env.example")["SITE_NAME"] == "corner-shop"


def test_an_empty_folder_may_be_the_site(maker: Path, tmp_path: Path) -> None:
    folder = tmp_path / "ready"
    folder.mkdir()
    assert _new(maker, folder) == 0
    assert (folder / lock.NAME).is_file()


def test_a_folder_that_isnt_empty_is_refused_and_left_alone(
    maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "taken"
    write(folder / "notes.txt", "mine\n")
    assert _new(maker, folder) == 2
    assert "isn't empty" in capsys.readouterr().err
    assert [path.name for path in folder.iterdir()] == ["notes.txt"]
    afile = tmp_path / "a-file"
    afile.write_text("x", "utf-8")
    assert _new(maker, afile) == 2
    assert afile.read_text("utf-8") == "x"


def test_an_unknown_theme_is_refused_and_nothing_is_written(
    maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "site"
    assert _new(maker, folder, "--theme", "neon") == 2
    err = capsys.readouterr().err
    assert "There's no theme neon" in err
    assert "machined-light, vibrant-mindz" in err
    assert not folder.exists()


@pytest.mark.parametrize("name", ["", "   ", "Two\nlines", "Tab\there", "x" * 101])
def test_a_name_that_cant_be_a_sites_is_refused(
    maker: Path, tmp_path: Path, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "site"
    assert _new(maker, folder, "--name", name) == 2
    assert "site's name" in capsys.readouterr().err
    assert not folder.exists()


def test_the_site_is_made_in_one_go_or_not_at_all(
    maker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A copy that fails half-way leaves no half-made site behind."""

    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("the disk is full")

    monkeypatch.setattr(lock, "write", broken)
    folder = tmp_path / "site"
    with pytest.raises(OSError, match="the disk is full"):
        new.new(folder, name="Site", theme="machined-light", root=maker)
    assert not folder.exists()
    ready = tmp_path / "ready"
    ready.mkdir()
    with pytest.raises(OSError, match="the disk is full"):
        new.new(ready, name="Site", theme="machined-light", root=maker)
    assert ready.is_dir()
    assert list(ready.iterdir()) == []


def test_a_checkout_without_the_template_or_themes_is_refused(
    maker: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.rmtree(maker / "templates")
    assert _new(maker, tmp_path / "one") == 2
    assert "This checkout has no templates/site/." in capsys.readouterr().err
    shutil.rmtree(maker / "themes")
    assert new.themes(maker) == []
    assert _new(maker, tmp_path / "two") == 2
    assert "The themes: none." in capsys.readouterr().err
