"""HTTP routes for portfolio (SPEC.md section 7). Mounted at /api/portfolio behind require_module("portfolio").

Every route declares its access. Bodies are TODO: keep routers thin and put the logic in service.py.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import OwnerOr, get_db, public, require_owner_or

router = APIRouter()


@router.get("/pieces", dependencies=[Depends(public)])
async def list_pieces(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Published pieces, filterable by discipline."""
    raise NotImplementedError("portfolio.list_pieces")


@router.get("/pieces/{slug}", dependencies=[Depends(public)])
async def get_piece(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """One piece with its images."""
    raise NotImplementedError("portfolio.get_piece")


@router.put("/admin/pieces/{piece_id}")
async def save_piece(
    piece_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    who: OwnerOr = Depends(require_owner_or("portfolio.piece.manage")),
) -> dict[str, Any]:
    """Create or update a piece; sends `version`."""
    raise NotImplementedError("portfolio.save_piece")
