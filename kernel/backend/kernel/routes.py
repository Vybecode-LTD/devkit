"""The kernel's own routes, at /api/kernel: the health check, the modules on,
the staff's audit log (decision 0037), the dashboard's "Needs you" list (K4
contract §2, addition 9), each person's notices (decision 0038), and
moderation: reports, the queue, actions, time-outs and the moderators' log
(decision 0039); and the terms of the vocabularies modules declare, with
staff's changes to them (decision 0052, hook 2); and site search (hook 3)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    field_validator,
)
from sqlalchemy import ColumnElement, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import attention, audit, moderation, notifications, search, server_copy, taxonomy
from kernel.access import public
from kernel.answers import Answer, AuditEntry, Id, TargetRef, When, answer
from kernel.auth import sessions
from kernel.auth.dependencies import current_user, require_permission, signed_in
from kernel.auth.models import Role, User, UserRole
from kernel.db import get_db
from kernel.errors import Problem
from kernel.models import AuditEvent
from kernel.ratelimit import rate_limit
from kernel.version import __version__

log = logging.getLogger(__name__)

router = APIRouter(tags=["kernel"])


# --- what these routes answer (kernel.answers, decision 0042) ---------------------------


class Health(Answer):
    status: Literal["ok", "unavailable"]
    version: str
    database: Literal["ok", "unreachable"]


class ModulesOn(Answer):
    on: list[str]


class Site(Answer):
    """The site's identity as the web app reads it (`useSite`)."""

    name: str
    description: str
    kind: Literal["Organization", "LocalBusiness", "MusicGroup", "Person"]
    logo: str
    card_image: str
    same_as: list[str]


class AuditRole(Answer):
    id: str
    name: str


class AuditPerson(Answer):
    """Someone an entry on the page names, as the Activity page shows them:
    their name if they gave one, else their email, and their roles."""

    name: str | None
    email: str
    roles: list[AuditRole]


class AuditPage(Answer):
    items: list[AuditEntry]
    next_cursor: str | None
    #: Each actor and subject on the page who still has an account, by id.
    people: dict[str, AuditPerson]
    #: How long an entry is kept before it leaves the log on its own.
    kept_days: int


class AttentionAction(Answer):
    label: str
    to: str


class AttentionItem(Answer):
    """One thing that needs the person: what's wrong, why it matters, and
    the page that fixes it."""

    key: str
    tone: Literal["info", "warning", "danger"]
    what: str
    why: str
    action: AttentionAction


class AttentionList(Answer):
    items: list[AttentionItem]


class Notice(Answer):
    id: Id
    key: str
    title: str
    link: str | None
    created_at: When
    read_at: When | None


class Notices(Answer):
    items: list[Notice]
    next_cursor: str | None
    unread: int


class NoticePreference(Answer):
    key: str
    description: str
    default: Literal["in_site", "email", "both"]
    in_site: bool
    email: bool


class NoticePreferences(Answer):
    items: list[NoticePreference]


class UnsubscribeLink(Answer):
    """What a one-click link would turn off."""

    key: str
    description: str
    email: bool


class Unsubscribed(Answer):
    email: bool


class Reported(Answer):
    """The same empty answer for a first report and a repeat."""


class CaseReport(Answer):
    reporter_id: Id | None
    reason: str
    note: str | None
    at: When


class Case(Answer):
    id: Id
    target: TargetRef
    source: Literal["report", "filter"]
    status: Literal["open", "actioned", "dismissed"]
    author_id: Id | None
    excerpt: str
    link: str | None
    report_count: int
    reasons: dict[str, int]
    opened_at: When
    last_report_at: When
    closed_at: When | None
    closed_by: Id | None
    outcome: str | None


class CaseWithReports(Case):
    reports: list[CaseReport]


class Cases(Answer):
    items: list[Case]
    next_cursor: str | None


class TimedOut(Answer):
    until: When


class ModerationLogEntry(Answer):
    """An audit entry as the moderators' log answers it: no address, no browser."""

    id: int
    at: When
    action: str
    result: str
    actor_id: Id | None
    subject_id: Id | None
    target: TargetRef | None
    details: dict[str, Any]


class ModerationLog(Answer):
    items: list[ModerationLogEntry]
    next_cursor: str | None


@router.get(
    "/health",
    dependencies=[Depends(public)],
    response_model=Health,
    responses={503: {"model": Health, "description": "The database didn't answer"}},
)
async def health(request: Request) -> Response:
    """For the host's health check: 200 while the database answers, else 503."""
    database = request.app.state.database
    try:
        async with database.sessions() as session:
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as error:
        log.error("health check: the database didn't answer (%s)", type(error).__name__)
        return answer(
            Health,
            {"status": "unavailable", "version": __version__, "database": "unreachable"},
            status_code=503,
        )
    return answer(Health, {"status": "ok", "version": __version__, "database": "ok"})


@router.get("/modules", dependencies=[Depends(public)], response_model=ModulesOn)
async def modules_on(request: Request) -> dict[str, Any]:
    """The modules on, for the web shell (`useModuleEnabled`). Modules that are
    off aren't named: a visitor learns nothing of what the site lacks."""
    registry = request.app.state.modules
    return {"on": sorted(await registry.current(request.app.state.database.sessions))}


@router.get("/site", dependencies=[Depends(public)], response_model=Site)
async def site(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The site's name and saved identity, for the web app's home page, frame
    and `<Seo>` (K4 contract §2, addition 2). llms.txt's summary and the AI
    crawlers' switch stay with the server."""
    found = await server_copy.identity(db)
    return {
        "name": found.name,
        "description": found.description,
        "kind": found.kind,
        "logo": found.logo,
        "card_image": found.card_image,
        "same_as": list(found.same_as),
    }


# --- the staff's audit log (SPEC.md 14.10) ---------------------------------------------


def _invalid(name: str, message: str) -> Problem:
    return Problem(
        "kernel.invalid_request",
        422,
        "Some of what was sent isn't valid.",
        errors={name: [message]},
    )


def _utc(moment: datetime) -> datetime:
    """A time sent without a zone is UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _named(value: str) -> bool:
    return len(value) <= audit.MAX_NAME and audit.NAME.fullmatch(value) is not None


#: How many actions and prefixes one read of the log may ask for.
MAX_ACTIONS = 50


def _action(value: str) -> ColumnElement[bool]:
    """An action's name, or a prefix ending in a dot (`blog.`), as a condition."""
    if len(value) <= audit.MAX_NAME and audit.PREFIX.fullmatch(value):
        return AuditEvent.action.startswith(value, autoescape=True)
    if _named(value):
        return AuditEvent.action == value
    raise _invalid("action", "An action's name, or a prefix ending in a dot.")


async def _people(db: AsyncSession, ids: set[uuid.UUID]) -> dict[str, dict[str, Any]]:
    """The accounts among `ids`, by id: name, email and roles by name."""
    if not ids:
        return {}
    people: dict[str, dict[str, Any]] = {
        str(user.id): {"name": user.display_name, "email": user.email, "roles": []}
        for user in await db.scalars(select(User).where(User.id.in_(ids)))
    }
    held = await db.execute(
        select(UserRole.user_id, Role.id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(ids))
        .order_by(Role.name, Role.id)
    )
    for user_id, role_id, role_name in held:
        person = people.get(str(user_id))
        if person is not None:
            person["roles"].append({"id": role_id, "name": role_name})
    return people


@router.get(
    "/admin/audit",
    dependencies=[Depends(require_permission("auth.audit.read"))],
    response_model=AuditPage,
)
async def audit_log(
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID | None = None,
    subject: uuid.UUID | None = None,
    action: list[str] | None = Query(default=None),
    target_type: str | None = None,
    target_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """Every module's entries, newest first, in pages: by who did it
    (`actor`), whom it concerns (`subject`), the action (a name, or a prefix
    ending in a dot such as `blog.`; given more than once, any of them), the
    target, and from `since` up to `until`. The page names the people its
    entries do (`people`) and says how long entries are kept."""
    where: list[ColumnElement[bool]] = []
    if actor is not None:
        where.append(AuditEvent.actor_id == actor)
    if subject is not None:
        where.append(AuditEvent.subject_id == subject)
    if action:
        if len(action) > MAX_ACTIONS:
            raise _invalid("action", f"At most {MAX_ACTIONS} actions and prefixes.")
        where.append(or_(*(_action(each) for each in dict.fromkeys(action))))
    if target_type is not None:
        if not _named(target_type):
            raise _invalid("target_type", "A target's kind: <owner>.<entity>, lowercase.")
        where.append(AuditEvent.target_type == target_type)
    if target_id is not None:
        if target_type is None:
            raise _invalid("target_id", "Only with target_type.")
        where.append(AuditEvent.target_id == target_id)
    if since is not None:
        where.append(AuditEvent.at >= _utc(since))
    if until is not None:
        where.append(AuditEvent.at < _utc(until))
    page = await audit.read(db, where=where, cursor=cursor, limit=limit)
    named = {
        person
        for entry in page.entries
        for person in (entry.actor_id, entry.subject_id)
        if person is not None
    }
    return {
        "items": [audit.item(entry) for entry in page.entries],
        "next_cursor": page.next,
        "people": await _people(db, named),
        "kept_days": audit.keep().days,
    }


# --- the dashboard's "Needs you" list (kernel.attention) ---------------------------------


@router.get("/admin/attention", response_model=AttentionList)
async def needs_you(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """What needs the signed-in staff member, the worst first, each item only
    if they can act on it (K4 contract §2, addition 9). On an admin path,
    `current_user` lets only staff with a second factor through."""
    return {"items": [item.as_answer() for item in await attention.for_person(db, user.id)]}


# --- each person's notices (kernel.notifications, decision 0038) ------------------------


async def _modules_on(request: Request) -> frozenset[str]:
    on: frozenset[str] = await request.app.state.modules.current(
        request.app.state.database.sessions
    )
    return on


@router.get("/notifications", response_model=Notices)
async def notices(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The person's notices, newest first, in pages, and how many are unread."""
    return await notifications.listed(db, user.id, cursor=cursor, limit=limit)


class ReadSome(BaseModel):
    """`{ids: [...]}`: 1 to 100 of the person's notices."""

    model_config = ConfigDict(strict=True, extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=100)
    all: None = None


class ReadAll(BaseModel):
    """`{all: true}`: every one of them."""

    model_config = ConfigDict(strict=True, extra="forbid")

    all: Literal[True]
    ids: None = None


#: Two shapes, so the spec and the client's types say which bodies are taken
#: (CodeRabbit on #78); the null the other one names is still taken.
ReadNotices = ReadSome | ReadAll


@router.post("/notifications/read", status_code=204)
async def read_notices(
    body: ReadNotices, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Marks the person's own notices read; anyone else's id changes nothing."""
    ids = None
    if isinstance(body, ReadSome):
        try:
            ids = [uuid.UUID(value) for value in body.ids]
        except ValueError:
            raise _invalid("ids", "Each id is a notice's id.") from None
    await notifications.mark_read(db, user.id, ids)
    return Response(status_code=204)


class Choice(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    in_site: StrictBool
    email: StrictBool


class Choices(RootModel[dict[str, Choice]]):
    """`{"<key>": {in_site, email}, ...}`, strict as every body (SPEC 7)."""

    model_config = ConfigDict(strict=True)


@router.get("/notifications/preferences", response_model=NoticePreferences)
async def notice_preferences(
    request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Every key of the modules on, with the person's choice for it."""
    on = await _modules_on(request)
    return {"items": await notifications.preferences(db, user.id, on)}


@router.put("/notifications/preferences", response_model=NoticePreferences)
async def choose_notices(
    request: Request,
    body: Choices,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Saves the person's choices for the keys sent; 422 for a key of no module on."""
    on = await _modules_on(request)
    changes = {key: (choice.in_site, choice.email) for key, choice in body.root.items()}
    await notifications.choose(db, user.id, changes, on)
    return {"items": await notifications.preferences(db, user.id, on)}


@router.get(
    notifications.UNSUBSCRIBE_API.removeprefix("/api/kernel"),
    dependencies=[Depends(public)],
    response_model=UnsubscribeLink,
)
async def unsubscribe_link(token: str = "", db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """What the link would turn off, changing nothing: link scanners open links."""
    return await notifications.looked_up(db, token)


@router.post(
    notifications.UNSUBSCRIBE_API.removeprefix("/api/kernel"),
    dependencies=[Depends(public)],
    response_model=Unsubscribed,
)
async def unsubscribe(token: str = "", db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """One click (RFC 8058): email off for the link's key. No session and no
    Origin needed (security.SameOriginWrites lets it through): the token is the proof."""
    await notifications.unsubscribe(db, token)
    return {"email": False}


# --- moderation (kernel.moderation, decision 0039) ----------------------------------------

Reason = Literal[
    "spam", "harassment", "hate", "sexual", "violence", "self_harm", "illegal", "other"
]
ACT = "kernel.moderation.act"
#: How recent a sign-in a ban needs: suspending's step-up (14.4, 14.7).
STEP_UP = timedelta(minutes=10)


def _no_nul(value: str | None) -> str | None:
    """Postgres can't hold a NUL; refused here, it's a 422 rather than the
    service's ValueError as a 500 (Codex on #71)."""
    if value is not None and chr(0) in value:
        raise ValueError("Text can't hold a NUL character.")
    return value


class Target(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    type: str = Field(min_length=1, max_length=moderation.MAX_ID)
    id: str = Field(min_length=1, max_length=moderation.MAX_ID)

    _plain = field_validator("type", "id")(_no_nul)


class Report(BaseModel):
    """`{target: {type, id}, reason, note?}`."""

    model_config = ConfigDict(strict=True, extra="forbid")

    target: Target
    reason: Reason
    note: str | None = Field(default=None, max_length=moderation.MAX_NOTE)

    _plain = field_validator("note")(_no_nul)


@router.post(
    "/moderation/reports",
    status_code=202,
    response_model=Reported,
    dependencies=[
        Depends(current_user),
        Depends(rate_limit(moderation.REPORTS_PER_HOUR, key="account")),
    ],
)
async def report(
    request: Request,
    body: Report,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reports a thing a module lets people report; the same answer for a
    first report and a repeat. 404 for no such thing, or one of a module off."""
    if user.email_verified_at is None:
        raise Problem("auth.email_unverified", 403, "Verify your email address first.")
    found = moderation.named(body.target.type)
    if found is None or found.owner not in await _modules_on(request):
        raise moderation.no_target()
    await moderation.report(
        db, (body.target.type, body.target.id), reporter=user.id, reason=body.reason, note=body.note
    )
    await db.commit()
    return {}


@router.get(
    "/admin/moderation/cases",
    dependencies=[Depends(require_permission(ACT))],
    response_model=Cases,
)
async def cases(
    db: AsyncSession = Depends(get_db),
    status: str = "open",
    kind: str | None = None,
    source: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The queue, the latest report first, in pages: by status (`open` by
    default, `actioned`, `dismissed`), kind and source."""
    if status not in moderation.STATUSES:
        raise _invalid("status", f"One of {', '.join(moderation.STATUSES)}.")
    if source is not None and source not in moderation.SOURCES:
        raise _invalid("source", f"One of {', '.join(moderation.SOURCES)}.")
    if kind is not None and not moderation.KIND.fullmatch(kind):
        raise _invalid("kind", "A kind: <module id>.<entity>, lowercase.")
    return await moderation.listed(
        db, status=status, kind=kind, source=source, cursor=cursor, limit=limit
    )


@router.get(
    "/admin/moderation/cases/{case_id}",
    dependencies=[Depends(require_permission(ACT))],
    response_model=CaseWithReports,
)
async def one_case(case_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """A case with every report on it."""
    return await moderation.case(db, case_id)


class Action(BaseModel):
    """`{action, reason?, note?, minutes?}`: a reason for all but dismiss,
    minutes for a time-out."""

    model_config = ConfigDict(strict=True, extra="forbid")

    action: str
    reason: str | None = None
    note: str | None = None
    minutes: int | None = None


@router.post("/admin/moderation/cases/{case_id}/actions", response_model=CaseWithReports)
async def act(
    request: Request,
    case_id: uuid.UUID,
    body: Action,
    user: User = Depends(require_permission(ACT)),
    resumed: sessions.Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Acts on an open case and closes it; answers the case. A ban suspends
    the account, so it needs a recent sign-in, as suspending does (14.7;
    CodeRabbit on #71)."""
    if body.action == "ban" and not sessions.recent(resumed.session, within=STEP_UP):
        raise Problem("auth.step_up_required", 403, "Confirm it's you to continue.")
    await moderation.act(
        db,
        case_id,
        body.action,
        actor=user,
        reason=body.reason,
        note=body.note,
        minutes=body.minutes,
        on=await _modules_on(request),
    )
    await db.commit()
    return await moderation.case(db, case_id)


class TimeOut(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    minutes: int
    reason: str


TIME_OUT = "/admin/moderation/people/{user_id}/time-out"


@router.put(TIME_OUT, response_model=TimedOut)
async def time_out(
    user_id: uuid.UUID,
    body: TimeOut,
    user: User = Depends(require_permission(ACT)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stops a member posting without a case (live chat); answers when it ends."""
    until = await moderation.time_out(
        db, user_id, actor=user, minutes=body.minutes, reason=body.reason
    )
    await db.commit()
    return {"until": until.isoformat()}


@router.delete(TIME_OUT, status_code=204)
async def lift_time_out(
    user_id: uuid.UUID,
    user: User = Depends(require_permission(ACT)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Lets the person post again."""
    await moderation.lift_time_out(db, user_id, actor=user)
    await db.commit()
    return Response(status_code=204)


@router.get(
    "/admin/moderation/log",
    dependencies=[Depends(require_permission(ACT))],
    response_model=ModerationLog,
)
async def moderation_log(
    db: AsyncSession = Depends(get_db),
    subject: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The moderators' slice of the audit log: moderation and suspensions,
    newest first, with no address or browser (decision 0037's narrower view)."""
    where: list[ColumnElement[bool]] = [moderation.LOGGED]
    if subject is not None:
        where.append(AuditEvent.subject_id == subject)
    page = await audit.read(db, where=where, cursor=cursor, limit=limit)
    return {
        "items": [moderation.log_item(entry) for entry in page.entries],
        "next_cursor": page.next,
    }


# --- taxonomy: the vocabularies' terms (decision 0052, hook 2) ----------------------------


class VocabularyShown(Answer):
    key: str
    label: str
    hierarchical: bool


class TermShown(Answer):
    id: Id
    vocabulary: str
    slug: str
    label: str
    parent_id: Id | None
    position: int


class Terms(Answer):
    vocabulary: VocabularyShown
    items: list[TermShown]
    next_cursor: str | None


MANAGE_TERMS = "kernel.taxonomy.manage"
_SLUG = f"^{taxonomy.SLUG.pattern}$"


@router.get("/terms", dependencies=[Depends(public)], response_model=Terms)
async def terms(
    request: Request,
    vocabulary: str,
    db: AsyncSession = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """A vocabulary's terms, by position and then slug, while a module
    declaring it is on: one that's off names nothing of what the site lacks."""
    found = taxonomy.vocabulary(vocabulary)
    if found is None or not set(found.modules) & await _modules_on(request):
        raise Problem("kernel.vocabulary_not_found", 404, "There's no such vocabulary.")
    return await taxonomy.listed(db, found, cursor=cursor, limit=limit)


class NewTerm(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    vocabulary: str = Field(max_length=40)
    slug: str = Field(min_length=1, max_length=taxonomy.MAX_SLUG, pattern=_SLUG)
    label: str = Field(min_length=1, max_length=taxonomy.MAX_LABEL)
    parent_id: str | None = None
    position: int = Field(default=0, ge=0, le=taxonomy.MAX_POSITION)


class TermChanges(BaseModel):
    """The fields to change; `parent_id` null moves the term to the top."""

    model_config = ConfigDict(strict=True, extra="forbid")

    slug: str | None = Field(
        default=None, min_length=1, max_length=taxonomy.MAX_SLUG, pattern=_SLUG
    )
    label: str | None = Field(default=None, min_length=1, max_length=taxonomy.MAX_LABEL)
    parent_id: str | None = None
    position: int | None = Field(default=None, ge=0, le=taxonomy.MAX_POSITION)


def _label(label: str) -> str:
    if not label.strip():
        raise _invalid("label", "A label has words in it.")
    return label.strip()


def _parent(parent_id: str | None) -> uuid.UUID | None:
    if parent_id is None:
        return None
    try:
        return uuid.UUID(parent_id)
    except ValueError:
        raise _invalid("parent_id", "A term's id.") from None


@router.post("/admin/terms", status_code=201, response_model=TermShown)
async def new_term(
    body: NewTerm,
    user: User = Depends(require_permission(MANAGE_TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adds a term to a vocabulary a module declares, on or off."""
    found = taxonomy.vocabulary(body.vocabulary)
    if found is None:
        raise _invalid("vocabulary", "No module declares that vocabulary.")
    term = await taxonomy.create(
        db,
        found,
        slug=body.slug,
        label=_label(body.label),
        parent_id=_parent(body.parent_id),
        position=body.position,
        actor=user.id,
    )
    await db.commit()
    return taxonomy.view(term)


TERM = "/admin/terms/{term_id}"


@router.patch(TERM, response_model=TermShown)
async def change_term(
    term_id: uuid.UUID,
    body: TermChanges,
    user: User = Depends(require_permission(MANAGE_TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Renames, re-slugs, moves or reorders a term: only the fields sent change."""
    changes: dict[str, Any] = {}
    for field in sorted(body.model_fields_set):
        value = getattr(body, field)
        if field == "parent_id":
            changes[field] = _parent(value)
        elif value is None:
            raise _invalid(field, "It can't be empty.")
        else:
            changes[field] = _label(value) if field == "label" else value
    term = await taxonomy.change(db, term_id, changes, actor=user.id)
    await db.commit()
    return taxonomy.view(term)


@router.delete(TERM, status_code=204)
async def delete_term(
    term_id: uuid.UUID,
    user: User = Depends(require_permission(MANAGE_TERMS)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deletes a term and its links; one with terms under it stays."""
    await taxonomy.remove(db, term_id, actor=user.id)
    await db.commit()
    return Response(status_code=204)


# --- site search (decision 0052, hook 3) ------------------------------------------------


class SearchHit(Answer):
    type: str
    id: Id
    title: str
    #: Plain text around the words found.
    snippet: str
    #: Where the site shows it, such as /blog/jazz.
    path: str


class SearchResults(Answer):
    items: list[SearchHit]
    next_cursor: str | None


@router.get(
    "/search",
    dependencies=[Depends(public), Depends(rate_limit(search.PER_MINUTE))],
    response_model=SearchResults,
)
async def site_search(
    request: Request,
    q: str = Query(max_length=search.MAX_QUERY),
    kind: str | None = Query(default=None, alias="type", max_length=64),
    db: AsyncSession = Depends(get_db),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    """The public documents matching `q`, the best first, of the modules that
    are on; `type` keeps to one content type. One that isn't searched, or
    whose module is off, is refused alike: it names nothing of what the site
    lacks."""
    on = await _modules_on(request)
    types = [found for found in search.searched() if found.partition(".")[0] in on]
    if kind is not None:
        if kind not in types:
            raise _invalid("type", "This site searches no such type.")
        types = [kind]
    return await search.find(db, q, types=types, cursor=cursor, limit=limit)
