"""The harness's seed data (hook 4, decision 0052):

    $env:MECHFRAME_ALLOW_SEED = "1"
    try { python -m harness.seed } finally { Remove-Item Env:MECHFRAME_ALLOW_SEED }

Seeds every module in this repo that has a `seed.py`, each after those it
requires (`kernel.seed`), on the harness's database (DATABASE_URL). It
refuses unless MECHFRAME_ALLOW_SEED=1 is in the environment, which is read
from the environment only, never `.env`. Run `python -m harness.migrations
upgrade` first. A second run changes nothing.

The probe modules aren't seeded here: only the test support mounts them,
and the contract suite seeds them through `POST /api/_test/seed`.
"""

from __future__ import annotations

import asyncio
import sys

from harness.registry import discover
from kernel import seed
from kernel.app import Assembled, assemble


async def _seed(built: Assembled) -> list[str]:
    database = built.database()
    try:
        async with database.sessions() as db:
            return await seed.run(db, built.installed)
    finally:
        await database.dispose()


def main() -> int:
    try:
        seed.check_allowed()
        built = assemble(modules=discover(), role="worker")
        seeded = asyncio.run(_seed(built))
    except (seed.Refused, RuntimeError) as refusal:
        print(f"Refused: {refusal}", file=sys.stderr)
        return 2
    print("Seeded: " + (", ".join(seeded) or "nothing, since no module has a seed") + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
