"""This site's own seed data (MechFrame's hook 4, decision 0052): rows that show
the site's own pages working, for a demo, a review or a screenshot, never the
live site's. `python -m app.seed` runs it last, after every module's.

It MUST be idempotent: fixed ids or slugs, and a check or an upsert before
each write, so a second run changes nothing. `ctx` gives a fixed clock
(`ctx.now`), a seeded random (`ctx.random`), a seeded account for a role
(`await ctx.user("editor")`) and a placeholder image in the public bucket
(`await ctx.put_image("hero")`, its key). It has nothing to seed until the
site has rows of its own.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from kernel import seed as seeding  # the public surface; `seed` is the function below


async def seed(db: AsyncSession, ctx: seeding.Context) -> None:
    """The site's own rows, in the run's transaction, which the run commits."""
    return None
