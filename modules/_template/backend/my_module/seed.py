"""my-module: its seed data (kernel.seed, hook 4, decision 0052).

Rows that show the module working, for a demo, a review or a screenshot,
never a live site's: `mechframe seed` runs every module's, each after those
it requires, only with MECHFRAME_ALLOW_SEED=1. It MUST be idempotent, so a
second run changes nothing. For example:

    from kernel.seed import Context

    async def seed(db: AsyncSession, ctx: Context) -> None:
        author = await ctx.user("editor")
        for number, slug in enumerate(("welcome", "second-post"), 1):
            if await db.scalar(select(Item.id).where(Item.slug == slug)) is None:
                db.add(Item(slug=slug, title=f"Item {number}", author_id=author,
                            created_at=ctx.now, cover=await ctx.put_image(slug)))

`ctx.now` is a fixed instant and `ctx.random` is seeded with the module's
id, so a seed writes the same rows each run. A module with nothing to seed
leaves `seed` as None, or deletes this file.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

seed: Callable[[Any, Any], Awaitable[None]] | None = None
