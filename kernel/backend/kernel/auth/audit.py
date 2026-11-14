"""Auth's rows in the append-only audit log (SPEC.md 14.10): sign-ins and
their failures, second-factor failures, step-ups, sign-outs and ended
sessions, each with its actor, subject, address and browser.

`details` holds only what the action needs explained, never a secret, a code
or an address someone typed: a failed sign-in for an address with no account
keeps no trace of the address. K3's `audit.record` takes over the writing for
every module; until then auth writes its own rows here.
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.auth.models import AuditEvent
from kernel.ratelimit import client_address

_USER_AGENT_CHARS = 300


def _network(request: Request) -> str | None:
    """The client's address as Postgres's INET takes it, or None."""
    try:
        return str(ipaddress.ip_network(client_address(request), strict=False))
    except ValueError:
        return None


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
    """Add a row to the caller's transaction, which the caller commits."""
    db.add(
        AuditEvent(
            at=clock.now(),
            actor_id=actor,
            subject_id=subject,
            action=action,
            result=result,
            ip=_network(request),
            user_agent=request.headers.get("user-agent", "")[:_USER_AGENT_CHARS],
            details=details or {},
        )
    )
