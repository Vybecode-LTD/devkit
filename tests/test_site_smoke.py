"""tools/site_smoke.py: its steps, in order, and a run that stops at the first
failure, keeps the log and names the step. The real run (pip, npm, Chromium)
is CI's E2E workflow and K5's gate: here it runs on stand-in commands."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

from tools import site_smoke
from tools.site_smoke import Step


def test_the_steps_are_the_contracts_in_order(tmp_path: Path) -> None:
    site = tmp_path / "test-site"
    plan = site_smoke.steps(site, npm="npm", migrated="postgresql://u:p@db.test/site_smoke")
    assert [step.name for step in plan] == [
        "venv",
        "pip install --require-hashes",
        "ruff",
        "black",
        "mypy",
        "migrations",
        "pytest",
        "npm ci",
        "eslint",
        "tsc",
        "vitest",
        "vite build",
        "npm ci (Railway's SDK)",
        "railway.ts types",
        "playwright",
        "mechframe check",
    ]
    named = {step.name: step for step in plan}
    python = str(site_smoke.venv_python(site))
    assert named["pip install --require-hashes"].command[0] == python
    assert "--require-hashes" in named["pip install --require-hashes"].command
    assert named["migrations"].env["DATABASE_URL"] == "postgresql://u:p@db.test/site_smoke"
    assert named["pytest"].env["MECHFRAME_REQUIRE_DB"] == "1"
    assert all(named[name].cwd == "web" for name in ("npm ci", "vitest", "playwright"))
    assert named["playwright"].env["E2E_PYTHON"] == python
    assert named["mechframe check"].command[-2:] == ("--site", str(site))
    for name in ("ruff", "mypy", "migrations", "pytest"):
        assert named[name].env["PYTHONPATH"] == "backend"


def test_a_database_url_on_the_same_server() -> None:
    assert (
        site_smoke.database_url("postgresql+asyncpg://u:p@db.test:5432/postgres")
        == "postgresql://u:p@db.test:5432/site_smoke"
    )


def test_a_run_stops_at_the_first_failure_and_logs_each_step(tmp_path: Path) -> None:
    said: list[str] = []
    plan = [
        Step("first", (sys.executable, "-c", "print('one')")),
        Step("second", (sys.executable, "-c", "import sys; print('two'); sys.exit(3)")),
        Step("third", (sys.executable, "-c", "print('three')")),
    ]
    log = tmp_path / "smoke.log"
    assert site_smoke.run(tmp_path, plan, log, say=said.append) == "second"
    text = log.read_text("utf-8")
    assert "one" in text
    assert "two" in text
    assert "=== second: exit 3" in text
    assert "three" not in text
    assert [line.split(" (")[0] for line in said[:2]] == ["ok   first", "FAIL second"]
    # The failed step's own output is shown too, for a log nobody can open (CodeRabbit on #92).
    assert "two" in said[2:]
    assert "one" not in said[2:]


def test_a_command_that_isnt_there_fails_its_step(tmp_path: Path) -> None:
    plan = [Step("missing", (str(tmp_path / "no-such-tool"),))]
    assert site_smoke.run(tmp_path, plan, tmp_path / "smoke.log", say=lambda _: None) == "missing"


def test_a_pass_runs_every_step_with_the_sites_own_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", "this-repos-own")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.test/mine")
    script = "import os; print(os.environ.get('PYTHONPATH'), os.environ.get('DATABASE_URL'))"
    plan = [Step("env", (sys.executable, "-c", script), env={"PYTHONPATH": "backend"})]
    log = tmp_path / "smoke.log"
    assert site_smoke.run(tmp_path, plan, log, say=lambda _: None) is None
    assert "backend None" in log.read_text("utf-8")


@pytest.mark.parametrize("argv", [["--fast"], ["--keep", "--keep"]])
def test_an_unknown_argument_is_refused(argv: list[str]) -> None:
    assert site_smoke.main(argv) == 2


def test_it_needs_a_database_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert site_smoke.main([]) == 2
    assert "TEST_DATABASE_URL" in capsys.readouterr().err


async def test_a_fresh_database_is_made_again_each_run(server_url: str) -> None:
    import asyncpg

    name = f"site_smoke_{uuid.uuid4().hex[:8]}"
    first = await site_smoke.fresh_database(server_url, name)
    connection = await asyncpg.connect(first)
    await connection.execute("CREATE TABLE left_over (id int)")
    await connection.close()
    again = await site_smoke.fresh_database(server_url, name)  # dropped and made again
    connection = await asyncpg.connect(again)
    try:
        assert await connection.fetchval("SELECT to_regclass('left_over')") is None
    finally:
        await connection.close()
    admin = await asyncpg.connect(server_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await admin.close()


def test_make_writes_a_kernel_only_site(tmp_path: Path) -> None:
    site = tmp_path / "test-site"
    site_smoke.make(site)
    lock = json.loads((site / "mechframe.lock.json").read_text("utf-8"))
    assert lock["modules"] == {}
    assert (site / "backend" / "app" / "main.py").is_file()


class Faked:
    """`main` with its slow parts stood in for: the folder, the site, the database and the run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, folder: Path, failed: str | None) -> None:
        self.folder = folder
        self.planned: list[Step] = []
        monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@db.test/postgres")
        monkeypatch.setattr(site_smoke.shutil, "which", lambda _name: "npm")
        monkeypatch.setattr(site_smoke.tempfile, "mkdtemp", self.mkdtemp)
        monkeypatch.setattr(site_smoke, "make", lambda site: site.mkdir(parents=True))

        async def fresh(admin_url: str) -> str:
            return site_smoke.database_url(admin_url)

        def run(site: Path, plan: list[Step], log: Path) -> str | None:
            self.planned = list(plan)
            log.write_text("the steps' output\n", "utf-8")
            return failed

        monkeypatch.setattr(site_smoke, "fresh_database", fresh)
        monkeypatch.setattr(site_smoke, "run", run)

    def mkdtemp(self, prefix: str) -> str:
        self.folder.mkdir()
        return str(self.folder)


def test_a_pass_removes_the_folder_unless_it_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    faked = Faked(monkeypatch, tmp_path / "smoke", failed=None)
    assert site_smoke.main([]) == 0
    assert not faked.folder.exists()
    assert "Every step passed" in capsys.readouterr().out
    assert faked.planned[-1].name == "mechframe check"
    kept = Faked(monkeypatch, tmp_path / "kept", failed=None)
    assert site_smoke.main(["--keep"]) == 0
    assert (kept.folder / "test-site").is_dir()
    assert f"The site is in {kept.folder / 'test-site'}" in capsys.readouterr().out


def test_a_failure_keeps_the_folder_and_names_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    faked = Faked(monkeypatch, tmp_path / "smoke", failed="pytest")
    assert site_smoke.main([]) == 1
    out = capsys.readouterr().out
    assert "The site's pytest step failed" in out
    assert str(faked.folder / "smoke.log") in out
    assert (faked.folder / "smoke.log").is_file()


def test_it_needs_npm(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@db.test/postgres")
    monkeypatch.setattr(site_smoke.shutil, "which", lambda _name: None)
    assert site_smoke.main([]) == 2
    assert "npm isn't on the path" in capsys.readouterr().err


def test_the_venvs_python_on_each_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(site_smoke.sys, "platform", "linux")
    assert site_smoke.venv_python(tmp_path) == tmp_path / ".venv" / "bin" / "python"
    monkeypatch.setattr(site_smoke.sys, "platform", "win32")
    assert site_smoke.venv_python(tmp_path) == tmp_path / ".venv" / "Scripts" / "python.exe"


def test_a_kernel_only_site_with_modules_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mechframe import new

    made = new.Made(tmp_path, "Test Site", "machined-light", {"modules": {"shop": {}}})
    monkeypatch.setattr(new, "new", lambda *_args, **_kwargs: made)
    with pytest.raises(RuntimeError, match="came out with modules"):
        site_smoke.make(tmp_path / "test-site")


def test_a_failure_without_a_last_newline_shows_only_its_own_output(tmp_path: Path) -> None:
    """Output that doesn't end its last line still ends before the exit marker
    (CodeRabbit on #92)."""
    said: list[str] = []
    plan = [
        Step("first", (sys.executable, "-c", "print('earlier output')")),
        Step(
            "second",
            (sys.executable, "-c", "import sys; sys.stdout.write('no newline'); sys.exit(1)"),
        ),
    ]
    assert site_smoke.run(tmp_path, plan, tmp_path / "smoke.log", say=said.append) == "second"
    assert said[2:] == ["no newline"]
