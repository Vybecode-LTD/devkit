"""HTTP routes for roster (SPEC.md section 7). Mounted at /api/roster behind require_module("roster").

Every route declares its access. Bodies are TODO: keep routers thin and put the logic in service.py.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import OwnerOr, get_db, public, require_owner_or

router = APIRouter()


@router.get("/profiles", dependencies=[Depends(public)])
async def list_profiles(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Visible profiles in ring order."""
    raise NotImplementedError("roster.list_profiles")


@router.get("/profiles/{slug}", dependencies=[Depends(public)])
async def get_profile(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """One profile; the page gathers work from other modules through their public surfaces."""
    raise NotImplementedError("roster.get_profile")


@router.put("/admin/profiles/{profile_id}")
async def save_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    who: OwnerOr = Depends(require_owner_or("roster.profile.manage")),
) -> dict[str, Any]:
    """Staff with the permission, or the member who owns the profile (require_owner_or)."""
    raise NotImplementedError("roster.save_profile")
