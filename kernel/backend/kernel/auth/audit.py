"""Auth's entries in the kernel's audit log (SPEC.md 14.10; `kernel.audit`,
decision 0037): sign-ins and their failures, second-factor failures,
step-ups, sign-outs and ended sessions, each with its actor, subject, address
and browser.

These are auth's shorthand for `kernel.audit.record`, which writes every
module's entries: `record` for what a request did, `record_by_kernel` for
what the kernel did on its own, in a job. `details` holds only what the
action needs explained, never a secret, a code or an address someone typed:
a failed sign-in for an address with no account keeps no trace of the
address.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit as log


def record(
    db: AsyncSession,
    request: Request,
    action: str,
    result: str,
    *,
    actor: uuid.UUID | None = None,
    subject: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an entry to the caller's transaction, which the caller commits."""
    log.record(
        db, action, actor=actor, subject=subject, result=result, details=details, request=request
    )


def record_by_kernel(
    db: AsyncSession,
    action: str,
    result: str,
    *,
    subject: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """An entry for what the kernel did on its own, in a job: no actor,
    address or browser. Added to the caller's transaction, which the caller
    commits."""
    log.record(db, action, actor=None, subject=subject, result=result, details=details)
