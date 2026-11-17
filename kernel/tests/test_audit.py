"""kernel.audit: one append-only log every module writes to, in the caller's
transaction; the staff's and each person's reads; pruning (SPEC.md 6, 14.10;
decision 0037; contract dev plans/contracts/k3-audit.md).

The run's database is shared, so each test's entries carry a target, an
actor or a subject of its own and every read filters on it. Auth's own
entries are tested beside the routes that write them (`kernel/tests/auth`).
"""

from __future__ import annotations

import ast
import enum
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel, SecretStr, ValidationError
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

import kernel
from kernel import audit, clock, jobs
from kernel.auth import sessions
from kernel.auth.models import Totp, User, UserRole
from kernel.db import Database
from kernel.email import LogMailer
from kernel.models import AuditEvent
from kernel.modules import InstalledModule
from kernel.settings import SettingsRegistry

from .conftest import AppFactory, Client, make_config, manifest, unique_id

KERNEL_SOURCE = Path(kernel.__file__).parent


@pytest.fixture(autouse=True)
def _fresh() -> Iterator[None]:
    """Real time, and the owners and keep an app's start would install put
    back as before any app."""
    clock.reset()
    audit.install((), keep_days=365)
    yield
    clock.reset()
    audit.install((), keep_days=365)


class _Session:
    """Takes what `record` adds, for the refusals, which touch no database."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, row: Any) -> None:
        self.added.append(row)


def _record(action: str = "kernel.settings_saved", **given: Any) -> AuditEvent:
    session = _Session()
    given.setdefault("actor", None)
    audit.record(cast(AsyncSession, session), action, **given)
    assert len(session.added) == 1
    row: AuditEvent = session.added[0]
    return row


def _request(host: str = "203.0.113.9", agent: str = "Firefox") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"user-agent", agent.encode())],
        "client": (host, 50000),
        "app": FastAPI(),
    }
    return Request(scope)


# --- what record takes ---------------------------------------------------------------


def test_the_kernel_s_actions_are_a_closed_set() -> None:
    assert _record("auth.sign_in").action == "auth.sign_in"
    assert _record("kernel.settings_saved").action == "kernel.settings_saved"
    with pytest.raises(ValueError, match=r"kernel\.setings_saved"):
        _record("kernel.setings_saved")
    with pytest.raises(ValueError, match=r"auth\.sign_inn"):
        _record("auth.sign_inn")


def test_a_module_writes_only_once_its_app_installs_it(app_factory: AppFactory) -> None:
    owner = unique_id("blog")  # a module's id, hyphen and all
    with pytest.raises(ValueError, match=owner):
        _record(f"{owner}.post_deleted")
    audit.install([owner], keep_days=365)
    assert _record(f"{owner}.post_deleted").action == f"{owner}.post_deleted"
    assert _record(f"{owner}.post.restored").action == f"{owner}.post.restored"
    audit.install((), keep_days=365)
    app_factory([InstalledModule(manifest(owner))])
    assert _record(f"{owner}.post_deleted").action == f"{owner}.post_deleted"


@pytest.mark.parametrize(
    "action",
    [
        "",
        "kernel",
        "kernel.",
        ".settings_saved",
        "Kernel.settings_saved",
        "kernel..x",
        "kernel.x-y",
        "kernel.x y",
        "kernel.x\n",
        "auth.é",
        "kernel.1x",
        "-kernel.x",
    ],
)
def test_a_bad_action_name_is_refused(action: str) -> None:
    with pytest.raises(ValueError, match="audit action"):
        _record(action)


def test_an_action_is_at_most_64_characters() -> None:
    audit.install(["blog"], keep_days=365)
    assert _record("blog." + "x" * 59).action == "blog." + "x" * 59
    with pytest.raises(ValueError, match="audit action"):
        _record("blog." + "x" * 60)


@pytest.mark.parametrize(
    "target",
    [
        ("blog", 1),
        ("Blog.post", 1),
        ("blog.post", ""),
        ("blog.post", "x" * 65),
        ("blog." + "p" * 60, 1),
        ("blog.post", True),
        ("blog.post", 1.5),
        ("blog.post", None),
        ("blog.post",),
        ("blog.post", 1, 2),
        "blog.post",
    ],
)
def test_a_bad_target_is_refused(target: Any) -> None:
    with pytest.raises(ValueError, match="target"):
        _record(target=target)


def test_a_target_s_id_is_kept_as_text() -> None:
    post = uuid.uuid4()
    assert (_record(target=("blog.post", post)).target_id) == str(post)
    row = _record(target=("blog.post", 42))
    assert (row.target_type, row.target_id) == ("blog.post", "42")
    assert _record(target=("blog.post", "x" * 64)).target_id == "x" * 64
    row = _record()
    assert (row.target_type, row.target_id) == (None, None)


@pytest.mark.parametrize("result", ["", "Success", "x" * 17, "with space", "ok!"])
def test_a_bad_result_is_refused(result: str) -> None:
    with pytest.raises(ValueError, match="audit result"):
        _record(result=result)


@pytest.mark.parametrize("who", ["actor", "subject"])
@pytest.mark.parametrize("value", ["3f6e…", 7, object()])
def test_actor_and_subject_are_ids(who: str, value: Any) -> None:
    with pytest.raises(ValueError, match=f"{who} is an account's UUID"):
        _record(**{who: value})


def test_the_actor_is_never_left_out() -> None:
    with pytest.raises(TypeError):
        audit.record(cast(AsyncSession, _Session()), "kernel.settings_saved")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "details",
    [
        {"to": "ana@site.test"},
        {"people": ["x", {"email": "b@c"}]},
        {"note": "@"},
        {"ana@site.test": True},  # CodeRabbit on #67
        {"outer": {"b@c": 1}},
    ],
)
def test_details_never_hold_an_address(details: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="address"):
        _record(details=details)


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "new_password",
        "Password",
        "secret",
        "api_secret",
        "token",
        "csrf_token",
        "code",
        "recovery_code",
        "TOKEN_hash",
    ],
)
def test_details_never_name_a_secret(key: str) -> None:
    with pytest.raises(ValueError, match="secret"):
        _record(details={key: "x"})
    with pytest.raises(ValueError, match="secret"):
        _record(details={"outer": [{key: 1}]})


@pytest.mark.parametrize(
    "value",
    [object(), float("nan"), float("inf"), b"bytes", {1: "a"}, {"set"}, complex(1, 1)],
)
def test_details_hold_only_json(value: Any) -> None:
    with pytest.raises(ValueError, match="Audit details"):
        _record(details={"value": value})


NUL = chr(0)


@pytest.mark.parametrize(
    "given",
    [
        {"details": {"label": f"a{NUL}b"}},
        {"details": {f"a{NUL}": 1}},
        {"details": {"list": [NUL]}},
        {"target": ("blog.post", f"7{NUL}")},
    ],
)
def test_a_nul_character_is_refused_before_postgres_sees_it(given: dict[str, Any]) -> None:
    """CodeRabbit on #67: Postgres refuses it in JSONB and text, at the
    caller's flush; `record` refuses it first."""
    with pytest.raises(ValueError, match="NUL"):
        _record(**given)


@pytest.mark.parametrize("details", [["method", "totp"], "method=totp", 7])
def test_details_are_a_mapping(details: Any) -> None:
    with pytest.raises(ValueError, match="mapping"):
        _record(details=details)


def test_details_are_at_most_4_kib() -> None:
    room = audit.MAX_DETAILS - len('{"x":""}')
    kept = _record(details={"x": "a" * room}).details
    assert len(json.dumps(kept, separators=(",", ":"))) == audit.MAX_DETAILS
    with pytest.raises(ValueError, match="4 KiB"):
        _record(details={"x": "a" * (room + 1)})
    with pytest.raises(ValueError, match="4 KiB"):
        _record(details={"x": "é" * (room // 2 + 1)})  # counted in UTF-8 bytes


class _Colour(enum.Enum):
    RED = "red"
    DEEP = 3


def test_details_values_become_json() -> None:
    item = uuid.uuid4()
    when = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)
    row = _record(
        details={
            "item": item,
            "at": when,
            "on": date(2026, 11, 17),
            "colour": _Colour.RED,
            "depth": _Colour.DEEP,
            "ids": (1, 2),
            "nested": {"ok": True, "none": None, "ratio": 0.5},
        }
    )
    assert row.details == {
        "item": str(item),
        "at": "2026-11-17T09:30:00+00:00",
        "on": "2026-11-17",
        "colour": "red",
        "depth": 3,
        "ids": [1, 2],
        "nested": {"ok": True, "none": None, "ratio": 0.5},
    }
    assert _record().details == {}


def test_a_request_s_address_and_browser_are_kept_and_none_without_one() -> None:
    row = _record(request=_request(agent="F" * 400))
    assert (str(row.ip), row.user_agent) == ("203.0.113.9/32", "F" * 300)
    row = _record(request=_request(host="2001:db8::1"))
    assert str(row.ip) == "2001:db8::/64"
    row = _record(request=_request(host="testclient"))
    assert (row.ip, row.user_agent) == (None, "Firefox")
    row = _record()
    assert (row.ip, row.user_agent) == (None, "")


def test_the_keep_is_at_least_30_days() -> None:
    assert make_config().audit_keep_days == 365
    assert make_config(audit_keep_days=30).audit_keep_days == 30
    with pytest.raises(ValidationError):
        make_config(audit_keep_days=29)
    with pytest.raises(ValueError, match="30 days"):
        audit.install((), keep_days=29)


# --- every kernel call names a kernel action ---------------------------------------


def _kernel_calls() -> dict[str, list[str]]:
    """Every action the kernel's code passes to `audit.record`,
    `kernel.auth.audit.record` or `record_by_kernel`, resolving a name bound
    to a string in the same file."""
    found: dict[str, list[str]] = {}
    for path in sorted(KERNEL_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bound: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value.value, str):
                        bound.setdefault(target.id, set()).add(node.value.value)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            func_ = node.func
            if not (isinstance(func_.value, ast.Name) and func_.value.id == "audit"):
                continue
            if func_.attr not in ("record", "record_by_kernel"):
                continue
            auth_style = path.parent.name == "auth" or func_.attr == "record_by_kernel"
            index = (2 if func_.attr == "record" else 1) if auth_style else 1
            argument = node.args[index]
            if isinstance(argument, ast.Constant):
                names = {argument.value}
            else:
                assert isinstance(argument, ast.Name), f"{path.name}:{node.lineno}"
                names = bound[argument.id]
            for name in names:
                found.setdefault(name, []).append(f"{path.name}:{node.lineno}")
    return found


def test_every_kernel_audit_call_names_a_kernel_action_and_each_is_used() -> None:
    calls = _kernel_calls()
    assert set(calls) == set(audit.KERNEL_ACTIONS)


# --- written with the change, and only ever added -----------------------------------


async def _entries(db: AsyncSession, target_type: str) -> list[AuditEvent]:
    found = await db.scalars(
        select(AuditEvent)
        .where(AuditEvent.target_type == target_type)
        .order_by(AuditEvent.id)
        .execution_options(populate_existing=True)
    )
    return list(found.all())


def _kind() -> str:
    return f"test.k{uuid.uuid4().hex[:12]}"


async def test_an_entry_commits_with_the_change_and_a_rollback_drops_it(db: AsyncSession) -> None:
    kind = _kind()
    audit.record(db, "kernel.settings_saved", actor=None, target=(kind, "dropped"))
    await db.rollback()
    actor, subject = uuid.uuid4(), uuid.uuid4()
    before = clock.now()
    audit.record(
        db,
        "auth.sign_in",
        actor=actor,
        target=(kind, "kept"),
        subject=subject,
        result="failure",
        details={"method": "password"},
        request=_request(),
    )
    await db.commit()
    rows = await _entries(db, kind)
    assert [(r.action, r.result, r.actor_id, r.subject_id, r.target_id) for r in rows] == [
        ("auth.sign_in", "failure", actor, subject, "kept")
    ]
    assert (str(rows[0].ip), rows[0].user_agent, rows[0].details) == (
        "203.0.113.9",
        "Firefox",
        {"method": "password"},
    )
    assert before <= rows[0].at <= clock.now()


async def _one(db: AsyncSession) -> tuple[str, int]:
    kind = _kind()
    audit.record(db, "kernel.settings_saved", actor=None, target=(kind, "1"))
    await db.commit()
    return kind, (await _entries(db, kind))[0].id


async def test_the_database_refuses_to_change_an_entry(db: AsyncSession) -> None:
    kind, entry = await _one(db)
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(update(AuditEvent).where(AuditEvent.id == entry).values(result="ok"))
    await db.rollback()
    assert (await _entries(db, kind))[0].result == "success"


async def test_the_database_refuses_to_delete_an_entry_but_for_the_pruning(
    db: AsyncSession,
) -> None:
    kind, entry = await _one(db)
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(text("DELETE FROM kernel_audit_event WHERE id = :id"), {"id": entry})
    await db.rollback()
    await db.execute(text("SELECT set_config('kernel.audit_prune', 'off', true)"))
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(text("DELETE FROM kernel_audit_event WHERE id = :id"), {"id": entry})
    await db.rollback()
    assert len(await _entries(db, kind)) == 1
    # The switch lasts for its transaction alone.
    await db.execute(text(f"SELECT set_config('{audit.PRUNE_SWITCH}', 'on', true)"))
    await db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(text("DELETE FROM kernel_audit_event WHERE id = :id"), {"id": entry})
    await db.rollback()
    await db.execute(text(f"SELECT set_config('{audit.PRUNE_SWITCH}', 'on', true)"))
    await db.execute(text("DELETE FROM kernel_audit_event WHERE id = :id"), {"id": entry})
    await db.commit()
    assert await _entries(db, kind) == []


async def test_the_database_refuses_to_empty_the_log(db: AsyncSession) -> None:
    """CodeRabbit on #67: TRUNCATE runs no row trigger. Rolled back whatever
    happens, so a run without the trigger loses nothing."""
    kind, _ = await _one(db)
    try:
        with pytest.raises(DBAPIError, match="append-only"):
            await db.execute(text("TRUNCATE kernel_audit_event"))
    finally:
        await db.rollback()
    assert len(await _entries(db, kind)) == 1


# --- pruning ------------------------------------------------------------------------


async def test_pruning_removes_only_entries_past_the_keep_across_batches(
    db: AsyncSession, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit, "BATCH", 2)
    audit.install((), keep_days=40)
    kind = _kind()
    now = clock.now()
    ages = {
        "old-1": timedelta(days=400),
        "old-2": timedelta(days=41),
        "old-3": timedelta(days=40, minutes=1),
        "old-4": timedelta(days=40, minutes=1),
        "old-5": timedelta(days=40, minutes=1),
        "kept-1": timedelta(days=40) - timedelta(minutes=1),
        "kept-2": timedelta(0),
    }
    for name, age in ages.items():
        await db.execute(
            insert(AuditEvent).values(
                at=now - age,
                action="kernel.settings_saved",
                result="success",
                target_type=kind,
                target_id=name,
            )
        )
    await db.commit()
    context = jobs.Context(
        job_id=uuid.uuid4(),
        name="kernel.prune_audit",
        try_number=1,
        _database=database,
        _mailer=LogMailer(),
    )
    await audit.PRUNE.run(context, {})
    assert [r.target_id for r in await _entries(db, kind)] == ["kept-1", "kept-2"]


def test_pruning_is_one_of_the_kernel_s_daily_jobs(app_factory: AppFactory) -> None:
    app = app_factory()
    assert "kernel.prune_audit" in app.state.worker.names
    assert audit.PRUNE.schedule is not None
    assert audit.PRUNE.name == "kernel.prune_audit"


async def test_an_app_installs_its_modules_as_owners_and_its_keep(
    app_factory: AppFactory,
) -> None:
    app_factory(audit_keep_days=90)
    assert audit.keep() == timedelta(days=90)


# --- reading: staff -----------------------------------------------------------------


async def _user(db: AsyncSession, *roles: str, second_factor: bool = False) -> User:
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@site.test"
    user = User(id=user_id, email=email, email_normal=email, session_epoch=0, role_version=0)
    db.add(user)
    await db.flush()
    for role in roles or ("member",):
        db.add(UserRole(user_id=user_id, role_id=role))
    if second_factor:
        db.add(Totp(user_id=user_id, secret_sealed="sealed", confirmed_at=clock.now()))
    await db.commit()
    return user


async def _as(db: AsyncSession, user: User) -> dict[str, str]:
    token, _ = await sessions.start(db, user, user_agent="pytest")
    await db.commit()
    return {"cookie": f"{sessions.SESSION_COOKIE}={token}"}


STAFF_LOG = "/api/kernel/admin/audit"
OWN_LOG = "/api/auth/activity"


def _code(response: httpx.Response) -> str:
    assert response.headers["content-type"].startswith("application/problem+json")
    code: str = response.json()["code"]
    return code


async def test_reading_the_log_needs_staff_with_audit_read_and_a_second_factor(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    member = await _user(db)
    bare_admin = await _user(db, "admin")
    admin = await _user(db, "admin", second_factor=True)
    editor = await _user(db, "editor", second_factor=True)
    async with Client(app_factory()) as client:
        response = await client.get(STAFF_LOG)
        assert (response.status_code, _code(response)) == (401, "kernel.not_signed_in")
        response = await client.get(STAFF_LOG, headers=await _as(db, member))
        assert (response.status_code, _code(response)) == (403, "kernel.forbidden")
        response = await client.get(STAFF_LOG, headers=await _as(db, bare_admin))
        assert (response.status_code, _code(response)) == (403, "auth.second_factor_required")
        response = await client.get(STAFF_LOG, headers=await _as(db, editor))
        assert (response.status_code, _code(response)) == (403, "kernel.forbidden")
        response = await client.get(STAFF_LOG, headers=await _as(db, admin))
        assert response.status_code == 200


async def _write(db: AsyncSession, kind: str, count: int) -> None:
    """`count` entries on `kind`, a second apart, their ids 0 (oldest) up."""
    for n in range(count):
        audit.record(db, "kernel.settings_saved", actor=None, target=(kind, str(n)))
        await db.commit()
        clock.advance(1)


async def test_the_staff_s_log_is_newest_first_in_pages_that_neither_repeat_nor_skip(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    admin = await _user(db, "admin", second_factor=True)
    kind = _kind()
    await _write(db, kind, 5)
    seen: list[str] = []
    async with Client(app_factory()) as client:
        headers = await _as(db, admin)
        query: dict[str, Any] = {"target_type": kind, "limit": 2}
        pages = 0
        while True:
            response = await client.get(STAFF_LOG, params=query, headers=headers)
            assert response.status_code == 200, response.text
            body = response.json()
            seen += [item["target"]["id"] for item in body["items"]]
            pages += 1
            if body["next_cursor"] is None:
                break
            query["cursor"] = body["next_cursor"]
    assert (seen, pages) == (["4", "3", "2", "1", "0"], 3)


async def test_entries_written_at_the_same_moment_page_by_id(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    admin = await _user(db, "admin", second_factor=True)
    kind, now = _kind(), clock.now()
    for n in range(3):
        await db.execute(
            insert(AuditEvent).values(
                at=now,
                action="kernel.settings_saved",
                result="success",
                target_type=kind,
                target_id=str(n),
            )
        )
    await db.commit()
    seen: list[str] = []
    async with Client(app_factory()) as client:
        headers = await _as(db, admin)
        query: dict[str, Any] = {"target_type": kind, "limit": 1}
        while True:
            body = (await client.get(STAFF_LOG, params=query, headers=headers)).json()
            seen += [item["target"]["id"] for item in body["items"]]
            if body["next_cursor"] is None:
                break
            query["cursor"] = body["next_cursor"]
    assert seen == ["2", "1", "0"]


async def test_an_item_on_the_staff_s_log_has_every_field(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    admin = await _user(db, "admin", second_factor=True)
    kind, actor, subject = _kind(), uuid.uuid4(), uuid.uuid4()
    audit.record(
        db,
        "auth.step_up",
        actor=actor,
        subject=subject,
        target=(kind, "7"),
        result="failure",
        details={"method": "totp"},
        request=_request(),
    )
    await db.commit()
    entry = (await _entries(db, kind))[0]
    async with Client(app_factory()) as client:
        response = await client.get(
            STAFF_LOG, params={"target_type": kind}, headers=await _as(db, admin)
        )
    assert response.json() == {
        "items": [
            {
                "id": entry.id,
                "at": entry.at.isoformat(),
                "action": "auth.step_up",
                "result": "failure",
                "actor_id": str(actor),
                "subject_id": str(subject),
                "target": {"type": kind, "id": "7"},
                "ip": "203.0.113.9",
                "user_agent": "Firefox",
                "details": {"method": "totp"},
            }
        ],
        "next_cursor": None,
    }


async def test_the_staff_s_log_filters_by_person_action_target_and_time(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    admin = await _user(db, "admin", second_factor=True)
    kind = _kind()
    ana, ben = uuid.uuid4(), uuid.uuid4()
    start = clock.now()
    audit.record(db, "auth.sign_in", actor=ana, subject=ana, target=(kind, "a"))
    audit.record(db, "auth.sign_out", actor=ana, subject=ana, target=(kind, "b"))
    audit.record(db, "auth.session_ended", actor=ben, subject=ana, target=(kind, "c"))
    await db.commit()
    clock.advance(60)
    middle = clock.now()
    audit.record(db, "kernel.settings_saved", actor=ben, target=(kind, "d"))
    audit.record(db, "auth.sign_up", actor=None, target=(kind, "e"))
    await db.commit()

    async def ids(**query: Any) -> list[str]:
        response = await client.get(
            STAFF_LOG, params={"target_type": kind, **query}, headers=headers
        )
        assert response.status_code == 200, response.text
        return sorted(item["target"]["id"] for item in response.json()["items"])

    async with Client(app_factory()) as client:
        headers = await _as(db, admin)
        assert await ids() == ["a", "b", "c", "d", "e"]
        assert await ids(actor=str(ana)) == ["a", "b"]
        assert await ids(subject=str(ana)) == ["a", "b", "c"]
        assert await ids(action="auth.sign_in") == ["a"]
        assert await ids(action="auth.sign_") == []  # a prefix ends with a dot
        assert await ids(action="auth.") == ["a", "b", "c", "e"]
        assert await ids(action="kernel.") == ["d"]
        assert await ids(target_id="c") == ["c"]
        assert await ids(since=middle.isoformat()) == ["d", "e"]
        assert await ids(until=middle.isoformat()) == ["a", "b", "c"]
        assert await ids(since=start.isoformat(), until=middle.isoformat(), actor=str(ben)) == ["c"]


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 0},
        {"limit": 101},
        {"actor": "ana"},
        {"action": "Auth."},
        {"action": "auth"},
        {"action": "auth..x"},
        {"target_id": "7"},
        {"cursor": "not-a-cursor"},
        {"cursor": "123"},
        {"cursor": "9999999999999999999.1"},  # past the last datetime (Codex on #67)
        {"cursor": "1.9223372036854775808"},  # past Postgres's bigint
        {"cursor": "1." + "9" * 20},
        {"since": "yesterday"},
    ],
)
async def test_a_bad_filter_on_the_staff_s_log_is_a_422(
    db: AsyncSession, app_factory: AppFactory, query: dict[str, Any]
) -> None:
    admin = await _user(db, "admin", second_factor=True)
    async with Client(app_factory()) as client:
        response = await client.get(STAFF_LOG, params=query, headers=await _as(db, admin))
    assert (response.status_code, _code(response)) == (422, "kernel.invalid_request")


# --- reading: one's own security activity -------------------------------------------


async def test_a_person_reads_only_their_own_security_activity(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    ana = await _user(db)
    staff_id, other = uuid.uuid4(), uuid.uuid4()
    audit.record(db, "auth.sign_in", actor=ana.id, subject=ana.id, request=_request())
    await db.commit()
    clock.advance(1)
    audit.record(db, "auth.session_ended", actor=staff_id, subject=ana.id, details={"removed": 1})
    audit.record(db, "kernel.settings_saved", actor=ana.id, subject=ana.id)  # not security
    audit.record(db, "auth.sign_in", actor=other, subject=other)  # someone else's
    audit.record(db, "auth.code_sent", actor=None, subject=ana.id, result="waiting")
    await db.commit()
    async with Client(app_factory()) as client:
        response = await client.get(OWN_LOG)
        assert (response.status_code, _code(response)) == (401, "kernel.not_signed_in")
        response = await client.get(OWN_LOG, headers=await _as(db, ana))
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(i["action"], i["result"], i["by_you"]) for i in items] == [
        ("auth.code_sent", "waiting", False),
        ("auth.session_ended", "success", False),
        ("auth.sign_in", "success", True),
    ]
    assert all("actor_id" not in item and "subject_id" not in item for item in items)
    assert (items[1]["details"], items[2]["ip"], items[2]["user_agent"]) == (
        {"removed": 1},
        "203.0.113.9",
        "Firefox",
    )


async def test_one_s_own_activity_comes_in_pages(db: AsyncSession, app_factory: AppFactory) -> None:
    ana = await _user(db)
    for _ in range(3):
        audit.record(db, "auth.sign_in", actor=ana.id, subject=ana.id)
        await db.commit()
        clock.advance(1)
    async with Client(app_factory()) as client:
        headers = await _as(db, ana)
        first = (await client.get(OWN_LOG, params={"limit": 2}, headers=headers)).json()
        second = await client.get(
            OWN_LOG, params={"limit": 2, "cursor": first["next_cursor"]}, headers=headers
        )
        bad = await client.get(OWN_LOG, params={"cursor": "x"}, headers=headers)
        late = await client.get(
            OWN_LOG, params={"cursor": "9999999999999999999.1"}, headers=headers
        )
        whole = (await client.get(OWN_LOG, params={"limit": 3}, headers=headers)).json()
    assert len(first["items"]) == 2
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None
    assert (len(whole["items"]), whole["next_cursor"]) == (3, None)  # a full last page ends it
    assert {i["id"] for i in first["items"]}.isdisjoint(i["id"] for i in second.json()["items"])
    assert (bad.status_code, _code(bad)) == (422, "kernel.invalid_request")
    assert (late.status_code, _code(late)) == (422, "kernel.invalid_request")


# --- the first use: settings ---------------------------------------------------------


class _Shop(BaseModel):
    title: str = "Shop"
    api_key: SecretStr | None = None


async def test_a_settings_save_that_changes_something_is_audited_once(db: AsyncSession) -> None:
    found = SettingsRegistry()
    module_id = unique_id("shop")
    found.register(module_id, _Shop)
    admin = await _user(db, "admin")
    await found.save(
        db, module_id, {"title": "Store", "api_key": "sk-hidden-1"}, version=0, by=admin.id
    )
    await found.save(db, module_id, {"title": "Store"}, version=1, by=admin.id)  # nothing changes
    await found.save(db, module_id, {"title": "Shop"}, version=1, via="code")
    rows = list(
        (
            await db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.target_type == "kernel.settings", AuditEvent.target_id == module_id
                )
                .order_by(AuditEvent.id)
            )
        ).all()
    )
    assert [(r.action, r.actor_id, r.details) for r in rows] == [
        (
            "kernel.settings_saved",
            admin.id,
            {"version": 1, "changed": ["api_key", "title"], "via": "form"},
        ),
        ("kernel.settings_saved", None, {"version": 2, "changed": ["title"], "via": "code"}),
    ]
    assert "sk-hidden-1" not in json.dumps([r.details for r in rows])


async def test_the_table_is_auth_s_widened(db: AsyncSession) -> None:
    """Auth's model is the kernel's: one table for every module."""
    from kernel.auth import models as auth_models

    assert auth_models.AuditEvent is AuditEvent
    assert AuditEvent.__tablename__ == "kernel_audit_event"
    assert await db.scalar(select(func.to_regclass("auth_audit_event"))) is None
