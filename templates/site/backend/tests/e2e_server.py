"""The server Playwright runs against (web/playwright.config.ts starts it):

    python backend/tests/e2e_server.py          (with PYTHONPATH=backend)

The site's app and its built web app (`web/dist`: `npm run build` first) on
a database of its own: it drops and makes `site_e2e` on TEST_DATABASE_URL's
server at each start, migrates it and gives the site a description, so the
home page has words of both kinds to compare. Made-up secrets each start, no
.env read, and DEBUG on, since the address is http://localhost.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from cryptography.fernet import Fernet

SITE = Path(__file__).resolve().parents[2]
NAME = "site_e2e"
PORT = int(os.environ.get("E2E_PORT", "8766"))
DESCRIPTION = "A site made from MechFrame's template, for its end-to-end tests."


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def fresh(admin_url: str) -> str:
    """The database `site_e2e`, dropped and made again; its URL."""
    admin = await asyncpg.connect(_plain(admin_url), timeout=5)
    try:
        await admin.execute(
            "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity"
            " WHERE datname = $1 AND usename = current_user AND pid <> pg_backend_pid()",
            NAME,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{NAME}"')
        await admin.execute(f'CREATE DATABASE "{NAME}"')
    finally:
        await admin.close()
    return urlunsplit(urlsplit(_plain(admin_url))._replace(path=f"/{NAME}"))


async def describe(database_url: str) -> None:
    from kernel import server_copy
    from kernel.db import Database
    from kernel.settings import settings

    database = Database(database_url)
    try:
        async with database.sessions() as db:
            form = await settings.form(db, server_copy.SECTION)
            await settings.save(
                db, server_copy.SECTION, {"description": DESCRIPTION}, version=form["version"]
            )
            await db.commit()
    finally:
        await database.dispose()


def environment(dist: Path, database_url: str) -> dict[str, str]:
    """Made up, as the tests' conftest.py's are; .test is reserved, never live."""
    return {
        "DATABASE_URL": database_url,
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": Fernet.generate_key().decode(),
        "DEBUG": "true",
        "WEB_DIST": str(dist),
        "SITE_NAME": "Test Site",
        "SITE_URL": f"http://localhost:{PORT}",
        "RATE_LIMIT_ENABLED": "false",
        "MODULES": "*",
        "SENTRY_DSN": "",
        "CLIENT_IP_HEADER": "",
        "HSTS_MAX_AGE": "0",
        "JOBS_IN_WEB": "false",
        "MAIL_FROM": "",
        "SMTP_HOST": "",
        "RESEND_API_KEY": "",
        "STORAGE_ENDPOINT_URL": "",
        "STORAGE_ACCESS_KEY_ID": "",
        "STORAGE_SECRET_ACCESS_KEY": "",
        "STORAGE_BUCKET": "",
    }


def main() -> int:
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        print("Set TEST_DATABASE_URL to a Postgres server's admin URL.", file=sys.stderr)
        return 2
    dist = SITE / "web" / "dist"
    if not (dist / "index.html").is_file():
        print("No built web app: run `npm run build` in web/ first.", file=sys.stderr)
        return 2
    database_url = asyncio.run(fresh(admin_url))
    from app.migrations import upgrade

    upgrade(database_url)
    os.environ.update(environment(dist, database_url))
    import uvicorn

    from app import installed
    from app.modules import MODULE_IDS
    from app.site.pages import SITE_PAGES
    from kernel import create_app
    from kernel.config import KernelConfig

    no_env_file: dict[str, Any] = {"_env_file": None}  # the environment above, no .env
    config = KernelConfig(**no_env_file)
    app = create_app(modules=installed(MODULE_IDS), config=config, site=SITE_PAGES)
    asyncio.run(describe(database_url))
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
