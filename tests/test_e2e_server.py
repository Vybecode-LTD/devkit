"""harness.e2e, the server Playwright runs against, and the workflows that run
it: a database of its own made fresh each start with the site's description,
the refusals before anything starts, CI's lint and types for the Playwright
files, and e2e.yml never on a pull request (the owner, 2026-11-18)."""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import asyncpg
import pytest

from harness import e2e
from harness.migrations import upgrade
from kernel import server_copy
from kernel.db import Database
from kernel.settings import settings

ROOT = Path(__file__).resolve().parents[1]

#: The settings a half setup in .env would trip over.
MAIL_AND_STORAGE = (
    "MAIL_FROM",
    "MAIL_FROM_NAME",
    "SMTP_HOST",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "RESEND_API_KEY",
    "STORAGE_ENDPOINT_URL",
    "STORAGE_ACCESS_KEY_ID",
    "STORAGE_SECRET_ACCESS_KEY",
    "STORAGE_BUCKET",
    "STORAGE_PUBLIC_BUCKET",
    "STORAGE_PUBLIC_URL",
)


def test_it_refuses_to_start_without_a_database_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert e2e.main() == 2


def test_it_refuses_to_start_without_a_built_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://nobody@localhost:1/postgres")
    assert e2e.main(root=tmp_path) == 2


def test_its_app_never_reads_a_local_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A .env with half a storage or mail setup in it would stop the server
    starting, whatever the launcher blanks (cubic on #79), so it reads none."""
    from harness.testing import build_test_app

    # Only the .env below may hold mail or storage settings: none from the shell
    # (cubic on #79).
    for name in MAIL_AND_STORAGE:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "STORAGE_PUBLIC_BUCKET=public\nMAIL_FROM=site@mechframe.test\n", "utf-8"
    )
    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")
    url = "postgresql://nobody@localhost:1/none"
    with pytest.raises(RuntimeError, match="Refusing to start"):
        build_test_app(url)
    assert build_test_app(url, env_file=False) is not None


def test_its_site_is_the_address_the_browser_opens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The page's writes pass the origin check and a passkey's ceremony its
    origin and relying party, at the address Playwright opens (K4.5)."""
    from kernel.auth.ceremonies import relying_party
    from kernel.config import KernelConfig

    for name, value in e2e.environment(tmp_path, port=8799).items():
        monkeypatch.setenv(name, value)
    config = KernelConfig(_env_file=None)  # type: ignore[call-arg]
    assert config.site_url == "http://localhost:8799"
    party = relying_party(config)
    assert (party.id, party.origins) == ("localhost", ("http://localhost:8799",))
    assert config.rate_limit_enabled is False


async def test_its_database_is_made_fresh_with_the_sites_description(server_url: str) -> None:
    settings.register(server_copy.SECTION, server_copy.SiteSettings)  # as the server's app does
    name = f"mechframe_e2e_test_{uuid.uuid4().hex[:8]}"
    url = await e2e.fresh(server_url, name)
    admin = await asyncpg.connect(e2e._plain(server_url))
    try:
        stale = await asyncpg.connect(url)
        await stale.execute("CREATE TABLE left_behind (id int)")
        await stale.close()
        url = await e2e.fresh(server_url, name)  # a second start: dropped and made again
        await asyncio.to_thread(upgrade, url)
        await e2e.describe(url)
        database = Database(url)
        try:
            async with database.sessions() as db:
                saved = await settings.for_module(db, server_copy.SECTION)
        finally:
            await database.dispose()
        assert getattr(saved, "description", None) == e2e.DESCRIPTION
        fresh = await asyncpg.connect(url)
        try:
            assert await fresh.fetchval("SELECT to_regclass('left_behind')") is None
        finally:
            await fresh.close()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity"
            " WHERE datname = $1 AND usename = current_user AND pid <> pg_backend_pid()",
            name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await admin.close()


def _filter(name: str) -> re.Pattern[str]:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    match = re.search(rf"^\s*{name}=\$\(any '([^']+)'\)", workflow, re.MULTILINE)
    assert match, f"ci.yml has no {name} filter"
    return re.compile(match.group(1))


@pytest.mark.parametrize("path", ["kernel/tests/e2e/parity.spec.ts", "playwright.config.ts"])
def test_a_change_to_the_playwright_files_runs_the_web_jobs_lint_and_types(path: str) -> None:
    assert _filter("web").search(path)


def test_the_end_to_end_tests_never_run_on_a_pull_request() -> None:
    workflow = (ROOT / ".github" / "workflows" / "e2e.yml").read_text("utf-8")
    triggers = workflow.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert "pull_request" not in triggers
    assert all(trigger in triggers for trigger in ("push:", "schedule:", "workflow_dispatch:"))
