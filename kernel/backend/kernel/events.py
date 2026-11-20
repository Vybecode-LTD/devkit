"""Durable events between modules (SPEC.md section 11, decision 0036; contract
dev plans/contracts/k3-events.md).

The module that owns an event declares its payload in `backend/<id_>/events.py`
and emits it in the same transaction as the change it reports:

    @events.payload("blog.post.published", v=1)
    class PostPublished(events.Payload):
        post_id: uuid.UUID

    await events.emit(db, "blog.post.published", PostPublished(post_id=post.id))
    await db.commit()   # the event exists exactly when the change does

A module that cares listens in its own `events.py`, naming its delivery job:

    @events.on("auth.user.deleted", "comments.forget_user")
    async def forget_user(ctx: jobs.Context, event: events.Event) -> None:
        gone = event.parse(events.UserDeleted)

- **Names** are `<module>.<entity>.<past-tense verb>`. A module declares only
  its own (the kernel `auth.*` and `kernel.*`), and its module.json's
  `events.emits` and `events.listens` list exactly what its `events.py`
  declares and hears; `create_app` and `create_worker` refuse to start
  otherwise (`build`).
- **Delivery is a job.** `emit` adds one `kernel.jobs` job per listener to the
  caller's transaction: the jobs table is the outbox. Each is named by its
  listener, so it waits while the listener's module is switched off, and is
  retried with the jobs' backoff, 8 tries in all; a delivery dead after them is
  the event's dead-letter entry for that listener (K4's System page).
- **At least once.** A listener MUST be safe to run twice. Every listener and
  every try sees the same `event.id`, the key for making it so.
- **A listener reads its own view.** Modules don't import each other (SPEC 7):
  `event.parse` reads the payload into the kernel's model or any Pydantic model
  holding the fields the listener needs.
"""

from __future__ import annotations

import inspect
import json
import re
import uuid
from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, jobs

#: `<module>.<entity>.<past-tense verb>`, as the manifest's pattern has it.
NAME = re.compile(r"([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
#: The owners whose events the kernel declares.
KERNEL_OWNERS = frozenset({"auth", "kernel"})
#: SPEC 11: after 8 failures a delivery moves to the dead-letter list.
TRIES = 8

P = TypeVar("P", bound="Payload")
M = TypeVar("M", bound=BaseModel)


class Payload(BaseModel):
    """An event's payload: ids rather than rows, frozen, typed strictly, and
    refusing fields it doesn't declare."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


_declared: dict[type[Payload], tuple[str, int]] = {}


def check_name(name: str) -> str:
    """The event's owner. ValueError for a name that isn't one."""
    match = NAME.fullmatch(name)
    if match is None:
        raise ValueError(
            "An event's name is <module id>.<entity>.<past-tense verb>, the last two in "
            f"[a-z][a-z0-9_]*, not {name!r}."
        )
    return match.group(1)


def payload(name: str, *, v: int) -> Callable[[type[P]], type[P]]:
    """Declares the class below as `name`'s payload, version `v`."""
    check_name(name)
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ValueError(f"{name}'s version is a whole number from 1, not {v!r}.")

    def declare(model: type[P]) -> type[P]:
        if not (isinstance(model, type) and issubclass(model, Payload)):
            raise TypeError(f"{name}'s payload must be a class that subclasses events.Payload.")
        _declared[model] = (name, v)
        return model

    return declare


def declaration(model: type) -> tuple[str, int] | None:
    """The event name and version `model` was declared with, or None."""
    return _declared.get(model)


@dataclass(frozen=True)
class Event:
    """What a listener gets: the same `id` for every listener and every try."""

    id: uuid.UUID
    name: str
    v: int
    emitted_at: datetime
    payload: dict[str, Any]

    def parse(self, model: type[M]) -> M:
        """The payload as `model`: the kernel's, or a view of the listener's own."""
        return model.model_validate_json(json.dumps(self.payload))


class _Envelope(BaseModel):
    """A delivery job's payload, as `emit` writes it."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    v: int
    emitted_at: datetime
    payload: dict[str, Any]


Listening = Callable[[jobs.Context, Event], Awaitable[None]]


@dataclass(frozen=True)
class Listener:
    """A declared listener: what `@events.on` makes. Its job is the delivery."""

    event: str
    job: jobs.Job

    @property
    def name(self) -> str:
        return self.job.name

    @property
    def owner(self) -> str:
        return self.job.owner


def on(
    event: str, name: str, *, timeout: float = jobs.DEFAULT_TIMEOUT
) -> Callable[[Listening], Listener]:
    """Declares a listener to `event`, delivered by the job `name` (its own
    module's, `<id>.<name>`): `async def f(ctx, event)`."""
    check_name(event)

    def declare(function: Listening) -> Listener:
        if not inspect.iscoroutinefunction(function):
            raise TypeError(f"{name}'s listener must be an async function.")

        async def run(ctx: jobs.Context, body: dict[str, Any]) -> None:
            try:
                envelope = _Envelope.model_validate(body)
            except ValidationError:
                raise jobs.Abandon() from None  # never an event: no try will read it
            if envelope.name != event:
                raise jobs.Abandon()
            await function(
                ctx,
                Event(
                    envelope.id, envelope.name, envelope.v, envelope.emitted_at, envelope.payload
                ),
            )

        return Listener(event, jobs.handler(name, tries=TRIES, timeout=timeout)(run))

    return declare


# --- the kernel's events -----------------------------------------------------------------


@payload("auth.user.created", v=1)
class UserCreated(Payload):
    """An account was made."""

    user_id: uuid.UUID


@payload("auth.user.verified", v=1)
class UserVerified(Payload):
    """An account's address was confirmed: sign-up's link, a reset that
    confirmed it, or an email change's confirmation."""

    user_id: uuid.UUID


@payload("auth.user.deleted", v=1)
class UserDeleted(Payload):
    """An account is gone: erase or anonymize what you hold on that person."""

    user_id: uuid.UUID


@payload("auth.user.suspended", v=1)
class UserSuspended(Payload):
    """Staff suspended an account (kernel.moderation): it's signed out
    everywhere and can't sign in. Close what you hold open for that person."""

    user_id: uuid.UUID


@payload("auth.user.restored", v=1)
class UserRestored(Payload):
    """A suspended account is active again."""

    user_id: uuid.UUID


@payload("kernel.settings.changed", v=1)
class SettingsChanged(Payload):
    """A module's settings were saved with a change, as their `version`."""

    module: str
    version: int


@payload("kernel.module.enabled", v=1)
class ModuleEnabled(Payload):
    """A module is on again: the admin switched it on, or a module it
    requires came back on (SPEC 12)."""

    module: str


@payload("kernel.module.disabled", v=1)
class ModuleDisabled(Payload):
    """A module went off: the admin switched it off, or a module it requires
    went off. Its data is kept; its jobs and deliveries wait."""

    module: str


KERNEL_PAYLOADS: tuple[type[Payload], ...] = (
    UserCreated,
    UserVerified,
    UserSuspended,
    UserRestored,
    UserDeleted,
    SettingsChanged,
    ModuleEnabled,
    ModuleDisabled,
)


# --- the start's checks, and emitting ----------------------------------------------------


@dataclass(frozen=True)
class Catalog:
    """Every declared event, and who hears each."""

    payloads: Mapping[str, tuple[type[Payload], int]]
    #: By event: the listeners of the kernel and of the modules MODULES allows.
    listeners: Mapping[str, tuple[Listener, ...]]


def _same(owner: str, verb: str, listed: Iterable[Any], coded: set[str]) -> None:
    wanted = {str(name) for name in listed}
    for name in sorted(wanted - coded):
        raise ValueError(
            f"{owner}'s module.json {verb} {name}, which its events.py doesn't "
            f"{'declare with @events.payload' if verb == 'emits' else 'listen to with @events.on'}."
        )
    for name in sorted(coded - wanted):
        raise ValueError(
            f"{owner}'s events.py {'declares' if verb == 'emits' else 'listens to'} {name}, "
            f"which its module.json's events.{verb} doesn't list."
        )


def build(
    declared: Iterable[
        tuple[str, Iterable[type[Payload]], Iterable[Listener], Mapping[str, Any] | None]
    ],
    *,
    allowed: Collection[str],
) -> Catalog:
    """Every event, from (owner, its payloads, its listeners, its module.json's
    `events` or None for the kernel) entries; `allowed` is the modules MODULES
    lets this deploy use. ValueError, naming the event, on any the start can't take."""
    entries = [
        (owner, tuple(models), tuple(heard), listed) for owner, models, heard, listed in declared
    ]
    installed = {owner for owner, _, _, listed in entries if listed is not None}
    payloads: dict[str, tuple[type[Payload], int]] = {}
    for owner, models, heard, listed in entries:
        coded: set[str] = set()
        for model in models:
            found = declaration(model)
            if found is None:
                raise ValueError(f"{owner}'s {model.__name__} isn't declared with @events.payload.")
            name, version = found
            event_owner = name.partition(".")[0]
            ours = event_owner in KERNEL_OWNERS if listed is None else event_owner == owner
            if not ours:
                mine = "auth.* and kernel.*" if listed is None else f"{owner}.*"
                raise ValueError(f"{owner} may only declare {mine} events, not {name}.")
            if name in payloads:
                raise ValueError(f"The event {name} is declared twice.")
            payloads[name] = (model, version)
            coded.add(name)
        for listener in heard:
            if listener.owner != owner:
                raise ValueError(
                    f"{owner} may only declare {owner}.* listeners, not {listener.name}."
                )
        if listed is not None:
            _same(owner, "emits", listed.get("emits") or (), coded)
            _same(owner, "listens", listed.get("listens") or (), {item.event for item in heard})

    by_event: dict[str, list[Listener]] = {}
    for owner, _, heard, listed in entries:
        for listener in heard:
            event_owner = listener.event.partition(".")[0]
            known = event_owner in KERNEL_OWNERS or event_owner in installed
            if known and listener.event not in payloads:
                who = "the kernel" if event_owner in KERNEL_OWNERS else event_owner
                raise ValueError(
                    f"{listener.name} listens to {listener.event}, which {who} doesn't declare."
                )
            if listed is None or owner in allowed:
                by_event.setdefault(listener.event, []).append(listener)
    return Catalog(
        payloads,
        {
            event: tuple(sorted(heard, key=lambda listener: listener.name))
            for event, heard in by_event.items()
        },
    )


_catalog: Catalog = build([("kernel", KERNEL_PAYLOADS, (), None)], allowed=())


def install(catalog: Catalog) -> None:
    """Sets the events `emit` knows and who hears them: `create_app` and
    `create_worker` call it. Until then, the kernel's events, heard by no one."""
    global _catalog
    _catalog = catalog


async def emit(db: AsyncSession, name: str, payload: Payload) -> int:
    """Adds `name`'s deliveries to the caller's transaction, which the caller
    commits: one job per listener. Returns how many."""
    catalog = _catalog
    declared = catalog.payloads.get(name)
    if declared is None:
        raise ValueError(
            f"No event {name}: its module declares it in events.py with @events.payload and "
            "lists it in module.json's events.emits."
        )
    model, version = declared
    if type(payload) is not model:
        raise TypeError(f"{name}'s payload is a {model.__name__}, not a {type(payload).__name__}.")
    body = {
        "id": str(uuid.uuid4()),
        "name": name,
        "v": version,
        "emitted_at": clock.now().isoformat(),
        "payload": payload.model_dump(mode="json"),
    }
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode()) > jobs.MAX_PAYLOAD:
        raise ValueError(
            f"An event holds at most {jobs.MAX_PAYLOAD // 1024} KiB of JSON: ids, not rows."
        )
    heard = catalog.listeners.get(name, ())
    for listener in heard:
        await jobs.enqueue(db, listener.name, body)
    return len(heard)
