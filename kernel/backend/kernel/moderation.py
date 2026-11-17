"""Moderation: reports, the staff queue, word and link filters, actions and
suspension (SPEC.md 6 and 14.7; decision 0039; contract
dev plans/contracts/k3-moderation.md).

**A module declares what can be reported** in its `moderation.py`, and lists
the classes on `InstalledModule(reportable=...)`; the start refuses a kind its
module doesn't own:

    @moderation.kind("comments.comment", actions=("hide", "delete"))
    class Comment(moderation.Kind):
        async def describe(self, db, id): ...   # an Item, or None: no such thing
        async def apply(self, db, id, action): ...   # in the caller's transaction

**Reports.** `report` opens the thing's case, or adds to the open one: one
case per thing is open, holding the excerpt as it was first reported, and a
person reports it once. The filters' `check` (`screen` reads the saved
filters) holds text on a held term, a blocked domain or too many links; the
module keeps held text out of sight and calls `hold`, which opens a case whose
report is the filters'. Nothing is ever dropped, and the poster gets the same
answer either way (VybeSite's contact filter).

**Actions** (`act`): dismiss; hide or delete, which the kind's `apply` does in
the same transaction as the case closing; a time-out from posting
(`auth_user.timed_out_until`, checked by `Depends(can_post)`); and a ban, which
suspends the account. Nobody acts on a case about what they wrote; staff
aren't timed out or banned here, and their content is hidden only by someone
holding every permission they hold (decision 0013's rule). Each action is
audited, and the author is told why, never by whom.

**Suspension** (`suspend`, `restore`; 14.7): `status` and a new session epoch,
so every session ends; audited, emitted as `auth.user.suspended` and
`auth.user.restored`, and mailed. Only an owner suspends an owner, nobody
themselves (so never the last owner), and only someone holding every
permission the person holds.

**Pruning:** `kernel.prune_moderation`, daily, deletes cases closed more than
AUDIT_KEEP_DAYS ago, with their reports.
"""

from __future__ import annotations

import abc
import functools
import re
import unicodedata
import uuid
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, TypeVar, cast

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import ColumnElement, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit, clock, email, events, jobs, notifications
from kernel.auth.dependencies import current_user
from kernel.auth.mails import when
from kernel.auth.models import RolePermission, User
from kernel.auth.permissions import OWNER, can, roles_of
from kernel.errors import Problem
from kernel.models import AuditEvent, ModerationCase, ModerationReport
from kernel.modules import OFF
from kernel.settings import settings

#: Why a person reports something, and why staff act on it.
REASONS = ("spam", "harassment", "hate", "sexual", "violence", "self_harm", "illegal", "other")
#: The reason on the filters' own report, and why the filters held text.
FILTER = "filter"
FILTER_REASONS = ("term", "domain", "links")
#: The actions a kind may carry out itself; the kernel does the rest.
CONTENT_ACTIONS = ("hide", "delete")
ACTIONS = ("dismiss", "hide", "delete", "time_out", "ban")
STATUSES = ("open", "actioned", "dismissed")
SOURCES = ("report", "filter")

MAX_ID = 64
MAX_EXCERPT = 1000
MAX_NOTE = 1000
MAX_LINK = 500
#: A time-out runs an hour to 30 days, in minutes.
MIN_TIME_OUT = 60
MAX_TIME_OUT = 43_200
REPORTS_PER_HOUR = "20/1h"
BATCH = 1000

#: The filters' settings section, saved through `settings.save`.
SECTION = "kernel.moderation"
#: The notice a removal sends, and the two mails that always go.
NOTICE = "kernel.content_removed"
TIMED_OUT_MAIL = "kernel.timed_out"
SUSPENDED_MAIL = "kernel.account_suspended"

#: `<module id>.<entity>`: a kind's name.
KIND = re.compile(r"([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.[a-z][a-z0-9_]*")

#: How a reason reads in a mail: "... removed for $reason."
_SAID = {
    "spam": "spam",
    "harassment": "harassment",
    "hate": "hate speech",
    "sexual": "sexual content",
    "violence": "violence",
    "self_harm": "content about self-harm",
    "illegal": "illegal content",
    "other": "breaking the site's rules",
}

_REPLY = "If you think this is a mistake, reply to this email.\n"

#: The kernel's own templates: the removal notice (its subject is the
#: notice's title) and the two mails a person can't turn off.
TEMPLATES = {
    NOTICE: email.Template(
        subject="Something you posted was removed",
        text=(
            "Something you posted on $site_name was removed by the site's moderators, "
            "for $reason.\n\n" + _REPLY
        ),
    ),
    TIMED_OUT_MAIL: email.Template(
        subject="You can't post for a while",
        text=(
            "The moderators of $site_name have stopped your account posting until $until, "
            "for $reason. You can still sign in and read.\n\n" + _REPLY
        ),
    ),
    SUSPENDED_MAIL: email.Template(
        subject="Your account is suspended",
        text=(
            "Your $site_name account is suspended, for $reason, and every device was "
            "signed out.\n\n" + _REPLY
        ),
    ),
}

#: The kernel's notification key, as a module's module.json declares its own.
NOTIFICATIONS: list[dict[str, str]] = [
    {
        "key": NOTICE,
        "description": "Something you posted was removed by the moderators",
        "default": "both",
    }
]


# --- declaring kinds ---------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """What a kind says of one thing: who wrote it, its text, and where it is."""

    author_id: uuid.UUID | None
    excerpt: str
    link: str | None = None


class Kind(abc.ABC):
    """A thing a module lets people report. Subclass it, declare it with
    `@moderation.kind`, and list it on `InstalledModule(reportable=...)`."""

    name: ClassVar[str] = ""
    actions: ClassVar[frozenset[str]] = frozenset()

    @property
    def owner(self) -> str:
        return self.name.partition(".")[0]

    @abc.abstractmethod
    async def describe(self, db: AsyncSession, id: str) -> Item | None:
        """The thing as it is now, or None when there's no such thing."""

    @abc.abstractmethod
    async def apply(self, db: AsyncSession, id: str, action: str) -> None:
        """Hides or deletes the thing (`action`, one the kind lists), in the
        caller's transaction."""

    async def dismissed(self, db: AsyncSession, id: str) -> None:
        """Staff found nothing wrong, in the caller's transaction: show the
        thing again if the module held it (`hold`). Nothing by default."""
        return None


K = TypeVar("K", bound=type[Kind])


def kind(name: str, *, actions: Iterable[str] = ()) -> Callable[[K], K]:
    """Declares the class below as the kind `name`, which carries out `actions`
    (hide, delete, or neither)."""
    if not (isinstance(name, str) and len(name) <= MAX_ID and KIND.fullmatch(name)):
        raise ValueError(
            "A kind's name is <module id>.<entity>, lowercase, at most "
            f"{MAX_ID} characters, not {name!r}."
        )
    chosen = frozenset(actions)
    if not chosen <= set(CONTENT_ACTIONS):
        raise ValueError(
            f"A kind's own actions are hide and delete; {name} lists {sorted(chosen)}."
        )

    def declare(cls: K) -> K:
        if not (isinstance(cls, type) and issubclass(cls, Kind)):
            raise TypeError(f"{name} must be a class that subclasses moderation.Kind.")
        cls.name = name
        cls.actions = chosen
        return cls

    return declare


def build(declared: Iterable[tuple[str, Iterable[type[Kind]]]]) -> dict[str, Kind]:
    """Every kind, from (module id, its `reportable`) pairs. ValueError,
    naming the kind, on any the start can't take."""
    kinds: dict[str, Kind] = {}
    for owner, classes in declared:
        for cls in classes:
            if not (isinstance(cls, type) and issubclass(cls, Kind) and cls.name):
                raise ValueError(
                    f"{owner}'s {getattr(cls, '__name__', cls)} isn't declared with "
                    "@moderation.kind."
                )
            if cls.name.partition(".")[0] != owner:
                raise ValueError(f"{owner} may only declare {owner}.* kinds, not {cls.name}.")
            if cls.name in kinds:
                raise ValueError(f"The kind {cls.name} is declared twice.")
            try:
                kinds[cls.name] = cls()
            except TypeError:
                raise ValueError(f"The kind {cls.name} needs both describe and apply.") from None
    return kinds


_kinds: dict[str, Kind] = {}


def install(kinds: Mapping[str, Kind]) -> None:
    """Sets the kinds the kernel knows: `create_app` and `create_worker` call it."""
    global _kinds
    _kinds = dict(kinds)


def named(name: str) -> Kind | None:
    """The installed kind `name`, or None."""
    return _kinds.get(name)


# --- small checks --------------------------------------------------------------------


def no_target() -> Problem:
    return Problem("kernel.report_target_unknown", 404, "There's nothing like that to report.")


def _invalid(name: str, message: str) -> Problem:
    return Problem(
        "kernel.invalid_request",
        422,
        "Some of what was sent isn't valid.",
        errors={name: [message]},
    )


def _refused(detail: str) -> Problem:
    return Problem("kernel.moderation_refused", 403, detail)


def _target(target: tuple[str, str | int | uuid.UUID]) -> tuple[Kind, str]:
    kind_name, ident = target
    if isinstance(ident, bool) or not isinstance(ident, str | int | uuid.UUID):
        raise ValueError("A thing's id is text, a whole number or a UUID.")
    text = str(ident)
    if not 1 <= len(text) <= MAX_ID or chr(0) in text:
        raise ValueError(f"A thing's id is 1 to {MAX_ID} characters.")
    found = _kinds.get(kind_name) if isinstance(kind_name, str) else None
    if found is None:
        raise no_target()
    return found, text


def _note(note: str | None) -> None:
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE or chr(0) in note):
        raise ValueError(f"A note is text of at most {MAX_NOTE} characters.")


def _item(item: Item) -> tuple[str, str | None]:
    """The excerpt and link a case keeps."""
    link = item.link
    if link is not None and not (
        isinstance(link, str) and link.startswith("/") and len(link) <= MAX_LINK
    ):
        raise ValueError(f"A thing's link is a path on this site of at most {MAX_LINK} characters.")
    return item.excerpt.replace(chr(0), "")[:MAX_EXCERPT], link


# --- reporting -----------------------------------------------------------------------


async def _open_case(db: AsyncSession, found: Kind, ident: str, source: str) -> uuid.UUID:
    item = await found.describe(db, ident)
    if item is None:
        raise no_target()
    excerpt, link = _item(item)
    now = clock.now()
    statement = insert(ModerationCase).values(
        id=uuid.uuid4(),
        target_type=found.name,
        target_id=ident,
        source=source,
        status="open",
        author_id=item.author_id,
        excerpt=excerpt,
        link=link,
        report_count=0,
        opened_at=now,
        last_report_at=now,
    )
    # The open case, made or found: the update only locks it and gives its id.
    # The predicate is literal: as a bound value, Postgres can't match it to
    # the partial index once a prepared statement turns generic (the 6th run).
    upsert = statement.on_conflict_do_update(
        index_elements=["target_type", "target_id"],
        index_where=text("status = 'open'"),
        set_={"target_type": statement.excluded.target_type},
    ).returning(ModerationCase.id)
    case_id: uuid.UUID = (await db.execute(upsert)).scalar_one()
    return case_id


async def _count(db: AsyncSession, case_id: uuid.UUID) -> None:
    await db.execute(
        update(ModerationCase)
        .where(ModerationCase.id == case_id)
        .values(report_count=ModerationCase.report_count + 1, last_report_at=clock.now())
    )


async def report(
    db: AsyncSession,
    target: tuple[str, str | int | uuid.UUID],
    *,
    reporter: uuid.UUID,
    reason: str,
    note: str | None = None,
) -> uuid.UUID:
    """Reports the thing `target` names, in the caller's transaction, and
    returns its open case. A second report from the same person changes
    nothing. Problem 404 when there's no such thing to report."""
    found, ident = _target(target)
    if reason not in REASONS:
        raise ValueError(f"A report's reason is one of {', '.join(REASONS)}.")
    _note(note)
    case_id = await _open_case(db, found, ident, "report")
    added = await db.scalar(
        insert(ModerationReport)
        .values(case_id=case_id, reporter_id=reporter, reason=reason, note=note, at=clock.now())
        .on_conflict_do_nothing(index_elements=["case_id", "reporter_id"])
        .returning(ModerationReport.id)
    )
    if added is not None:
        await _count(db, case_id)
    return case_id


async def hold(
    db: AsyncSession, target: tuple[str, str | int | uuid.UUID], *, reasons: Sequence[str]
) -> uuid.UUID:
    """Puts text the filters held in front of staff: its open case, with the
    filters' report naming why (`Screen.reasons`)."""
    found, ident = _target(target)
    chosen = tuple(reasons)
    if not chosen or not set(chosen) <= set(FILTER_REASONS):
        raise ValueError(f"A hold names the filters' reasons: {', '.join(FILTER_REASONS)}.")
    case_id = await _open_case(db, found, ident, "filter")
    db.add(
        ModerationReport(
            case_id=case_id, reporter_id=None, reason=FILTER, note=", ".join(chosen), at=clock.now()
        )
    )
    await _count(db, case_id)
    return case_id


# --- the filters ----------------------------------------------------------------------

_TERM = Annotated[str, StringConstraints(min_length=1, max_length=64)]
_DOMAIN = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


class Filters(BaseModel):
    """The filters a site sets (the settings section `kernel.moderation`)."""

    model_config = ConfigDict(extra="forbid")

    #: Words or phrases, matched whole-word after NFKC and case folding.
    held_terms: list[_TERM] = Field(default_factory=list, max_length=500)
    #: A link to one of these, or to any subdomain, is held.
    blocked_domains: list[str] = Field(default_factory=list, max_length=500)
    #: Text with more links than this is held.
    max_links: int = Field(default=2, ge=0, le=100)

    @field_validator("held_terms")
    @classmethod
    def _terms(cls, value: list[str]) -> list[str]:
        if any(not term.strip() for term in value):
            raise ValueError("A held term isn't blank.")
        return value

    @field_validator("blocked_domains")
    @classmethod
    def _domains(cls, value: list[str]) -> list[str]:
        out = []
        for given in value:
            name = given.strip().lower().rstrip(".")
            if not _DOMAIN.fullmatch(name):
                raise ValueError(f"{given!r} isn't a domain name, such as spam.example.")
            out.append(name)
        return out


@dataclass(frozen=True)
class Screen:
    """The filters' verdict on some text."""

    hold: bool
    reasons: tuple[str, ...]


#: Anything shaped like a host name: in a link, an address, or bare.
_HOST = re.compile(r"(?<![\w.-])[\w-]+(?:\.[\w-]+)+")
#: A link: a scheme or www. to the next space.
_LINK = re.compile(r"(?<![\w.-])(?:https?://|www\.)[^\s<>\"']+")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


@functools.lru_cache(maxsize=2048)
def _term(term: str) -> re.Pattern[str]:
    words = _fold(term).split()
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, words)) + r"(?!\w)")


def check(filters: Filters, text: str) -> Screen:
    """Whether `filters` hold `text`, and why: a held term, a blocked domain,
    too many links, in that order."""
    folded = _fold(text)
    reasons = []
    if any(_term(term).search(folded) for term in filters.held_terms):
        reasons.append("term")
    hosts = set(_HOST.findall(folded))
    blocked = filters.blocked_domains
    if any(host == name or host.endswith("." + name) for host in hosts for name in blocked):
        reasons.append("domain")
    if len(_LINK.findall(folded)) > filters.max_links:
        reasons.append("links")
    return Screen(bool(reasons), tuple(reasons))


async def screen(db: AsyncSession, text: str) -> Screen:
    """`check` against the site's saved filters."""
    filters = cast(Filters, await settings.for_module(db, SECTION))
    return check(filters, text)


# --- who may act on whom --------------------------------------------------------------


async def _held(db: AsyncSession, roles: set[str]) -> set[str]:
    if not roles:
        return set()
    found = await db.scalars(
        select(RolePermission.permission).where(RolePermission.role_id.in_(roles))
    )
    return set(found)


async def _outranked(db: AsyncSession, actor: uuid.UUID, person: uuid.UUID) -> bool:
    """Whether `actor` may act on `person`'s account or content: an owner only
    by an owner, anyone else by someone holding every permission they hold
    (decision 0013's rule)."""
    actor_roles = await roles_of(db, actor)
    # What every member holds is no rank: a module's permission for members
    # mustn't stop an admin suspending one.
    their_roles = await roles_of(db, person) - {"member"}
    if OWNER in actor_roles:
        return True
    if OWNER in their_roles:
        return False
    return await _held(db, their_roles) <= await _held(db, actor_roles)


async def _is_staff(db: AsyncSession, person: uuid.UUID) -> bool:
    return bool(await roles_of(db, person) - {"member"})


async def _person(db: AsyncSession, user_id: uuid.UUID) -> User:
    found = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if found is None:
        raise Problem("kernel.not_found", 404, "There's no such person.")
    return found


def _said(reason: str) -> str:
    return _SAID[reason]


# --- time-outs ------------------------------------------------------------------------


def _check_minutes(minutes: object) -> int:
    if (
        isinstance(minutes, bool)
        or not isinstance(minutes, int)
        or not MIN_TIME_OUT <= minutes <= MAX_TIME_OUT
    ):
        raise _invalid(
            "minutes", f"A time-out is {MIN_TIME_OUT} to {MAX_TIME_OUT} minutes (30 days)."
        )
    return minutes


def _check_reason(reason: object) -> str:
    if not isinstance(reason, str) or reason not in REASONS:
        raise _invalid("reason", f"One of {', '.join(REASONS)}.")
    return reason


async def _guard_person(db: AsyncSession, actor: User, person: uuid.UUID) -> None:
    if person == actor.id:
        raise _refused("You can't act on yourself.")
    if await _is_staff(db, person):
        raise _refused(
            "Staff aren't timed out or banned here: an admin suspends them from the People page."
        )


async def _time_out(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor: User,
    minutes: int,
    reason: str,
    case: uuid.UUID | None,
) -> datetime:
    person = await _person(db, user_id)
    until = clock.now() + timedelta(minutes=minutes)
    person.timed_out_until = until
    details: dict[str, Any] = {"reason": reason, "minutes": minutes}
    if case is not None:
        details["case"] = str(case)
    audit.record(
        db,
        "kernel.moderation.timed_out",
        actor=actor.id,
        target=("auth.user", user_id),
        subject=user_id,
        details=details,
    )
    await email.queue(
        db, TIMED_OUT_MAIL, person.email, {"until": when(until), "reason": _said(reason)}
    )
    return until


async def time_out(
    db: AsyncSession, user_id: uuid.UUID, *, actor: User, minutes: int, reason: str
) -> datetime:
    """Stops a member posting for `minutes` (60 to 43,200), in the caller's
    transaction, and returns when it ends. They still sign in and read."""
    _check_minutes(minutes)
    _check_reason(reason)
    await _guard_person(db, actor, user_id)
    return await _time_out(db, user_id, actor=actor, minutes=minutes, reason=reason, case=None)


async def lift_time_out(db: AsyncSession, user_id: uuid.UUID, *, actor: User) -> None:
    """Lets the person post again; a time-out that already ended changes nothing."""
    person = await _person(db, user_id)
    running = person.timed_out_until is not None and person.timed_out_until > clock.now()
    person.timed_out_until = None
    if running:
        audit.record(
            db,
            "kernel.moderation.time_out_lifted",
            actor=actor.id,
            target=("auth.user", user_id),
            subject=user_id,
        )


async def can_post(user: User = Depends(current_user)) -> User:
    """The signed-in account, or 403 `kernel.timed_out` (with `until`) while
    a time-out runs. Every route of a module that posts uses it."""
    until = user.timed_out_until
    if until is not None and until > clock.now():
        raise Problem(
            "kernel.timed_out",
            403,
            "You can't post until your time-out ends.",
            extra={"until": until.isoformat()},
        )
    return user


# --- suspension -----------------------------------------------------------------------


async def _may_change(db: AsyncSession, actor: User, user_id: uuid.UUID) -> User:
    """The person's row, once the actor may change it. The codes are auth's,
    as docs/contracts/auth-api.md has them.

    Both rows are locked, in id order, and the actor must still be active:
    two owners suspending each other at once can't both commit and leave no
    active owner (CodeRabbit on #71). The second waits, then finds its actor
    suspended."""
    if user_id == actor.id:
        raise Problem("auth.not_yourself", 403, "You can't suspend or restore yourself.")
    rows = await db.scalars(
        select(User)
        .where(User.id.in_([actor.id, user_id]))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    found = {row.id: row for row in rows}
    if user_id not in found:
        raise Problem("kernel.not_found", 404, "There's no such person.")
    acting = found.get(actor.id)
    if acting is None or acting.status != "active":
        raise Problem("auth.account_not_active", 409, "Your account is no longer active.")
    if not await _outranked(db, actor.id, user_id):
        raise Problem(
            "auth.role_not_yours",
            403,
            "Only an owner suspends or restores an owner, and anyone else only by "
            "someone holding every permission they hold.",
        )
    return found[user_id]


def _not_active() -> Problem:
    return Problem("auth.account_not_active", 409, "This account is being deleted.")


async def suspend(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor: User,
    reason: str,
    request: Request | None = None,
    case: uuid.UUID | None = None,
) -> None:
    """Suspends the account in the caller's transaction: every session ends,
    the person is mailed why, and `auth.user.suspended` is emitted. One
    already suspended changes nothing."""
    _check_reason(reason)
    person = await _may_change(db, actor, user_id)
    if person.status == "suspended":
        return
    if person.status != "active":
        raise _not_active()
    person.status = "suspended"
    person.session_epoch += 1
    details: dict[str, Any] = {"reason": reason}
    if case is not None:
        details["case"] = str(case)
    audit.record(
        db,
        "auth.user.suspended",
        actor=actor.id,
        target=("auth.user", user_id),
        subject=user_id,
        details=details,
        request=request,
    )
    await events.emit(db, "auth.user.suspended", events.UserSuspended(user_id=user_id))
    await email.queue(db, SUSPENDED_MAIL, person.email, {"reason": _said(reason)})


async def restore(
    db: AsyncSession, user_id: uuid.UUID, *, actor: User, request: Request | None = None
) -> None:
    """Restores a suspended account in the caller's transaction and emits
    `auth.user.restored`; its sessions stay ended. One already active changes nothing."""
    person = await _may_change(db, actor, user_id)
    if person.status == "active":
        return
    if person.status != "suspended":
        raise _not_active()
    person.status = "active"
    audit.record(
        db,
        "auth.user.restored",
        actor=actor.id,
        target=("auth.user", user_id),
        subject=user_id,
        request=request,
    )
    await events.emit(db, "auth.user.restored", events.UserRestored(user_id=user_id))


# --- acting on a case -----------------------------------------------------------------


async def _tell_removed(db: AsyncSession, author: uuid.UUID | None, reason: str) -> None:
    if author is not None:
        await notifications.notify(db, author, NOTICE, {"reason": _said(reason)})


async def act(
    db: AsyncSession,
    case_id: uuid.UUID,
    action: str,
    *,
    actor: User,
    reason: str | None = None,
    note: str | None = None,
    minutes: int | None = None,
    on: Collection[str] | None = None,
) -> None:
    """Acts on an open case in the caller's transaction and closes it. The
    route checks `kernel.moderation.act`; a ban also needs `auth.user.suspend`.
    `on`, when given, is the modules on: a case whose module is off is 404."""
    case = await db.scalar(
        select(ModerationCase)
        .where(ModerationCase.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if case is None:
        raise Problem("kernel.not_found", 404, "There's no such case.")
    found = _kinds.get(case.target_type)
    if found is None or (on is not None and found.owner not in on):
        raise Problem("kernel.module_off", 404, OFF)
    if case.status != "open":
        raise Problem("kernel.case_closed", 409, "This case is already closed.")
    if action not in ACTIONS or (action in CONTENT_ACTIONS and action not in found.actions):
        raise _invalid(
            "action", f"One of {', '.join(sorted(found.actions | {'dismiss', 'time_out', 'ban'}))}."
        )
    if reason is not None or action != "dismiss":
        _check_reason(reason)
    try:
        _note(note)
    except ValueError as error:
        raise _invalid("note", str(error)) from None
    if action == "time_out":
        _check_minutes(minutes)
    if action == "ban" and not await can(db, actor.id, "auth.user.suspend"):
        raise Problem("kernel.forbidden", 403, "Banning needs auth.user.suspend.")
    author = case.author_id
    if author == actor.id:
        raise _refused("You can't act on a case about something you wrote.")
    if action in ("time_out", "ban"):
        if author is None:
            raise _refused("Nobody wrote it, so there's no one to time out or ban.")
        await _guard_person(db, actor, author)
    elif (
        action in CONTENT_ACTIONS
        and author is not None
        and await _is_staff(db, author)
        and not await _outranked(db, actor.id, author)
    ):
        raise _refused("This was written by staff holding a permission you don't.")

    target = (case.target_type, case.target_id)
    details = {"case": str(case.id), "reason": reason}
    if action == "dismiss":
        await found.dismissed(db, case.target_id)
        audit.record(
            db,
            "kernel.moderation.dismissed",
            actor=actor.id,
            target=target,
            subject=author,
            details=details,
        )
    elif action == "hide":
        await found.apply(db, case.target_id, "hide")
        audit.record(
            db,
            "kernel.moderation.hidden",
            actor=actor.id,
            target=target,
            subject=author,
            details=details,
        )
        await _tell_removed(db, author, cast(str, reason))
    elif action == "delete":
        await found.apply(db, case.target_id, "delete")
        audit.record(
            db,
            "kernel.moderation.deleted",
            actor=actor.id,
            target=target,
            subject=author,
            details=details,
        )
        await _tell_removed(db, author, cast(str, reason))
    elif action == "time_out":
        await _time_out(
            db,
            cast(uuid.UUID, author),
            actor=actor,
            minutes=cast(int, minutes),
            reason=cast(str, reason),
            case=case.id,
        )
    else:
        await suspend(
            db, cast(uuid.UUID, author), actor=actor, reason=cast(str, reason), case=case.id
        )
    case.status = "dismissed" if action == "dismiss" else "actioned"
    case.closed_at = clock.now()
    case.closed_by = actor.id
    case.outcome = action


# --- reading: the queue and the moderators' log -------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DIGITS = re.compile(r"[0-9]{1,19}")
_HEX = re.compile(r"[0-9a-f]{32}")


def _cursor_of(case: ModerationCase) -> str:
    micros = (case.last_report_at - _EPOCH) // timedelta(microseconds=1)
    return f"{micros}.{case.id.hex}"


def _after(cursor: str) -> tuple[datetime, uuid.UUID]:
    micros, dot, ident = cursor.partition(".")
    try:
        if not (dot and _DIGITS.fullmatch(micros) and _HEX.fullmatch(ident)):
            raise ValueError(cursor)
        return _EPOCH + timedelta(microseconds=int(micros)), uuid.UUID(hex=ident)
    except (ValueError, OverflowError):
        raise _invalid("cursor", "Not a page of the queue.") from None


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def _view(case: ModerationCase, reasons: Mapping[str, int]) -> dict[str, Any]:
    return {
        "id": str(case.id),
        "target": {"type": case.target_type, "id": case.target_id},
        "source": case.source,
        "status": case.status,
        "author_id": str(case.author_id) if case.author_id else None,
        "excerpt": case.excerpt,
        "link": case.link,
        "report_count": case.report_count,
        "reasons": dict(reasons),
        "opened_at": _iso(case.opened_at),
        "last_report_at": _iso(case.last_report_at),
        "closed_at": _iso(case.closed_at),
        "closed_by": str(case.closed_by) if case.closed_by else None,
        "outcome": case.outcome,
    }


async def _reasons(db: AsyncSession, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    rows = await db.execute(
        select(ModerationReport.case_id, ModerationReport.reason, func.count())
        .where(ModerationReport.case_id.in_(ids))
        .group_by(ModerationReport.case_id, ModerationReport.reason)
        .order_by(ModerationReport.reason)
    )
    out: dict[uuid.UUID, dict[str, int]] = {}
    for case_id, reason, count in rows:
        out.setdefault(case_id, {})[reason] = count
    return out


async def listed(
    db: AsyncSession,
    *,
    status: str = "open",
    kind: str | None = None,
    source: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """A page of the queue, the latest report first (SPEC 7's list shape)."""
    where: list[ColumnElement[bool]] = [ModerationCase.status == status]
    if kind is not None:
        where.append(ModerationCase.target_type == kind)
    if source is not None:
        where.append(ModerationCase.source == source)
    if cursor is not None:
        at, ident = _after(cursor)
        where.append(
            (ModerationCase.last_report_at < at)
            | ((ModerationCase.last_report_at == at) & (ModerationCase.id < ident))
        )
    query = (
        select(ModerationCase)
        .where(*where)
        .order_by(ModerationCase.last_report_at.desc(), ModerationCase.id.desc())
        .limit(limit + 1)
        .execution_options(populate_existing=True)
    )
    found = list((await db.scalars(query)).all())
    page = found[:limit]
    reasons = await _reasons(db, [case.id for case in page])
    return {
        "items": [_view(case, reasons.get(case.id, {})) for case in page],
        "next_cursor": _cursor_of(page[-1]) if len(found) > limit else None,
    }


async def case(db: AsyncSession, case_id: uuid.UUID) -> dict[str, Any]:
    """One case, with every report on it, oldest first. Problem 404 for none."""
    found = await db.scalar(
        select(ModerationCase)
        .where(ModerationCase.id == case_id)
        .execution_options(populate_existing=True)
    )
    if found is None:
        raise Problem("kernel.not_found", 404, "There's no such case.")
    reports = list(
        (
            await db.scalars(
                select(ModerationReport)
                .where(ModerationReport.case_id == case_id)
                .order_by(ModerationReport.id)
            )
        ).all()
    )
    view = _view(found, (await _reasons(db, [case_id])).get(case_id, {}))
    view["reports"] = [
        {
            "reporter_id": str(report.reporter_id) if report.reporter_id else None,
            "reason": report.reason,
            "note": report.note,
            "at": report.at.isoformat(),
        }
        for report in reports
    ]
    return view


#: What the moderators' log shows: moderation, and suspensions.
LOGGED: ColumnElement[bool] = or_(
    AuditEvent.action.startswith("kernel.moderation."),
    AuditEvent.action.in_(("auth.user.suspended", "auth.user.restored")),
)


def log_item(entry: AuditEvent) -> dict[str, Any]:
    """An entry as the moderators' log answers it: no address, no browser."""
    shown = audit.item(entry)
    del shown["ip"], shown["user_agent"]
    return shown


# --- the kernel's own job: pruning --------------------------------------------------------


async def _prune(ctx: jobs.Context) -> None:
    """Deletes cases closed more than AUDIT_KEEP_DAYS ago, with their reports, in batches."""
    cutoff = clock.now() - audit.keep()
    while True:
        async with ctx.sessions() as db:
            doomed = select(ModerationCase.id).where(ModerationCase.closed_at < cutoff).limit(BATCH)
            result = await db.execute(delete(ModerationCase).where(ModerationCase.id.in_(doomed)))
            await db.commit()
        if getattr(result, "rowcount", 0) < BATCH:
            return


PRUNE = jobs.scheduled("37 4 * * *", "kernel.prune_moderation", timeout=900)(_prune)
