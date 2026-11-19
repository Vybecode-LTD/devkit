"""The dashboard's "Needs you" list (K4 contract §2, addition 9; SPEC 8, the
owner's lens): what's wrong, why it matters and what fixes it, each item only
for the people who can act on it.

The kernel's own items are the site's missing description and card image,
for those who can change the site's settings, and failed background jobs, for
those who can also open System and retry them. The worst come first: a
danger, then a warning, then what's only worth knowing. Modules add theirs
through the dashboard cards hook, after v1.0 (decision 0018).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import server_copy
from kernel.auth.permissions import can
from kernel.models import Job

Tone = Literal["info", "warning", "danger"]

#: The order a tone sorts in: the worst first.
_RANK: dict[Tone, int] = {"danger": 0, "warning": 1, "info": 2}

SETTINGS = "kernel.settings.manage"
JOBS = "kernel.jobs.manage"
SITE_PAGE = "/admin/settings"
SYSTEM_PAGE = "/admin/settings/system"


@dataclass(frozen=True)
class Item:
    key: str
    tone: Tone
    what: str
    why: str
    label: str
    to: str

    def as_answer(self) -> dict[str, object]:
        return {
            "key": self.key,
            "tone": self.tone,
            "what": self.what,
            "why": self.why,
            "action": {"label": self.label, "to": self.to},
        }


def _failed(count: int) -> Item:
    jobs = "1 background job" if count == 1 else f"{count} background jobs"
    return Item(
        key="kernel.jobs.dead",
        tone="danger",
        what=f"{jobs} failed",
        why=(
            "They ran out of tries, so what they were doing, such as sending an email, "
            "didn't happen. Retry them once the cause is fixed, or discard them."
        ),
        label="See failed jobs",
        to=SYSTEM_PAGE,
    )


DESCRIPTION_MISSING = Item(
    key="kernel.site.description_missing",
    tone="warning",
    what="The site has no description",
    why=(
        "Search engines and AI answers describe the site with whatever words they "
        "find on the home page instead."
    ),
    label="Add a description",
    to=SITE_PAGE,
)

CARD_MISSING = Item(
    key="kernel.site.card_missing",
    tone="info",
    what="Shared links show no picture",
    why="A link to the site posted anywhere has no image beside it until you choose one.",
    label="Choose a picture",
    to=SITE_PAGE,
)


async def _dead_jobs(db: AsyncSession) -> int:
    count = await db.scalar(select(func.count()).select_from(Job).where(Job.state == "dead"))
    return int(count or 0)


async def for_person(db: AsyncSession, user_id: uuid.UUID) -> list[Item]:
    """What needs this person, the worst first."""
    found: list[Item] = []
    site_settings = await can(db, user_id, SETTINGS)
    if site_settings:
        identity = await server_copy.identity(db)
        if not identity.description.strip():
            found.append(DESCRIPTION_MISSING)
        if not identity.card_image.strip():
            found.append(CARD_MISSING)
    # System is read with the settings permission; a job is retried with the jobs one.
    if site_settings and await can(db, user_id, JOBS):
        dead = await _dead_jobs(db)
        if dead:
            found.append(_failed(dead))
    return sorted(found, key=lambda item: _RANK[item.tone])
