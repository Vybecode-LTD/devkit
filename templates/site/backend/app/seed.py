"""The site's seed data: `python -m app.seed` (MechFrame's hook 4, decision 0052).
`mechframe seed` runs it with this site's `.venv`.

It seeds every module this site has that has a `seed.py`, each after those it
requires, then the site's own (`app/site/seed.py`) last, in one transaction:
a seed that fails keeps nothing, and a second run changes nothing. It runs as
the app does, from its own settings (the environment or `.env`) and its
modules, so their listeners hear of the accounts it makes.

It refuses unless MECHFRAME_ALLOW_SEED=1 is in the environment, read from
there only, never `.env`; `.railway/railway.ts` never sets it, so seed data
never reaches the live site. For one run, cleared after it, in PowerShell:
`$env:MECHFRAME_ALLOW_SEED = "1"; try { .venv\\Scripts\\python.exe -m app.seed }
finally { Remove-Item Env:MECHFRAME_ALLOW_SEED }`.
"""

from __future__ import annotations

import asyncio
import sys

from app import installed
from app.modules import MODULE_IDS
from app.site.pages import SITE_PAGES
from app.site.seed import seed as site_seed
from kernel import seed
from kernel.app import Assembled, assemble


async def _seed(built: Assembled) -> list[str]:
    database = built.database()
    try:
        async with database.sessions() as db:
            return await seed.run(db, built.installed, site=site_seed)
    finally:
        await database.dispose()


def main(argv: list[str]) -> int:
    if argv:
        print("usage: python -m app.seed  (with MECHFRAME_ALLOW_SEED=1)", file=sys.stderr)
        return 2
    try:
        seed.check_allowed()
        # The site as its app is built: its modules' events, mail and audit owners.
        built = assemble(modules=installed(MODULE_IDS), role="worker", site=SITE_PAGES)
        seeded = asyncio.run(_seed(built))
    except (seed.Refused, RuntimeError) as refusal:
        print(f"Refused: {refusal}", file=sys.stderr)
        return 2
    print("Seeded: " + ", ".join(seeded) + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
