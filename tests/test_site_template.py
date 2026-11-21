"""The site template (K5 contract §2, §4 item 2 and §7): a site `mechframe new`
makes from `templates/site/` holds every file the contract lists, its web
dependencies are MechFrame's, it deploys behind Railway's proxy with a real
client address, and its own Python tests and lint pass. With the CLI's
fixture modules added (`mechframe add`, the K5 contract §4 item 4), its
registries import and build, every setting is in `.railway/railway.ts`, its
tests pass again and `mechframe check` is clean.

The site's tests run here in a subprocess, with this repo's Python (the
site's pins are this repo's), so every pull request runs them; the database
tests among them need TEST_DATABASE_URL's server, as this repo's do.
`tools/site_smoke.py` goes further: a venv of the site's own, `npm ci`, the
build, Vitest, Playwright and `mechframe check` (main's pushes and weekly).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values

from mechframe import check, lock, modules, settings
from mechframe.__main__ import main

ROOT = Path(__file__).resolve().parents[1]

#: Every path the contract's table names, and the files the template adds to them.
PATHS = [
    "mechframe.lock.json",
    "backend/app/__init__.py",
    "backend/app/main.py",
    "backend/app/modules.py",
    "backend/app/migrations.py",
    "backend/app/worker.py",
    "backend/app/owner.py",
    "backend/app/seed.py",
    "backend/app/site/__init__.py",
    "backend/app/site/pages.py",
    "backend/app/site/seed.py",
    "backend/alembic/env.py",
    "backend/alembic/script.py.mako",
    "backend/kernel/__init__.py",
    "backend/kernel/kernel.json",
    "backend/migrations/kernel/0001_kernel_core.py",
    "backend/modules/README.md",
    "backend/tests/conftest.py",
    "backend/tests/test_app.py",
    "backend/tests/test_migrations.py",
    "backend/tests/test_pages.py",
    "backend/tests/test_seed.py",
    "backend/tests/e2e_server.py",
    "web/src/kernel/index.ts",
    "web/src/modules.ts",
    "web/src/main.tsx",
    "web/src/theme/tokens.css",
    "web/src/site/site.ts",
    "web/src/site/Home.tsx",
    "web/src/site/Home.test.tsx",
    "web/index.html",
    "web/package.json",
    "web/package-lock.json",
    "web/.npmrc",
    "web/vite.config.ts",
    "web/vitest.setup.ts",
    "web/tsconfig.json",
    "web/eslint.config.js",
    "web/playwright.config.ts",
    "web/e2e/smoke.spec.ts",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
    "requirements-dev.in",
    "pyproject.toml",
    ".env.example",
    ".railway/railway.ts",
    ".railway/tsconfig.json",
    "package.json",
    "package-lock.json",
    ".npmrc",
    "Dockerfile",
    ".dockerignore",
    "compose.yaml",
    ".gitignore",
    ".gitattributes",
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    ".github/workflows/ci.yml",
]


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("made") / "test-site"
    assert main(["new", str(folder), "--name", "Test Site"]) == 0
    return folder


def _json(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text("utf-8"))
    return data


def test_every_file_the_contract_lists_is_there(site: Path) -> None:
    missing = [path for path in PATHS if not (site / path).is_file()]
    assert missing == []


def test_the_new_site_checks_clean(site: Path) -> None:
    report = check.check(site)
    assert report.problems == []
    assert (report.edited, report.missing, report.added, report.behind) == ([], [], [], [])
    assert report.exit_code() == 0
    assert lock.read(site)["modules"] == {}


def test_the_web_dependencies_are_mechframes(site: Path) -> None:
    root = _json(ROOT / "package.json")
    web = _json(site / "web" / "package.json")
    for key in ("dependencies", "devDependencies", "overrides", "engines"):
        assert web[key] == root[key], key
    template = _json(ROOT / "templates" / "site" / "web" / "package.json")
    assert template == web


def test_the_web_lockfile_holds_the_same_versions(site: Path) -> None:
    """`npm ci` installs the lockfile, so its direct dependencies must be the
    package's, at the versions MechFrame's own lockfile resolves."""
    web = _json(site / "web" / "package.json")
    made = _json(site / "web" / "package-lock.json")["packages"]
    ours = _json(ROOT / "package-lock.json")["packages"]
    assert isinstance(made, dict)
    assert isinstance(ours, dict)
    top = made[""]
    assert top["dependencies"] == web["dependencies"]
    assert top["devDependencies"] == web["devDependencies"]
    for group in ("dependencies", "devDependencies"):
        names = web[group]
        assert isinstance(names, dict)
        for name in names:
            key = f"node_modules/{name}"
            assert made[key]["version"] == ours[key]["version"], name


def test_the_python_pins_are_mechframes(site: Path) -> None:
    for name in (
        "requirements.txt",
        "requirements-dev.txt",
        "requirements.in",
        "requirements-dev.in",
    ):
        assert (site / name).read_bytes() == (ROOT / name).read_bytes(), name


def test_the_environment_names_every_setting_and_a_real_client_address(site: Path) -> None:
    values = dotenv_values(site / ".env.example")
    assert values["SITE_NAME"] == "Test Site"
    assert values["CLIENT_IP_HEADER"] == "X-Real-IP"
    assert values["FORWARDED_ALLOW_IPS"] == "127.0.0.1"
    assert values["DEBUG"] == "false"
    harness = dotenv_values(ROOT / ".env.example")
    assert sorted(set(harness) - set(values)) == []


def test_the_start_command_reads_the_proxys_headers(site: Path) -> None:
    dockerfile = (site / "Dockerfile").read_text("utf-8")
    (command,) = [line for line in dockerfile.splitlines() if line.startswith("CMD")]
    for part in (
        "python -m uvicorn app.main:app",
        "--host 0.0.0.0",
        "--port ${PORT",
        "--proxy-headers",
        "--forwarded-allow-ips",
        "${FORWARDED_ALLOW_IPS",
    ):
        assert part in command, part
    assert "WEB_DIST=/app/web/dist" in dockerfile
    assert "PYTHONPATH=/app/backend" in dockerfile
    assert "--require-hashes" in dockerfile
    assert "npm ci" in dockerfile


def _railway_env(script: str) -> dict[str, str]:
    """`.railway/railway.ts`'s variables, each as written after its colon."""
    block = script[script.index("env: {") : script.index("},", script.index("env: {"))]
    return dict(re.findall(r"^\s+([A-Z][A-Z0-9_]*): (.+?),\s*$", block, re.MULTILINE))


def test_railway_builds_the_dockerfile_migrates_first_and_trusts_its_edge(site: Path) -> None:
    """Railway's infrastructure as code (decision 0048; the owner, 2026-11-20): the
    Dockerfile builder, migrations before each deploy, the health check, the
    edge's headers trusted, the database referenced, and no secret written."""
    script = (site / ".railway" / "railway.ts").read_text("utf-8")
    assert 'from "railway/iac"' in script
    assert 'export const partial = "web";' in script
    for setting in (
        'build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" }',
        'preDeploy: "python -m app.migrations upgrade"',
        'healthcheck: "/api/kernel/health"',
    ):
        assert setting in script, setting
    env = _railway_env(script)
    assert env["DATABASE_URL"] == "db.env.DATABASE_URL"
    assert env["FORWARDED_ALLOW_IPS"] == '"*"'
    assert env["CLIENT_IP_HEADER"] == '"X-Real-IP"'
    assert env["DEBUG"] == '"false"'
    assert env["SITE_NAME"] == '"Test Site"'
    for secret in ("SECRET_KEY", "ENCRYPTION_KEYS", "SMTP_PASSWORD", "STORAGE_SECRET_ACCESS_KEY"):
        assert env[secret] == "preserve()", secret
    assert not (site / "railway.toml").exists()


def test_railway_lists_every_setting_so_an_apply_deletes_none(site: Path) -> None:
    """An apply deletes a variable on the service that the file doesn't list
    (seen on a throwaway project, 2026-11-20): every setting the kernel reads
    is in railway.ts and in .env.example (CodeRabbit on #92)."""
    from kernel.config import KernelConfig

    env = _railway_env((site / ".railway" / "railway.ts").read_text("utf-8"))
    example = set(dotenv_values(site / ".env.example"))
    kernel = {(field.alias or name).upper() for name, field in KernelConfig.model_fields.items()}
    assert sorted(kernel - set(env)) == []
    assert sorted(kernel - example) == []
    assert sorted(example - set(env)) == []


#: Seeding's permission (hook 4, decision 0052): the process's environment only.
ALLOW_SEED = "MECHFRAME_ALLOW_SEED"


def test_railway_never_allows_seeding(site: Path) -> None:
    """Seed data never reaches a live site: no file of the site's sets the
    permission, so it's only ever typed for one run (decision 0052, hook 4)."""
    for path in (".railway/railway.ts", ".env.example", "Dockerfile", "compose.yaml"):
        assert ALLOW_SEED not in (site / path).read_text("utf-8"), path


def test_railways_sdk_is_pinned_and_locked(site: Path) -> None:
    package = _json(site / "package.json")
    assert package["devDependencies"] == {"railway": "3.16.0"}
    locked = _json(site / "package-lock.json")["packages"]
    assert isinstance(locked, dict)
    assert locked["node_modules/railway"]["version"] == "3.16.0"
    assert (site / ".npmrc").read_text("utf-8") == (ROOT / ".npmrc").read_text("utf-8")


def test_the_sites_ci_checks_it_against_a_shallow_clone(site: Path) -> None:
    workflow = (site / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    assert "git clone --depth 1 https://github.com/mechframe/mechframe" in workflow
    assert "-m mechframe check --site ." in workflow
    assert "npm ci" in workflow
    assert "--require-hashes" in workflow
    ours = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    pinned = re.compile(r"uses: ([\w./-]+)@([0-9a-f]{40})")
    shas = dict(pinned.findall(ours))
    used = pinned.findall(workflow)
    assert used
    for action, sha in used:
        assert shas.get(action) == sha, action
    assert "uses: " not in pinned.sub("", workflow)  # every action pinned to a commit


def test_the_agents_files_hold_the_same_rules(site: Path) -> None:
    claude = (site / "CLAUDE.md").read_text("utf-8")
    agents = (site / "AGENTS.md").read_text("utf-8")
    assert claude.replace("CLAUDE.md", "AGENTS.md") == agents.replace("CLAUDE.md", "AGENTS.md")
    assert "Test Site" in claude
    assert "mechframe check" in claude


def test_the_kernel_resolves_as_at_mechframe(site: Path) -> None:
    for name in ("vite.config.ts", "tsconfig.json"):
        assert "src/kernel/index.ts" in (site / "web" / name).read_text("utf-8"), name
    main_tsx = (site / "web" / "src" / "main.tsx").read_text("utf-8")
    assert main_tsx.index('import "./theme/tokens.css"') < main_tsx.index("mountApp")
    assert 'data-theme="machined-light"' in (site / "web" / "index.html").read_text("utf-8")


def _run(
    site: Path, *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONPATH"] = "backend"
    env.update(env_extra or {})
    return subprocess.run(  # noqa: S603 (this repo's own Python, on a site it just made)
        [sys.executable, *args],
        cwd=site,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def test_the_sites_python_is_linted_clean(site: Path) -> None:
    for command in (
        ("-m", "ruff", "check", "backend/app", "backend/tests", "backend/alembic"),
        ("-m", "black", "--check", "backend/app", "backend/tests", "backend/alembic"),
    ):
        found = _run(site, *command)
        assert found.returncode == 0, found.stdout + found.stderr


def test_the_sites_own_python_tests_pass(site: Path) -> None:
    found = _run(site, "-m", "pytest", "-q", "-p", "no:cacheprovider", "backend/tests")
    assert found.returncode == 0, found.stdout[-4000:] + found.stderr[-2000:]
    if os.environ.get("MECHFRAME_REQUIRE_DB") == "1":
        assert " skipped" not in found.stdout, found.stdout[-2000:]


#: The fixture modules a site gets added, each after what it requires.
FIXTURE_MODULES = ("fixture-notes", "fixture-pins")


@pytest.fixture(scope="module")
def site_with_modules(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A new site with the CLI's fixture modules added, from a checkout of this
    one's schemas and the fixtures as its modules (no real module is built yet)."""
    root = tmp_path_factory.mktemp("fixture-checkout") / "mechframe"
    shutil.copytree(ROOT / "schema", root / "schema")
    shutil.copytree(ROOT / "cli" / "tests" / "fixtures" / "modules", root / "modules")
    folder = tmp_path_factory.mktemp("made") / "with-modules"
    assert main(["new", str(folder), "--name", "Test Site"]) == 0
    for module_id in FIXTURE_MODULES:
        modules.add(folder, module_id, root=root)
    return folder


def test_a_site_with_modules_lists_every_setting_for_railway(site_with_modules: Path) -> None:
    env = _railway_env((site_with_modules / settings.RAILWAY).read_text("utf-8"))
    example = set(dotenv_values(site_with_modules / settings.ENV))
    assert {"FIXTURE_NOTES_FEED_URL", "FIXTURE_PINS_LIMIT"} <= example
    assert sorted(example - set(env)) == []
    for name in ("FIXTURE_NOTES_FEED_URL", "FIXTURE_NOTES_PAGE_SIZE", "FIXTURE_PINS_LIMIT"):
        assert env[name] == "preserve()", name
    assert ALLOW_SEED not in (site_with_modules / settings.RAILWAY).read_text("utf-8")


def test_a_site_with_modules_imports_each_binding_it_lists(site_with_modules: Path) -> None:
    web = (site_with_modules / "web" / "src" / "modules.ts").read_text("utf-8")
    imported = re.findall(r'from "\./(modules/[a-z0-9-]+/module\.web)";', web)
    assert imported == ["modules/fixture-notes/module.web", "modules/fixture-pins/module.web"]
    for path in imported:
        assert (site_with_modules / "web" / "src" / f"{path}.ts").is_file(), path


def test_a_site_with_modules_checks_clean(site_with_modules: Path) -> None:
    report = check.check(site_with_modules, root=ROOT)
    assert report.exit_code() == 0, report.lines()
    assert (report.edited, report.missing, report.added) == ([], [], [])
    assert report.unknown == list(FIXTURE_MODULES)  # not this checkout's modules


def test_a_site_with_modules_is_linted_clean_and_passes_its_tests(site_with_modules: Path) -> None:
    """The registries `add` wrote import, the app builds with the modules, and
    their migration round-trips with the kernel's (the site's own tests)."""
    for command in (
        ("-m", "ruff", "check", "backend"),
        ("-m", "black", "--check", "backend"),
    ):
        found = _run(site_with_modules, *command)
        assert found.returncode == 0, found.stdout + found.stderr
    found = _run(site_with_modules, "-m", "pytest", "-q", "-p", "no:cacheprovider", "backend/tests")
    assert found.returncode == 0, found.stdout[-4000:] + found.stderr[-2000:]
    if os.environ.get("MECHFRAME_REQUIRE_DB") == "1":
        assert " skipped" not in found.stdout, found.stdout[-2000:]


async def _jobs_named(url: str, name: str) -> int:
    import asyncpg

    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        found: int = await connection.fetchval(
            "SELECT count(*) FROM kernel_job WHERE name = $1", name
        )
    finally:
        await connection.close()
    return found


async def test_the_owner_made_from_the_server_reaches_the_modules_listeners(
    site_with_modules: Path, empty_database_url: str
) -> None:
    """`python -m app.owner` builds the site as its app does, so a module that
    listens for a new account gets its delivery (Codex on #95): deliveries are
    written when the event is, and nothing else would queue this one."""
    settings = {"DATABASE_URL": empty_database_url, "SITE_URL": "https://site.test"}
    migrated = _run(site_with_modules, "-m", "app.migrations", "upgrade", env_extra=settings)
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    made = _run(site_with_modules, "-m", "app.owner", "owner@site.test", env_extra=settings)
    assert made.returncode == 0, made.stdout + made.stderr
    assert "https://site.test/auth/reset?token=" in made.stdout
    assert await _jobs_named(empty_database_url, "fixture-notes.greet_account") == 1
