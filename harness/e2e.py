"""The server Playwright runs against (`npm run e2e`; playwright.config.ts).

    python -m harness.e2e

The harness with its test support (HARNESS_TEST_SUPPORT=1) and the built web
app (WEB_DIST, `npm run build` first), on a database of its own: it drops and
makes `mechframe_e2e` on TEST_DATABASE_URL's server at each start, so a run
stopped half-way is cleaned by the next, then migrates it and gives the site
a description, so the home page's parity test compares a paragraph as well as
the heading. A fresh SECRET_KEY each start; nothing here is a site's.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
NAME = "mechframe_e2e"
PORT = int(os.environ.get("E2E_PORT", "8765"))
SITE_NAME = "MechFrame test site"
DESCRIPTION = "A site built from MechFrame's modules, for the end-to-end tests."


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def fresh(admin_url: str, name: str = NAME) -> str:
    """The database `name`, dropped and made again; its URL."""
    admin = await asyncpg.connect(_plain(admin_url), timeout=5)
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
    return urlunsplit(urlsplit(_plain(admin_url))._replace(path=f"/{name}"))


async def describe(database_url: str) -> None:
    """Gives the site its description (the settings section kernel.site)."""
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


def main(root: Path = ROOT) -> int:
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        print("Set TEST_DATABASE_URL to a Postgres server's admin URL.", file=sys.stderr)
        return 2
    dist = root / "harness" / "web" / "dist"
    if not (dist / "index.html").is_file():
        print("No built web app: run `npm run build` first.", file=sys.stderr)
        return 2
    database_url = asyncio.run(fresh(admin_url))

    from harness.migrations import upgrade

    upgrade(database_url)
    # Made up, as conftest.py's are. The app reads no .env (env_file=False
    # below), so a local one's keys, bucket or mail server never reach it;
    # these blanks also cover anything set in the shell. .test is reserved
    # (RFC 2606), never live.
    os.environ.update(
        {
            "HARNESS_TEST_SUPPORT": "1",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "ENCRYPTION_KEYS": Fernet.generate_key().decode(),
            "DEBUG": "false",
            "WEB_DIST": str(dist),
            "SITE_NAME": SITE_NAME,
            "SITE_URL": "https://mechframe.test",
            "MODULES": "*",
            "SENTRY_DSN": "",
            "CLIENT_IP_HEADER": "",
            "CORS_ORIGINS": "",
            "HSTS_MAX_AGE": "0",
            "ROBOTS_NOINDEX": "false",
            "JOBS_IN_WEB": "false",
            "STORAGE_ENDPOINT_URL": "",
            "STORAGE_ACCESS_KEY_ID": "",
            "STORAGE_SECRET_ACCESS_KEY": "",
            "STORAGE_BUCKET": "",
            "STORAGE_PUBLIC_BUCKET": "",
            "STORAGE_PUBLIC_URL": "",
            "MAIL_FROM": "",
            "MAIL_FROM_NAME": "",
            "SMTP_HOST": "",
            "SMTP_USERNAME": "",
            "SMTP_PASSWORD": "",
            "RESEND_API_KEY": "",
        }
    )
    import uvicorn

    from harness.testing import build_test_app

    app = build_test_app(database_url, env_file=False)  # registers the settings sections
    asyncio.run(describe(database_url))
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
