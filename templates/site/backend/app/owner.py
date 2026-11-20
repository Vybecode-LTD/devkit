"""The site's owner, from the server: `python -m app.owner <email>` (K5 contract
§2; decision 0051). `mechframe create-owner` runs it with this site's `.venv`.

It makes the address's account the owner (making the account when there's
none) and prints a one-time link to set its password, valid 30 minutes, so no
password is typed into a terminal (the owner, 2026-11-20). Nothing is mailed.
With an owner already, only an owner's own address gets a new link, which is
how an owner locked out gets back in from the server; any other address is
refused, since an owner grants the role in Admin, People.

It runs with the app's own settings, from the environment or `.env`: its
database, and its SECRET_KEY, which the link's stored hash is keyed with, so
it refuses the secrets the app would refuse. On Railway, run it in the
service's own shell (`railway ssh`), where both are.
"""

from __future__ import annotations

import asyncio
import sys

from kernel.auth import owners
from kernel.config import KernelConfig, get_config, unsafe_secrets
from kernel.db import Database


async def _issue(config: KernelConfig, email: str) -> str:
    database = Database(config.database_url)
    try:
        async with database.sessions() as db:
            return await owners.create_owner(db, email)
    finally:
        await database.dispose()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.owner <email>", file=sys.stderr)
        return 2
    config = get_config()
    wrong = unsafe_secrets(config)
    if wrong and not config.debug:
        print(
            "Refused: " + " ".join(wrong) + " The link is checked with the app's own SECRET_KEY.",
            file=sys.stderr,
        )
        return 2
    try:
        token = asyncio.run(_issue(config, argv[0]))
    except owners.OwnerRefused as refusal:
        print(f"Refused: {refusal}", file=sys.stderr)
        return 2
    print(f"{argv[0].strip()} is the site's owner. Set its password within 30 minutes, once, at:")
    if config.site_url:
        print(f"  {owners.link(config.site_url, token)}")
    else:
        print(f"  {owners.link('', token)}  (on this site: SITE_URL isn't set)")
    print("The link is the way in: don't share it. Run this again for a new one.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
