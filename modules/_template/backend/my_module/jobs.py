"""my-module: its background and scheduled jobs (kernel.jobs, decision 0035).

Every `jobs.Job` here is found by its type: `@jobs.handler` declares one that
code queues, `@jobs.scheduled` one that runs on a cron line (UTC) and must
also be listed in module.json's `jobs` with the same schedule. Names are
`my-module.<name>` (`[a-z][a-z0-9_]*` after the dot). For example:

    from typing import Any

    @jobs.handler("my-module.send_digest", tries=5, timeout=300)
    async def send_digest(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        async with ctx.sessions() as db:
            ...

    @jobs.scheduled("*/5 * * * *", "my-module.publish_scheduled")
    async def publish_scheduled(ctx: jobs.Context) -> None: ...

and, in the module's service, in the same transaction as the change:

    await jobs.enqueue(db, "my-module.send_digest", {"week": 47})

A job runs at least once: make each one safe to run twice. Keep ids in a
payload, not rows; pass `sealed=True` for anything a database dump mustn't
show.
"""

from kernel import jobs  # noqa: F401  (the examples above use it)
