"""HTTP routes for featured (SPEC.md section 7). Mounted at /api/featured behind require_module("featured").

Every route declares its access. Bodies are TODO: keep routers thin and put the logic in service.py.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import get_db, public, require_permission

router = APIRouter()


@router.get("/slots/{key}", dependencies=[Depends(public)])
async def live_slot(key: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The slot's live placements, in order (starts_at <= now < ends_at, or no dates)."""
    raise NotImplementedError("featured.live_slot")


@router.get("/admin/slots")
async def list_slots(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("featured.placement.manage")),
) -> dict[str, Any]:
    """Every slot with its placement count and what's live now."""
    raise NotImplementedError("featured.list_slots")


@router.get("/admin/slots/{key}")
async def get_slot(
    key: str,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("featured.placement.manage")),
) -> dict[str, Any]:
    """All placements in a slot, live, scheduled and ended, with the slot's version."""
    raise NotImplementedError("featured.get_slot")


@router.put("/admin/slots/{key}")
async def replace_slot(
    key: str,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("featured.placement.manage")),
) -> dict[str, Any]:
    """Replace the ordered list in one save. Checks `version` (SaveConflict) and each item against `accepts`; emits featured.placement.changed; audited."""
    raise NotImplementedError("featured.replace_slot")


@router.post("/admin/oembed")
async def oembed(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("featured.placement.manage")),
) -> dict[str, Any]:
    """Title and thumbnail for a pasted YouTube link, through the kernel's SSRF guard."""
    raise NotImplementedError("featured.oembed")
