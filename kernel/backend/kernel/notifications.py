"""Notices to a person, in the site and by email, by their choice per key
(SPEC.md 6; decision 0038; contract dev plans/contracts/k3-notifications.md).

    await notifications.notify(db, user_id, "comments.reply", {"post": title}, link="/blog/x#c4")

**Keys** are declared in module.json's `notifications` (`{key, description,
default}`, the default `in_site`, `email` or `both`), each `<module id>.<name>`
and each with an email template of the same name (kernel.email). `assemble`
checks both and installs them; until then, no key is known.

**`notify`** renders the key's template now: its subject is the notice's
title in the site, its text and HTML the email. Then, in the caller's
transaction, it adds a `kernel_notification` row and queues the mail, sealed
(kernel.email, kernel.jobs), each as the person chose for that key, else as
the module's default. Email goes only to an `active` account with a verified
address; an account that isn't `active` gets nothing. Nothing goes out if the
change rolls back. A caller's bug (a key nobody declares, a link off the site,
a value the template needs) is ValueError, before anything is written.

**Every notice email** carries a footer (`kernel.notification_footer`, a
template a site can reword) with the unsubscribe and settings links, and the
one-click headers of RFC 8058. The unsubscribe token names the person and the
key, signed with SECRET_KEY, and never expires; it turns email off for that key
alone (the owner's answer). Security mail (`kernel.auth.mails`) is never a
notice and can't be turned off.

**Pruning:** `kernel.prune_notifications`, nightly, removes a notice 90 days
after it's read, and any notice after a year (the owner's answer).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, email, jobs
from kernel.auth.hashing import keyed_hash, same
from kernel.auth.models import User
from kernel.errors import Problem
from kernel.models import Notification, NotificationPreference

#: A key: a module's id, a dot, a name (module.schema.json's pattern).
KEY = re.compile(r"([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.[a-z][a-z0-9_]*")
MAX_KEY = 100
MAX_LINK = 500
#: A link is a path on this site: printable ASCII after one slash, no second
#: slash first (`//host` leaves the site), no backslash, no space.
_LINK = re.compile(r"/(?![/\\])[!-\[\]-~]*")
CHANNELS = {"in_site": (True, False), "email": (False, True), "both": (True, True)}

FOOTER = "kernel.notification_footer"
UNSUBSCRIBE_API = "/api/kernel/notifications/unsubscribe"
#: The pages K4's web shell serves for a person: confirm an unsubscribe, and
#: change every key.
UNSUBSCRIBE_PAGE = "/notifications/unsubscribe"
SETTINGS_PAGE = "/account/notifications"
ONE_CLICK = "List-Unsubscribe=One-Click"

KEEP_READ = timedelta(days=90)
KEEP_LONGEST = timedelta(days=365)
BATCH = 1000

#: The kernel's own template, the footer of every notice email. Its subject
#: is never sent.
TEMPLATES = {
    FOOTER: email.Template(
        subject="Your notification settings",
        text=(
            "\n--\nYou get this email because of your notification settings: "
            "${settings_url}\nStop these emails: ${unsubscribe_url}\n"
        ),
        html=(
            '<hr><p>You get this email because of your <a href="${settings_url}">'
            'notification settings</a>. <a href="${unsubscribe_url}">Stop these emails</a>.</p>'
        ),
    )
}


@dataclass(frozen=True)
class Kind:
    """A declared key: who owns it, what it's for, where it goes by default."""

    key: str
    module: str
    description: str
    default: str

    @property
    def in_site(self) -> bool:
        return CHANNELS[self.default][0]

    @property
    def email(self) -> bool:
        return CHANNELS[self.default][1]


@dataclass(frozen=True)
class Sent:
    """Where a notice went."""

    in_site: bool
    email: bool


def build(
    declared: Iterable[tuple[str, Sequence[Any]]], templates: Mapping[str, email.Template]
) -> dict[str, Kind]:
    """Every key, from (module id, its module.json's `notifications`) pairs,
    in the order declared. ValueError, naming the key, on any the start can't take."""
    kinds: dict[str, Kind] = {}
    for owner, entries in declared:
        for entry in entries:
            key = str(entry.get("key", "")) if isinstance(entry, Mapping) else ""
            match = KEY.fullmatch(key)
            if match is None or match.group(1) != owner or len(key) > MAX_KEY:
                raise ValueError(f"{owner} may only declare {owner}.* notifications, not {key!r}.")
            if key in kinds:
                raise ValueError(f"The notification {key} is declared twice.")
            if key not in templates:
                raise ValueError(
                    f"The notification {key} needs an email template of the same name "
                    "(its subject is the notice's title)."
                )
            default = entry.get("default")
            description = entry.get("description")
            if default not in CHANNELS or not isinstance(description, str):
                raise ValueError(f"The notification {key} needs a description and a default.")
            kinds[key] = Kind(key, owner, description, default)
    return kinds


_kinds: dict[str, Kind] = {}


def install(kinds: Mapping[str, Kind]) -> None:
    """Sets the keys `notify` knows: `create_app` and `create_worker` call it."""
    global _kinds
    _kinds = dict(kinds)


def _kind(key: str) -> Kind:
    kind = _kinds.get(key) if isinstance(key, str) else None
    if kind is None:
        raise ValueError(f"No installed module declares the notification {key!r}.")
    return kind


def _check_link(link: str) -> None:
    if not (isinstance(link, str) and len(link) <= MAX_LINK and _LINK.fullmatch(link)):
        raise ValueError(
            f"A notice's link is a path on this site: one /, then at most {MAX_LINK} "
            "printable characters, no space or backslash."
        )


# --- the unsubscribe token -------------------------------------------------------------

_PURPOSE = "notifications.unsubscribe"
_HEX = re.compile(r"[0-9a-f]{32}")
_MAC = re.compile(r"[0-9a-f]{64}")


def unsubscribe_token(user_id: uuid.UUID, key: str) -> str:
    """`<person>.<key>.<mac>`: names the person and the key, signed."""
    return f"{user_id.hex}.{key}.{keyed_hash(_PURPOSE, str(user_id), key)}"


def read_token(token: str) -> tuple[uuid.UUID, str] | None:
    """The person and key a token names, or None for one the kernel didn't sign."""
    person, dot, rest = token.partition(".")
    key, dot_too, mac = rest.rpartition(".")
    if not (dot and dot_too and _HEX.fullmatch(person) and _MAC.fullmatch(mac)):
        return None
    user_id = uuid.UUID(hex=person)
    if not same(mac, keyed_hash(_PURPOSE, str(user_id), key)):
        return None
    return user_id, key


# --- notify --------------------------------------------------------------------------


async def _choice(db: AsyncSession, user_id: uuid.UUID, kind: Kind) -> tuple[bool, bool]:
    found = (
        await db.execute(
            select(NotificationPreference.in_site, NotificationPreference.email).where(
                NotificationPreference.user_id == user_id, NotificationPreference.key == kind.key
            )
        )
    ).one_or_none()
    return (found.in_site, found.email) if found is not None else (kind.in_site, kind.email)


async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    key: str,
    context: Mapping[str, str | int],
    *,
    link: str | None = None,
) -> Sent:
    """Adds the notice and queues its email in the caller's transaction, as
    the person chose for `key`. Returns where it went."""
    kind = _kind(key)
    values: dict[str, str | int] = dict(context)
    if link is not None:
        _check_link(link)
        values["link"] = email.site_url() + link
    rendered = email.render(key, values)
    if len(rendered.subject) > email.MAX_SUBJECT:
        raise ValueError(f"The notification {key}'s title is past {email.MAX_SUBJECT} characters.")
    person = (
        await db.execute(
            select(User.email, User.email_verified_at, User.status).where(User.id == user_id)
        )
    ).one_or_none()
    if person is None or person.status != "active":
        return Sent(False, False)
    in_site, by_email = await _choice(db, user_id, kind)
    by_email = by_email and person.email_verified_at is not None
    if in_site:
        db.add(
            Notification(
                user_id=user_id, key=key, title=rendered.subject, link=link, created_at=clock.now()
            )
        )
    if by_email:
        await _queue(db, user_id, key, person.email, rendered)
    return Sent(in_site, by_email)


async def _queue(
    db: AsyncSession, user_id: uuid.UUID, key: str, address: str, rendered: email.Rendered
) -> None:
    base = email.site_url()
    token = unsubscribe_token(user_id, key)
    footer = email.render(
        FOOTER,
        {
            "unsubscribe_url": f"{base}{UNSUBSCRIBE_PAGE}?token={token}",
            "settings_url": f"{base}{SETTINGS_PAGE}",
        },
    )
    text = rendered.text + footer.text
    html = None if rendered.html is None else rendered.html + (footer.html or "")
    headers = {
        "List-Unsubscribe": f"<{base}{UNSUBSCRIBE_API}?token={token}>",
        "List-Unsubscribe-Post": ONE_CLICK,
    }
    await email.queue_message(db, address, rendered.subject, text, html, headers)


# --- reading and choosing (the routes' work) --------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DIGITS = re.compile(r"[0-9]{1,19}")


def _bad_cursor() -> Problem:
    return Problem(
        "kernel.invalid_request",
        422,
        "Some of what was sent isn't valid.",
        errors={"cursor": ["Not a page of your notices."]},
    )


def _cursor_of(notice: Notification) -> str:
    micros = (notice.created_at - _EPOCH) // timedelta(microseconds=1)
    return f"{micros}.{notice.id.hex}"


def _after(cursor: str) -> tuple[datetime, uuid.UUID]:
    micros, dot, ident = cursor.partition(".")
    try:
        if not (dot and _DIGITS.fullmatch(micros) and _HEX.fullmatch(ident)):
            raise ValueError(cursor)
        return _EPOCH + timedelta(microseconds=int(micros)), uuid.UUID(hex=ident)
    except (ValueError, OverflowError):
        raise _bad_cursor() from None


def view(notice: Notification) -> dict[str, Any]:
    return {
        "id": str(notice.id),
        "key": notice.key,
        "title": notice.title,
        "link": notice.link,
        "created_at": notice.created_at.isoformat(),
        "read_at": notice.read_at.isoformat() if notice.read_at else None,
    }


async def listed(
    db: AsyncSession, user_id: uuid.UUID, *, cursor: str | None, limit: int
) -> dict[str, Any]:
    """A page of the person's notices, newest first, and how many are unread."""
    query = select(Notification).where(Notification.user_id == user_id)
    if cursor is not None:
        at, ident = _after(cursor)
        query = query.where(
            (Notification.created_at < at)
            | ((Notification.created_at == at) & (Notification.id < ident))
        )
    query = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
    found = list((await db.scalars(query)).all())
    page = found[:limit]
    unread = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return {
        "items": [view(notice) for notice in page],
        "next_cursor": _cursor_of(page[-1]) if len(found) > limit else None,
        "unread": unread or 0,
    }


async def mark_read(db: AsyncSession, user_id: uuid.UUID, ids: Sequence[uuid.UUID] | None) -> None:
    """Marks the person's own notices read: `ids`, or all of them for None."""
    query = update(Notification).where(
        Notification.user_id == user_id, Notification.read_at.is_(None)
    )
    if ids is not None:
        query = query.where(Notification.id.in_(ids))
    await db.execute(query.values(read_at=clock.now()))
    await db.commit()


async def preferences(
    db: AsyncSession, user_id: uuid.UUID, on: Iterable[str]
) -> list[dict[str, Any]]:
    """Every key of the modules on, with the person's choice for it."""
    allowed = set(on)
    shown = [kind for kind in _kinds.values() if kind.module in allowed]
    rows = await db.execute(
        select(
            NotificationPreference.key, NotificationPreference.in_site, NotificationPreference.email
        ).where(NotificationPreference.user_id == user_id)
    )
    chosen = {row.key: (row.in_site, row.email) for row in rows}
    out = []
    for kind in shown:
        in_site, by_email = chosen.get(kind.key, (kind.in_site, kind.email))
        out.append(
            {
                "key": kind.key,
                "description": kind.description,
                "default": kind.default,
                "in_site": in_site,
                "email": by_email,
            }
        )
    return out


async def _set(
    db: AsyncSession, user_id: uuid.UUID, key: str, in_site: bool, by_email: bool
) -> None:
    statement = insert(NotificationPreference).values(
        user_id=user_id, key=key, in_site=in_site, email=by_email, updated_at=clock.now()
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=["user_id", "key"],
            set_={"in_site": in_site, "email": by_email, "updated_at": clock.now()},
        )
    )


async def choose(
    db: AsyncSession,
    user_id: uuid.UUID,
    changes: Mapping[str, tuple[bool, bool]],
    on: Iterable[str],
) -> None:
    """Saves the person's choices. Problem 422, saving nothing, for a key
    that isn't one of a module on."""
    allowed = set(on)
    unknown = sorted(
        key for key in changes if key not in _kinds or _kinds[key].module not in allowed
    )
    if unknown:
        raise Problem(
            "kernel.invalid_request",
            422,
            "Some of what was sent isn't valid.",
            errors={key: ["Not a notification you can choose."] for key in unknown},
        )
    for key, (in_site, by_email) in changes.items():
        await _set(db, user_id, key, in_site, by_email)
    await db.commit()


def _not_found() -> Problem:
    return Problem("kernel.not_found", 404, "This unsubscribe link isn't valid.")


async def _from_token(db: AsyncSession, token: str) -> tuple[uuid.UUID, Kind]:
    named = read_token(token)
    if named is None or named[1] not in _kinds:
        raise _not_found()
    user_id, key = named
    if await db.scalar(select(User.id).where(User.id == user_id)) is None:
        raise _not_found()
    return user_id, _kinds[key]


async def looked_up(db: AsyncSession, token: str) -> dict[str, Any]:
    """What a token would turn off, changing nothing (link scanners open links)."""
    user_id, kind = await _from_token(db, token)
    _, by_email = await _choice(db, user_id, kind)
    return {"key": kind.key, "description": kind.description, "email": by_email}


async def unsubscribe(db: AsyncSession, token: str) -> None:
    """Turns email off for the token's key alone; the site's notices stay as chosen."""
    user_id, kind = await _from_token(db, token)
    in_site, _ = await _choice(db, user_id, kind)
    await _set(db, user_id, kind.key, in_site, False)
    await db.commit()


# --- the kernel's own job: pruning -------------------------------------------------------


async def _prune(ctx: jobs.Context) -> None:
    """Deletes notices read 90 days ago and any a year old, in batches."""
    now = clock.now()
    gone = or_(Notification.read_at < now - KEEP_READ, Notification.created_at < now - KEEP_LONGEST)
    while True:
        async with ctx.sessions() as db:
            doomed = select(Notification.id).where(gone).limit(BATCH)
            result = await db.execute(delete(Notification).where(Notification.id.in_(doomed)))
            await db.commit()
        if getattr(result, "rowcount", 0) < BATCH:
            return


PRUNE = jobs.scheduled("7 4 * * *", "kernel.prune_notifications", timeout=900)(_prune)
