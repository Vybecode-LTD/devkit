"""The audit log: who did what to what, for every module and the kernel
(SPEC.md 6 and 14.10; decision 0037; contract dev plans/contracts/k3-audit.md).

    audit.record(db, "blog.post_deleted", actor=user.id, target=("blog.post", post.id))

`record` adds one row to the caller's session and awaits nothing: the
caller's commit writes it with the change, and its rollback drops both. Rows
are only ever added. Postgres refuses to change one, and to delete one but
in `kernel.prune_audit`'s own transactions (migration `kernel_0008`'s
trigger), which remove entries older than `AUDIT_KEEP_DAYS` (a year by
default) every night.

**Names.** An action is `<owner>.<name>`: the owner `auth`, `kernel` or an
installed module's id (`create_app` installs them), the name lowercase
`[a-z0-9_]` parts joined by dots. The kernel's own actions are a closed set,
`KERNEL_ACTIONS`, so a typo is a refusal (VybeSite's `staff_activity` rule).
A module writes only its own `<id>.*`. A target is `(kind, id)`, the kind
named the same way (`blog.post`, `auth.user`), the id kept as text.

**Details** hold ids, names, counts and flags: never a secret, a code or an
address, so an entry outlives the person it names without keeping what they
typed. `record` refuses a string holding `@` and a key naming a secret, and
anything JSON can't hold. Ids stay plain (no foreign keys), so a deleted
account's history stays, pseudonymous (14.7).

Every refusal is a ValueError, raised before anything is added.

**Reading** is `read`, for the staff's log (`GET /api/kernel/admin/audit`,
`auth.audit.read`) and each person's own security activity
(`GET /api/auth/activity`): newest first, in pages keyed on `(at, id)`,
as SPEC 7 has every list: `?cursor=&limit=` in, `{items, next_cursor}` out.
"""

from __future__ import annotations

import enum
import ipaddress
import json
import math
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import ColumnElement, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, jobs
from kernel.errors import Problem
from kernel.models import AuditEvent
from kernel.ratelimit import client_address

#: An owner is a module's id (`kernel.modules`) or the kernel's `auth` or
#: `kernel`; each part after it is lowercase, digits and underscores.
_OWNER = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
NAME = re.compile(rf"({_OWNER})(?:\.[a-z][a-z0-9_]*)+")
#: A prefix filter on the staff's log: an owner, or a name, ending in a dot.
PREFIX = re.compile(rf"{_OWNER}(?:\.[a-z][a-z0-9_]*)*\.")
RESULT = re.compile(r"[a-z][a-z0-9_]*")
MAX_NAME = 64
MAX_TARGET_ID = 64
MAX_RESULT = 16
#: The largest `details`, in bytes of compact JSON (UTF-8).
MAX_DETAILS = 4096
USER_AGENT_CHARS = 300

KERNEL_OWNERS = frozenset({"auth", "kernel"})

#: Every action the kernel writes. A new one is added here in the PR that
#: writes it; `kernel/tests/test_audit.py` holds this set to the code's calls.
KERNEL_ACTIONS = frozenset(
    {
        # Sign-up, verification and sign-in (K2).
        "auth.sign_up",
        "auth.email_verified",
        "auth.verification_resent",
        "auth.sign_in",
        "auth.code_sent",
        "auth.second_factor",
        "auth.step_up",
        "auth.sign_out",
        "auth.session_ended",
        # Passwords, addresses and second factors (K2).
        "auth.password_reset_requested",
        "auth.password_reset",
        "auth.password_changed",
        "auth.email_change_requested",
        "auth.email_changed",
        "auth.email_restored",
        "auth.totp_setup_started",
        "auth.totp_confirmed",
        "auth.totp_removed",
        "auth.recovery_codes_replaced",
        "auth.passkey_registration_started",
        "auth.passkey_added",
        "auth.passkey_renamed",
        "auth.passkey_removed",
        "auth.second_factor_undone",
        # What the kernel does on its own (K3).
        "auth.user.removed_unverified",
        "kernel.settings_saved",
        # Moderation and suspension (K3, decision 0039).
        "kernel.moderation.dismissed",
        "kernel.moderation.hidden",
        "kernel.moderation.deleted",
        "kernel.moderation.timed_out",
        "kernel.moderation.time_out_lifted",
        "auth.user.suspended",
        "auth.user.restored",
        # People and roles in the admin (K4.7).
        "auth.user.roles_changed",
        "auth.user.owner_link_issued",
        "auth.role.created",
        "auth.role.changed",
        "auth.role.deleted",
        # Features and System in the admin (K4.8).
        "kernel.module.enabled",
        "kernel.module.disabled",
        "kernel.job.retried",
        "kernel.job.discarded",
    }
)

#: A key naming one of these, as a part between underscores, is refused:
#: `password`, `new_password`, `csrf_token`, `recovery_code`.
_SECRET_PARTS = frozenset({"password", "secret", "token", "code"})

#: The setting `kernel.prune_audit` turns on, for its transaction alone, so
#: the trigger lets it delete (migration kernel_0008).
PRUNE_SWITCH = "kernel.audit_prune"
BATCH = 1000

Target = tuple[str, str | int | uuid.UUID]

_owners: frozenset[str] = KERNEL_OWNERS
_keep = timedelta(days=365)


def install(owners: Iterable[str], *, keep_days: int) -> None:
    """Sets the modules that may write and how long entries are kept:
    `create_app` and `create_worker` call it. Until then, the kernel alone,
    for a year."""
    global _owners, _keep
    if keep_days < 30:
        raise ValueError("The audit log is kept at least 30 days.")
    _owners = KERNEL_OWNERS | frozenset(owners)
    _keep = timedelta(days=keep_days)


def keep() -> timedelta:
    """How long an entry is kept."""
    return _keep


def check_action(action: str) -> None:
    """ValueError unless `action` is a name an installed owner may write."""
    match = NAME.fullmatch(action) if isinstance(action, str) else None
    if match is None or len(action) > MAX_NAME:
        raise ValueError(
            f"{action!r} isn't an audit action: <owner>.<name>, lowercase, at most {MAX_NAME}."
        )
    owner = match.group(1)
    if owner in KERNEL_OWNERS:
        if action not in KERNEL_ACTIONS:
            raise ValueError(f"{action} isn't one of the kernel's audit actions.")
    elif owner not in _owners:
        raise ValueError(f"{action}: no installed module is {owner}.")


def _target(target: object) -> tuple[str, str]:
    if not (isinstance(target, tuple) and len(target) == 2):
        raise ValueError("An audit target is (kind, id).")
    kind, raw = target
    if not (isinstance(kind, str) and len(kind) <= MAX_NAME and NAME.fullmatch(kind)):
        raise ValueError(f"{kind!r} isn't a target kind: <owner>.<entity>, lowercase.")
    if isinstance(raw, bool) or not isinstance(raw, str | int | uuid.UUID):
        raise ValueError("An audit target's id is text, a whole number or a UUID.")
    ident = str(raw)
    if "\x00" in ident:
        raise ValueError("An audit target's id never holds a NUL character.")
    if not 0 < len(ident) <= MAX_TARGET_ID:
        raise ValueError(f"An audit target's id is 1 to {MAX_TARGET_ID} characters.")
    return kind, ident


def _id(value: object, what: str) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    raise ValueError(f"An audit entry's {what} is an account's UUID or None.")


def _text(value: str, where: str) -> None:
    """ValueError for text an entry mustn't hold: a NUL, which Postgres's
    JSONB and text refuse at the caller's flush, or an address (an `@`), as a
    value or a key (CodeRabbit on #67)."""
    if "\x00" in value:
        raise ValueError(f"Audit entries never hold a NUL character ({where}).")
    if "@" in value:
        raise ValueError(f"Audit details never hold an address ({where}).")


def _plain(value: Any, where: str) -> Any:
    """`value` as JSON, or ValueError for anything an entry mustn't hold."""
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, enum.Enum):
        return _plain(value.value, where)
    if isinstance(value, str):
        _text(value, where)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Audit details hold finite numbers only ({where}).")
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Audit details' keys are text ({where}).")
            _text(key, f"{where} key")
            if _SECRET_PARTS & set(key.lower().split("_")):
                raise ValueError(f"Audit details never name a secret ({where}.{key}).")
            out[key] = _plain(item, f"{where}.{key}")
        return out
    if isinstance(value, list | tuple):
        return [_plain(item, f"{where}[{n}]") for n, item in enumerate(value)]
    raise ValueError(f"Audit details hold JSON values only, not {type(value).__name__} ({where}).")


def _details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    if details is None:
        return {}
    if not isinstance(details, Mapping):
        raise ValueError("Audit details are a mapping.")
    plain: dict[str, Any] = _plain(details, "details")
    size = len(json.dumps(plain, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if size > MAX_DETAILS:
        raise ValueError(f"Audit details are at most 4 KiB as JSON, not {size} bytes.")
    return plain


def _network(request: Request) -> str | None:
    """The client's address as Postgres's INET takes it, or None."""
    try:
        return str(ipaddress.ip_network(client_address(request), strict=False))
    except ValueError:
        return None


def record(
    db: AsyncSession,
    action: str,
    *,
    actor: uuid.UUID | None,
    target: Target | None = None,
    subject: uuid.UUID | None = None,
    result: str = "success",
    details: Mapping[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Adds an entry to the caller's transaction, which the caller commits.
    `actor` None is the kernel on its own (a job, the scheduler)."""
    check_action(action)
    kind, ident = _target(target) if target is not None else (None, None)
    if not (isinstance(result, str) and len(result) <= MAX_RESULT and RESULT.fullmatch(result)):
        raise ValueError(f"{result!r} isn't an audit result: lowercase, at most {MAX_RESULT}.")
    row = AuditEvent(
        at=clock.now(),
        actor_id=_id(actor, "actor"),
        subject_id=_id(subject, "subject"),
        action=action,
        result=result,
        target_type=kind,
        target_id=ident,
        ip=_network(request) if request is not None else None,
        user_agent=(
            request.headers.get("user-agent", "")[:USER_AGENT_CHARS] if request is not None else ""
        ),
        details=_details(details),
    )
    db.add(row)


# --- reading ---------------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DIGITS = re.compile(r"[0-9]{1,19}")
#: Postgres's bigint, the entry id's column.
_MAX_ID = 2**63 - 1


def cursor_of(entry: AuditEvent) -> str:
    """Where the next page starts: after `entry`, which it names."""
    return f"{(entry.at - _EPOCH) // timedelta(microseconds=1)}.{entry.id}"


def _after(value: str) -> tuple[datetime, int]:
    """The `(at, id)` a cursor names. Problem 422 for one `cursor_of` couldn't
    have made: not digits, a time past the last a datetime holds, or an id
    past the column's (Codex on #67)."""
    micros, dot, ident = value.partition(".")
    try:
        if not (dot and _DIGITS.fullmatch(micros) and _DIGITS.fullmatch(ident)):
            raise ValueError(value)
        if int(ident) > _MAX_ID:
            raise ValueError(value)
        return _EPOCH + timedelta(microseconds=int(micros)), int(ident)
    except (ValueError, OverflowError):
        raise Problem(
            "kernel.invalid_request",
            422,
            "Some of what was sent isn't valid.",
            errors={"cursor": ["Not a page of the audit log."]},
        ) from None


@dataclass(frozen=True)
class Page:
    entries: list[AuditEvent]
    next: str | None


async def read(
    db: AsyncSession,
    *,
    where: Sequence[ColumnElement[bool]] = (),
    cursor: str | None = None,
    limit: int = 50,
) -> Page:
    """A page of entries matching `where`, newest first, after `cursor`
    (SPEC 7's list shape). Problem 422 for a cursor `cursor_of` didn't make."""
    query = select(AuditEvent).where(*where)
    if cursor is not None:
        at, ident = _after(cursor)
        query = query.where(
            (AuditEvent.at < at) | ((AuditEvent.at == at) & (AuditEvent.id < ident))
        )
    query = query.order_by(AuditEvent.at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    found = list((await db.scalars(query)).all())
    more = len(found) > limit
    entries = found[:limit]
    return Page(entries, cursor_of(entries[-1]) if more else None)


def item(entry: AuditEvent) -> dict[str, Any]:
    """An entry as the staff's log answers it."""
    return {
        "id": entry.id,
        "at": entry.at.isoformat(),
        "action": entry.action,
        "result": entry.result,
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "subject_id": str(entry.subject_id) if entry.subject_id else None,
        "target": (
            {"type": entry.target_type, "id": entry.target_id} if entry.target_type else None
        ),
        "ip": str(entry.ip) if entry.ip is not None else None,
        "user_agent": entry.user_agent,
        "details": entry.details,
    }


def own_item(entry: AuditEvent, person: uuid.UUID) -> dict[str, Any]:
    """An entry as the person it concerns reads it: whether they did it, never
    who else did (a staff member stays unnamed)."""
    shown = item(entry)
    del shown["actor_id"], shown["subject_id"]
    shown["by_you"] = entry.actor_id == person
    return shown


# --- the kernel's own job: pruning -------------------------------------------------------


async def _prune(ctx: jobs.Context) -> None:
    """Deletes entries older than the keep, in batches, each in a transaction
    of its own that turns the trigger's switch on for itself alone."""
    cutoff = clock.now() - _keep
    while True:
        async with ctx.sessions() as db:
            await db.execute(text("SELECT set_config(:name, 'on', true)"), {"name": PRUNE_SWITCH})
            doomed = select(AuditEvent.id).where(AuditEvent.at < cutoff).limit(BATCH)
            result = await db.execute(delete(AuditEvent).where(AuditEvent.id.in_(doomed)))
            await db.commit()
        if getattr(result, "rowcount", 0) < BATCH:
            return


PRUNE = jobs.scheduled("53 3 * * *", "kernel.prune_audit", timeout=900)(_prune)
