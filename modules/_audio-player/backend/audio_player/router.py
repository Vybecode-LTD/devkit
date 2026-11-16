"""HTTP routes for audio-player (SPEC.md section 7). Mounted at /api/audio-player behind require_module("audio-player").

Every route declares its access. Bodies are TODO: keep routers thin and put the logic in service.py.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import get_db, public, require_permission

router = APIRouter()


@router.post("/plays", dependencies=[Depends(public)])
async def count_play(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Count one play after `count_after_seconds` (rate limited)."""
    raise NotImplementedError("audio-player.count_play")


@router.get("/admin/plays")
async def play_stats(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("audio-player.stats.read")),
) -> dict[str, Any]:
    """Plays by item and day."""
    raise NotImplementedError("audio-player.play_stats")
