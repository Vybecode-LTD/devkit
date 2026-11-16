"""HTTP routes for discography (SPEC.md section 7). Mounted at /api/discography behind require_module("discography").

Every route declares its access. Bodies are TODO: keep routers thin and put the logic in service.py.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import get_db, public, require_permission

router = APIRouter()


@router.get("/albums", dependencies=[Depends(public)])
async def list_albums(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Published albums, newest first (cursor pagination)."""
    raise NotImplementedError("discography.list_albums")


@router.get("/albums/{slug}", dependencies=[Depends(public)])
async def get_album(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """One album with its playable tracks (tracks with no audio are left out)."""
    raise NotImplementedError("discography.get_album")


@router.get("/admin/albums")
async def admin_list_albums(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("discography.release.manage")),
) -> dict[str, Any]:
    """Every album with its problems (tracks with no audio, processing)."""
    raise NotImplementedError("discography.admin_list_albums")


@router.put("/admin/albums/{album_id}")
async def save_album(
    album_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("discography.release.manage")),
) -> dict[str, Any]:
    """Create or update an album; sends `version`."""
    raise NotImplementedError("discography.save_album")


@router.post("/admin/tracks")
async def upload_track(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("discography.release.manage")),
) -> dict[str, Any]:
    """Upload a master to private storage; queues the job that makes the stream file, duration and peaks."""
    raise NotImplementedError("discography.upload_track")


@router.put("/admin/tracks/{track_id}")
async def save_track(
    track_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("discography.release.manage")),
) -> dict[str, Any]:
    """Title, order, explicit flag, lyrics, or switch the source to a SoundCloud link."""
    raise NotImplementedError("discography.save_track")


@router.delete("/admin/tracks/{track_id}")
async def delete_track(
    track_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("discography.release.manage")),
) -> dict[str, Any]:
    """Remove a track; emits discography.track.deleted."""
    raise NotImplementedError("discography.delete_track")
