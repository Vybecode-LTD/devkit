"""A new site, made and run from nothing (K5 contract §4 item 2 and §7; KICKOFF K5's gate).

    python -m tools.site_smoke            with TEST_DATABASE_URL set, npm on the path
    python -m tools.site_smoke --keep     keep the site's folder after a pass too

It makes `test-site` with `mechframe new` (kernel only) in a temporary
folder, then, in that folder and with its own environment, as an agent would:

1. a venv, and `pip install --require-hashes` from the site's pins;
2. the site's Python lint, format and types;
3. its migrations, on a database of its own on TEST_DATABASE_URL's server;
4. its Python tests, the database ones required (MECHFRAME_REQUIRE_DB=1);
5. `npm ci`, then its web lint, types, Vitest and the build, and
   `.railway/railway.ts` held to Railway's SDK's types;
6. its Playwright tests (`npm run e2e`: Chromium, axe), against its own server;
7. `mechframe check`, which must exit 0.

Each step's output goes to `smoke.log` in the folder, and the run stops at the
first step that fails, keeping the folder and naming the log. It needs the
network for pip and npm, so it runs where the owner said: CI's E2E workflow
(main's pushes, weekly, by hand), never a pull request; and locally before K5's
gate. It passes only when every step ran and exited 0 (verify-real-pass).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
SITE_NAME = "Test Site"
DATABASE = "site_smoke"
#: How much of a failed step's output is shown.
TAIL = 80


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    #: Relative to the site's folder.
    cwd: str = "."
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 900


def venv_python(site: Path) -> Path:
    if sys.platform == "win32":
        return site / ".venv" / "Scripts" / "python.exe"
    return site / ".venv" / "bin" / "python"


def database_url(admin_url: str, name: str = DATABASE) -> str:
    """`admin_url`'s server, database `name`, as asyncpg and the kernel take it."""
    plain = admin_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return urlunsplit(urlsplit(plain)._replace(path=f"/{name}"))


async def fresh_database(admin_url: str, name: str = DATABASE) -> str:
    """The database `name` on `admin_url`'s server, dropped and made again."""
    import asyncpg

    admin = await asyncpg.connect(
        admin_url.replace("postgresql+asyncpg://", "postgresql://", 1), timeout=5
    )
    try:
        await admin.execute(
            "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity"
            " WHERE datname = $1 AND usename = current_user AND pid <> pg_backend_pid()",
            name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    return database_url(admin_url, name)


def steps(site: Path, *, npm: str, migrated: str) -> list[Step]:
    """Every step after `mechframe new`, in order."""
    python = str(venv_python(site))
    backend = {"PYTHONPATH": "backend"}
    return [
        Step("venv", (sys.executable, "-m", "venv", ".venv")),
        Step(
            "pip install --require-hashes",
            (
                python,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--require-hashes",
                "--only-binary=:all:",
                "-r",
                "requirements.txt",
                "-r",
                "requirements-dev.txt",
            ),
        ),
        Step("ruff", (python, "-m", "ruff", "check", "."), env=backend),
        Step("black", (python, "-m", "black", "--check", "."), env=backend),
        Step("mypy", (python, "-m", "mypy"), env=backend),
        Step(
            "migrations",
            (python, "-m", "app.migrations", "upgrade"),
            env={**backend, "DATABASE_URL": migrated},
        ),
        Step(
            "pytest",
            (python, "-m", "pytest", "-p", "no:cacheprovider"),
            env={**backend, "MECHFRAME_REQUIRE_DB": "1"},
        ),
        Step("npm ci", (npm, "ci", "--no-audit", "--no-fund"), cwd="web"),
        Step("eslint", (npm, "run", "lint"), cwd="web"),
        Step("tsc", (npm, "run", "typecheck"), cwd="web"),
        Step("vitest", (npm, "test"), cwd="web"),
        Step("vite build", (npm, "run", "build"), cwd="web"),
        Step("npm ci (Railway's SDK)", (npm, "ci", "--no-audit", "--no-fund")),
        Step(
            "railway.ts types",
            ("node", "web/node_modules/typescript/bin/tsc", "-p", ".railway/tsconfig.json"),
        ),
        Step(
            "playwright", (npm, "run", "e2e"), cwd="web", env={"E2E_PYTHON": python, "CI": "true"}
        ),
        Step(
            "mechframe check",
            (sys.executable, "-m", "mechframe", "check", "--site", str(site)),
            env={"PYTHONPATH": str(ROOT / "cli")},
        ),
    ]


def _environment(extra: dict[str, str]) -> dict[str, str]:
    """This process's environment for a step, without this repo's own paths
    and settings, so the site runs on what it has."""
    left_out = {"PYTHONPATH", "VIRTUAL_ENV", "DATABASE_URL", "MECHFRAME_REQUIRE_DB", "E2E_PORT"}
    found = {key: value for key, value in os.environ.items() if key.upper() not in left_out}
    found.update(extra)
    return found


def run(
    site: Path,
    plan: Sequence[Step],
    log: Path,
    say: Callable[[str], None] = print,
) -> str | None:
    """Run `plan` in `site`, every output into `log`. The first step that fails,
    or None when every one passed."""
    with log.open("a", encoding="utf-8") as out:
        for step in plan:
            started = time.monotonic()
            out.write(f"\n=== {step.name}: {' '.join(step.command)} (in {step.cwd})\n")
            out.flush()
            try:
                finished = subprocess.run(  # noqa: S603 (the site's own tools, in its folder)
                    step.command,
                    cwd=site / step.cwd,
                    env=_environment(step.env),
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    timeout=step.timeout,
                    check=False,
                )
                code: int | str = finished.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                code = type(error).__name__
            took = time.monotonic() - started
            # On a line of its own, whether or not the output ended its last (CodeRabbit on #92).
            out.write(f"\n=== {step.name}: exit {code} after {took:.0f} s\n")
            out.flush()
            say(f"{'ok  ' if code == 0 else 'FAIL'} {step.name} ({took:.0f} s)")
            if code != 0:
                for line in _tail(log, step.name):
                    say(line)
                return step.name
    return None


def _tail(log: Path, name: str, lines: int = TAIL) -> list[str]:
    """The last `lines` lines of step `name`'s output in `log`. A runner's
    folder is gone once its job ends, so a failure shows them (CodeRabbit on #92)."""
    text = log.read_text("utf-8", errors="replace")
    end = text.rfind(f"\n=== {name}: exit ")
    start = text.rfind(f"\n=== {name}: ", 0, end)
    body = text[text.index("\n", start + 1) + 1 : end] if 0 <= start < end else text
    return body.splitlines()[-lines:]


def make(site: Path) -> None:
    """`mechframe new` for the site, as an agent runs it."""
    from mechframe import new

    made = new.new(site, name=SITE_NAME)
    if made.lock["modules"]:
        raise RuntimeError("A kernel-only site came out with modules.")


def main(argv: list[str]) -> int:
    if argv not in ([], ["--keep"]):
        print("usage: python -m tools.site_smoke [--keep]")
        return 2
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        print("Set TEST_DATABASE_URL to a Postgres server's admin URL.", file=sys.stderr)
        return 2
    npm = shutil.which("npm")
    if npm is None:
        print("npm isn't on the path: the site's web app needs it.", file=sys.stderr)
        return 2
    folder = Path(tempfile.mkdtemp(prefix="mechframe-smoke-"))
    site = folder / "test-site"
    log = folder / "smoke.log"
    print(f"Making {SITE_NAME} in {site}")
    make(site)
    migrated = asyncio.run(fresh_database(admin_url))
    failed = run(site, steps(site, npm=npm, migrated=migrated), log)
    if failed is not None:
        print(f"The site's {failed} step failed: its output is in {log}, the site in {site}.")
        return 1
    print(
        "Every step passed: the new site installs, builds, migrates, passes its tests and checks clean."
    )
    if argv == ["--keep"]:
        print(f"The site is in {site}.")
    else:
        shutil.rmtree(folder, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "cli"))
    sys.exit(main(sys.argv[1:]))
