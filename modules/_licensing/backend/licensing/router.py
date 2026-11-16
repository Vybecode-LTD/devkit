"""HTTP routes for licensing (SPEC.md section 7). Mounted at /api/licensing behind require_module("licensing").

Every route declares its access. Bodies are TODO: keep routers thin and put the logic in service.py.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import OwnerOr, get_db, public, require_owner_or, require_permission

router = APIRouter()


@router.get("/works", dependencies=[Depends(public)])
async def list_works(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The beat store, filterable by BPM, key, genre and mood."""
    raise NotImplementedError("licensing.list_works")


@router.get("/licenses/{license_id}", dependencies=[Depends(public)])
async def check_license(
    license_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Public license check: work, tier, buyer name and date, nothing private."""
    raise NotImplementedError("licensing.check_license")


@router.put("/admin/works/{work_id}")
async def save_work(
    work_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    who: OwnerOr = Depends(require_owner_or("licensing.work.manage")),
) -> dict[str, Any]:
    """Create or update a work and its files."""
    raise NotImplementedError("licensing.save_work")


@router.put("/admin/tiers")
async def save_tiers(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("licensing.tier.manage")),
) -> dict[str, Any]:
    """The tier table: formats, prices, terms, exclusive flag."""
    raise NotImplementedError("licensing.save_tiers")
