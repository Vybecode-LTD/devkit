"""A worker in a process of its own, for test_worker.py's restart tests (the
K3 gate): it runs one job whose first try writes a marker file and then
hangs, so a test can kill the process, or ask it to stop, mid-job.

    python kernel/tests/jobs_child.py <database url> <module id> <marker path> [serve]

With `serve`, it runs as a site's worker process does (`kernel.worker.serve`:
signals and the watchdog), with a short drain. Run with the repo root on
PYTHONPATH and the test run's environment.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import harness  # noqa: F401  (puts the kernel on sys.path)
from kernel import jobs
from kernel.db import Database
from kernel.email import LogMailer
from kernel.modules import InstalledModule, Manifest, ModuleRegistry
from kernel.worker import Worker, serve


def main(url: str, module_id: str, marker: str, mode: str = "") -> int:
    async def first_try_hangs(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(Path(marker).write_text, str(ctx.try_number), "utf-8")
        await asyncio.sleep(3600)

    job = jobs.handler(f"{module_id}.slow", tries=3, timeout=3600)(first_try_hangs)
    manifest = Manifest.from_dict(
        {"id": module_id, "name": "Child", "version": "0.1.0", "requires": {"kernel": "^0.1"}}
    )
    registry = ModuleRegistry([InstalledModule(manifest)], [module_id], ttl=0)
    database = Database(url, pool_size=2, max_overflow=2)
    worker = Worker(
        [job], registry=registry, database=database, mailer=LogMailer(), poll=0.1, drain=0.5
    )
    if mode == "serve":
        return serve(worker)
    asyncio.run(worker.run(asyncio.Event()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
