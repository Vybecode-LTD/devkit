"""HTTP routes for comments (SPEC.md section 7). Mounted at /api/comments behind require_module("comments").

Every route declares its access. Bodies are TODO: keep routers thin and put the logic in service.py.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import get_db, public, require_permission

router = APIRouter()


@router.get("/threads/{target_module}/{target_id}", dependencies=[Depends(public)])
async def get_thread(
    target_module: str, target_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Approved comments, two levels deep, sorted by top or newest."""
    raise NotImplementedError("comments.get_thread")


@router.post("/threads/{target_module}/{target_id}", dependencies=[Depends(public)])
async def post_comment(
    target_module: str, target_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Members and (if allowed) guests; first comments and guest comments wait for approval. Rate limited."""
    raise NotImplementedError("comments.post_comment")


@router.get("/admin/queue")
async def approval_queue(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("comments.comment.approve")),
) -> dict[str, Any]:
    """Comments waiting for approval, oldest first."""
    raise NotImplementedError("comments.approval_queue")


@router.post("/admin/comments/{comment_id}/approve")
async def approve(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("comments.comment.approve")),
) -> dict[str, Any]:
    """Approve one comment; emits comments.comment.approved."""
    raise NotImplementedError("comments.approve")
