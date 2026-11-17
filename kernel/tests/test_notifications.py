"""kernel.notifications: notices in the site and by email, by each person's
choice per key, with one-click unsubscribe (SPEC.md 6; decision 0038;
contract dev plans/contracts/k3-notifications.md).

Each test's people are its own, and every read filters on them; the app's
worker sends every due mail in the run's database, so a test reads only the
mail to its own people's addresses.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, email, jobs, notifications
from kernel.app import create_app
from kernel.auth import sessions
from kernel.auth.models import User
from kernel.db import Database
from kernel.email import Captured, CapturingMailer, Checked, LogMailer, Template
from kernel.models import ModuleState, Notification, NotificationPreference
from kernel.modules import InstalledModule, Manifest

from .conftest import Client, make_config, unique_id

REPLY = Template(
    subject="$who replied on $post",
    text="$who replied on $post: $link\n",
    html='<p>$who replied on <a href="$link">$post</a></p>',
)
READY = Template(subject="Your $thing is ready", text="Your $thing is ready.\n")
RECEIPT = Template(subject="Receipt $number", text="Thanks. Receipt $number.\n")
UNSUBSCRIBE_API = "/api/kernel/notifications/unsubscribe"


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


def _manifest(module_id: str, kinds: list[dict[str, str]]) -> Manifest:
    return Manifest.from_dict(
        {
            "id": module_id,
            "name": module_id.title(),
            "version": "0.1.0",
            "requires": {"kernel": "^0.1", "modules": {}},
            "notifications": kinds,
        }
    )


def _kinds(module_id: str) -> list[dict[str, str]]:
    return [
        {"key": f"{module_id}.reply", "description": "Someone replied to you", "default": "both"},
        {"key": f"{module_id}.ready", "description": "Your export is ready", "default": "in_site"},
        {"key": f"{module_id}.receipt", "description": "A receipt", "default": "email"},
    ]


def _templates(module_id: str) -> dict[str, Template]:
    return {
        f"{module_id}.reply": REPLY,
        f"{module_id}.ready": READY,
        f"{module_id}.receipt": RECEIPT,
    }


@dataclass
class Site:
    app: FastAPI
    module: str
    mailer: CapturingMailer

    def key(self, name: str) -> str:
        return f"{self.module}.{name}"

    @property
    def url(self) -> str:
        site_url: str = self.app.state.config.site_url
        return site_url.rstrip("/")

    async def mail(self, address: str) -> list[Captured]:
        await self.app.state.worker.run_due(wait=0)
        return self.mailer.to(address)


@pytest_asyncio.fixture(loop_scope="session")
async def site(migrated_url: str) -> AsyncIterator[Site]:
    module_id = unique_id("news")
    module = InstalledModule(_manifest(module_id, _kinds(module_id)), emails=_templates(module_id))
    mailer = CapturingMailer()
    app = create_app(
        modules=[module],
        config=make_config(database_url=migrated_url, modules_cache_seconds=0),
        mailer=mailer,
    )
    yield Site(app, module_id, mailer)
    await app.state.database.dispose()


async def _person(db: AsyncSession, *, verified: bool = True, status: str = "active") -> User:
    user_id = uuid.uuid4()
    address = f"{user_id.hex[:12]}@site.test"
    user = User(
        id=user_id,
        email=address,
        email_normal=address,
        email_verified_at=clock.now() if verified else None,
        status=status,
        session_epoch=0,
        role_version=0,
    )
    db.add(user)
    await db.commit()
    return user


async def _notices(db: AsyncSession, user_id: uuid.UUID) -> list[Notification]:
    found = await db.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .execution_options(populate_existing=True)
    )
    return list(found.all())


def _reply() -> dict[str, str]:
    return {"who": "Ben", "post": "Spring tour"}


# --- notify: where a notice goes ------------------------------------------------------


async def test_a_notice_goes_where_its_default_says(site: Site, db: AsyncSession) -> None:
    ana = await _person(db)
    sent = [
        await notifications.notify(db, ana.id, site.key("reply"), _reply(), link="/blog/spring#c4"),
        await notifications.notify(db, ana.id, site.key("ready"), {"thing": "export"}),
        await notifications.notify(db, ana.id, site.key("receipt"), {"number": "42"}),
    ]
    await db.commit()
    Sent = notifications.Sent
    assert sent == [Sent(True, True), Sent(True, False), Sent(False, True)]
    assert sorted((n.key, n.title, n.link, n.read_at) for n in await _notices(db, ana.id)) == [
        (site.key("ready"), "Your export is ready", None, None),
        (site.key("reply"), "Ben replied on Spring tour", "/blog/spring#c4", None),
    ]
    mail = await site.mail(ana.email)
    assert sorted(message.subject for message in mail) == [
        "Ben replied on Spring tour",
        "Receipt 42",
    ]
    [reply] = [message for message in mail if message.subject.startswith("Ben")]
    assert f"{site.url}/blog/spring#c4" in reply.text
    assert f'href="{site.url}/blog/spring#c4"' in (reply.html or "")


async def test_a_person_s_choice_overrides_the_default(site: Site, db: AsyncSession) -> None:
    ana = await _person(db)
    db.add(NotificationPreference(user_id=ana.id, key=site.key("reply"), in_site=True, email=False))
    db.add(NotificationPreference(user_id=ana.id, key=site.key("ready"), in_site=False, email=True))
    db.add(
        NotificationPreference(user_id=ana.id, key=site.key("receipt"), in_site=False, email=False)
    )
    await db.commit()
    Sent = notifications.Sent
    assert await notifications.notify(db, ana.id, site.key("reply"), _reply(), link="/x") == Sent(
        True, False
    )
    assert await notifications.notify(db, ana.id, site.key("ready"), {"thing": "export"}) == Sent(
        False, True
    )
    assert await notifications.notify(db, ana.id, site.key("receipt"), {"number": "7"}) == Sent(
        False, False
    )
    await db.commit()
    assert [n.key for n in await _notices(db, ana.id)] == [site.key("reply")]
    assert [m.subject for m in await site.mail(ana.email)] == ["Your export is ready"]


async def test_a_rolled_back_change_leaves_no_notice_and_sends_nothing(
    site: Site, db: AsyncSession
) -> None:
    ana = await _person(db)
    ana_id, address = ana.id, ana.email  # a rollback expires the row
    await notifications.notify(db, ana_id, site.key("reply"), _reply(), link="/x")
    await db.rollback()
    assert await _notices(db, ana_id) == []
    assert await site.mail(address) == []


async def test_no_email_to_an_unverified_address_and_nothing_to_an_account_not_active(
    site: Site, db: AsyncSession
) -> None:
    unverified = await _person(db, verified=False)
    suspended = await _person(db, status="suspended")
    Sent = notifications.Sent
    reply = site.key("reply")
    assert await notifications.notify(db, unverified.id, reply, _reply(), link="/x") == Sent(
        True, False
    )
    assert await notifications.notify(db, suspended.id, reply, _reply(), link="/x") == Sent(
        False, False
    )
    assert await notifications.notify(db, uuid.uuid4(), reply, _reply(), link="/x") == Sent(
        False, False
    )
    await db.commit()
    assert len(await _notices(db, unverified.id)) == 1
    assert await _notices(db, suspended.id) == []
    assert await site.mail(unverified.email) == []
    assert await site.mail(suspended.email) == []


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.test/x",
        "//evil.test/x",
        "/\\evil.test",
        "blog/post",
        "",
        "/a\nb",
        "/a b",
        "/" + "a" * 500,
        "javascript:alert(1)",
    ],
)
async def test_a_link_off_the_site_is_refused(site: Site, db: AsyncSession, link: str) -> None:
    ana = await _person(db)
    with pytest.raises(ValueError, match="link"):
        await notifications.notify(db, ana.id, site.key("reply"), _reply(), link=link)
    await db.rollback()
    assert await _notices(db, ana.id) == []


async def test_a_key_nobody_declares_and_a_missing_value_are_refused(
    site: Site, db: AsyncSession
) -> None:
    ana = await _person(db)
    for key in ("nobody.reply", f"{site.module}.unknown", "not a key"):
        with pytest.raises(ValueError, match="notification"):
            await notifications.notify(db, ana.id, key, _reply(), link="/x")
    with pytest.raises(ValueError, match="link"):  # REPLY uses $link
        await notifications.notify(db, ana.id, site.key("reply"), _reply())
    with pytest.raises(ValueError, match="post"):
        await notifications.notify(db, ana.id, site.key("reply"), {"who": "Ben"}, link="/x")
    await db.rollback()
    assert await _notices(db, ana.id) == []


# --- the start ---------------------------------------------------------------------------


def _start(module: InstalledModule) -> FastAPI:
    return create_app(modules=[module], config=make_config(), mailer=LogMailer())


def test_the_start_refuses_a_key_without_a_template() -> None:
    module_id = unique_id("news")
    templates = _templates(module_id)
    del templates[f"{module_id}.ready"]
    module = InstalledModule(_manifest(module_id, _kinds(module_id)), emails=templates)
    with pytest.raises(RuntimeError, match=rf"Refusing to start.*{module_id}\.ready"):
        _start(module)


def test_the_start_refuses_another_module_s_key_and_a_key_twice() -> None:
    module_id, owner = unique_id("news"), unique_id("other")
    theirs = [{"key": f"{owner}.reply", "description": "Not ours", "default": "both"}]
    # The other module has the template, so only the owner check can refuse it.
    other = InstalledModule(_manifest(owner, []), emails={f"{owner}.reply": REPLY})
    module = InstalledModule(_manifest(module_id, theirs), emails={})
    with pytest.raises(RuntimeError, match=rf"Refusing to start.*may only declare.*{owner}\.reply"):
        create_app(modules=[other, module], config=make_config(), mailer=LogMailer())
    twice = _kinds(module_id) + _kinds(module_id)[:1]
    module = InstalledModule(_manifest(module_id, twice), emails=_templates(module_id))
    with pytest.raises(RuntimeError, match=rf"Refusing to start.*{module_id}\.reply"):
        _start(module)


def test_pruning_is_one_of_the_kernel_s_jobs(site: Site) -> None:
    assert "kernel.prune_notifications" in site.app.state.worker.names
    assert notifications.PRUNE.schedule is not None


# --- the email: footer and one-click headers -----------------------------------------


def _token(message: Captured) -> str:
    headers = message.headers or {}
    url = headers["List-Unsubscribe"].strip("<>")
    assert urlsplit(url).path == UNSUBSCRIBE_API
    [token] = parse_qs(urlsplit(url).query)["token"]
    return token


async def test_a_notice_email_has_the_footer_and_the_one_click_headers(
    site: Site, db: AsyncSession
) -> None:
    ana = await _person(db)
    await notifications.notify(db, ana.id, site.key("reply"), _reply(), link="/x")
    await db.commit()
    [message] = await site.mail(ana.email)
    headers = message.headers or {}
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    token = _token(message)
    assert headers["List-Unsubscribe"] == f"<{site.url}{UNSUBSCRIBE_API}?token={token}>"
    page = f"{site.url}/notifications/unsubscribe?token={token}"
    settings_page = f"{site.url}/account/notifications"
    assert page in message.text
    assert settings_page in message.text
    assert page.replace("&", "&amp;") in (message.html or "")
    assert message.text.startswith("Ben replied on Spring tour: ")


def test_only_the_unsubscribe_headers_pass_the_checks() -> None:
    good = {"List-Unsubscribe": "<https://x.test/u>", "List-Unsubscribe-Post": "x"}
    email.check("a@site.test", "Hi", "Body", None, good)
    # Short enough that each fits the wire's 998 on one line, unfolded.
    assert len("List-Unsubscribe-Post: ") + email.MAX_HEADER <= 998
    longest = "<" + "u" * (email.MAX_HEADER - 2) + ">"
    email.check("a@site.test", "Hi", "Body", None, {"List-Unsubscribe": longest})
    with pytest.raises(ValueError, match="header"):
        email.check("a@site.test", "Hi", "Body", None, {"List-Unsubscribe": longest + "u"})
    for bad in (
        {"Bcc": "b@site.test"},
        {"List-Unsubscribe": "<https://x.test/u>\r\nBcc: b@site.test"},
        {"List-Unsubscribe": "<" + "u" * 1000 + ">"},
        {"List-Unsubscribe": ""},
    ):
        with pytest.raises(ValueError, match="header"):
            email.check("a@site.test", "Hi", "Body", None, bad)


async def test_a_mailer_without_headers_still_sends_plain_mail() -> None:
    sent: list[str] = []

    class Plain:
        async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
            sent.append(subject)

    await Checked(Plain()).send("a@site.test", "Hi", "Body")
    assert sent == ["Hi"]


# --- the routes ----------------------------------------------------------------------


async def _as(db: AsyncSession, user: User) -> dict[str, str]:
    token, _ = await sessions.start(db, user, user_agent="pytest")
    await db.commit()
    return {"cookie": f"{sessions.SESSION_COOKIE}={token}"}


def _code(response: httpx.Response) -> str:
    assert response.headers["content-type"].startswith("application/problem+json")
    code: str = response.json()["code"]
    return code


async def test_a_person_lists_their_own_notices_newest_first_in_pages(
    site: Site, db: AsyncSession
) -> None:
    ana, ben = await _person(db), await _person(db)
    for thing in ("one", "two", "three"):
        await notifications.notify(db, ana.id, site.key("ready"), {"thing": thing})
        await db.commit()
        clock.advance(1)
    await notifications.notify(db, ben.id, site.key("ready"), {"thing": "bens"})
    await db.commit()
    async with Client(site.app) as client:
        response = await client.get("/api/kernel/notifications")
        assert (response.status_code, _code(response)) == (401, "kernel.not_signed_in")
        headers = await _as(db, ana)
        first = (await client.get("/api/kernel/notifications?limit=2", headers=headers)).json()
        second = (
            await client.get(
                "/api/kernel/notifications",
                params={"limit": 2, "cursor": first["next_cursor"]},
                headers=headers,
            )
        ).json()
        bad = await client.get("/api/kernel/notifications?cursor=x", headers=headers)
        whole = (await client.get("/api/kernel/notifications?limit=3", headers=headers)).json()
    titles = [item["title"] for item in first["items"] + second["items"]]
    assert titles == ["Your three is ready", "Your two is ready", "Your one is ready"]
    assert (first["unread"], second["next_cursor"]) == (3, None)
    assert (len(whole["items"]), whole["next_cursor"]) == (3, None)  # a full last page ends it
    assert set(first["items"][0]) == {"id", "key", "title", "link", "created_at", "read_at"}
    assert (bad.status_code, _code(bad)) == (422, "kernel.invalid_request")


async def test_read_marks_only_the_person_s_own_notices(site: Site, db: AsyncSession) -> None:
    ana, ben = await _person(db), await _person(db)
    for person in (ana, ana, ben):
        await notifications.notify(db, person.id, site.key("ready"), {"thing": "x"})
    await db.commit()
    [bens] = await _notices(db, ben.id)
    first, _ = await _notices(db, ana.id)
    async with Client(site.app) as client:
        headers = await _as(db, ana)
        response = await client.post(
            "/api/kernel/notifications/read",
            json={"ids": [str(first.id), str(bens.id)]},
            headers=headers,
        )
        assert response.status_code == 204
        listed = (await client.get("/api/kernel/notifications", headers=headers)).json()
        assert listed["unread"] == 1
        for body in ({}, {"ids": []}, {"ids": ["x"]}, {"all": False}):
            refused = await client.post(
                "/api/kernel/notifications/read", json=body, headers=headers
            )
            assert (refused.status_code, _code(refused)) == (422, "kernel.invalid_request")
        response = await client.post(
            "/api/kernel/notifications/read", json={"all": True}, headers=headers
        )
        assert response.status_code == 204
    assert all(n.read_at is not None for n in await _notices(db, ana.id))
    assert [n.read_at for n in await _notices(db, ben.id)] == [None]


async def test_preferences_list_the_keys_of_modules_on_and_change(
    site: Site, db: AsyncSession
) -> None:
    ana = await _person(db)
    async with Client(site.app) as client:
        headers = await _as(db, ana)
        listed = (await client.get("/api/kernel/notifications/preferences", headers=headers)).json()
        # The kernel's own keys come first, whatever modules are on (decision 0039).
        kernel_keys = [item["key"] for item in listed["items"] if item["key"].startswith("kernel.")]
        assert kernel_keys == ["kernel.content_removed"]
        assert listed["items"][len(kernel_keys) :] == [
            {
                "key": site.key("reply"),
                "description": "Someone replied to you",
                "default": "both",
                "in_site": True,
                "email": True,
            },
            {
                "key": site.key("ready"),
                "description": "Your export is ready",
                "default": "in_site",
                "in_site": True,
                "email": False,
            },
            {
                "key": site.key("receipt"),
                "description": "A receipt",
                "default": "email",
                "in_site": False,
                "email": True,
            },
        ]
        changed = await client.put(
            "/api/kernel/notifications/preferences",
            json={site.key("reply"): {"in_site": False, "email": True}},
            headers=headers,
        )
        assert changed.status_code == 200
        assert changed.json()["items"][len(kernel_keys)] == {
            "key": site.key("reply"),
            "description": "Someone replied to you",
            "default": "both",
            "in_site": False,
            "email": True,
        }
        for body in (
            {"nobody.reply": {"in_site": True, "email": True}},
            {site.key("reply"): {"in_site": True}},
            {site.key("reply"): {"in_site": "yes", "email": True}},
        ):
            refused = await client.put(
                "/api/kernel/notifications/preferences", json=body, headers=headers
            )
            assert (refused.status_code, _code(refused)) == (422, "kernel.invalid_request")
        db.add(ModuleState(module_id=site.module, enabled=False))
        await db.commit()
        try:
            listed = (
                await client.get("/api/kernel/notifications/preferences", headers=headers)
            ).json()
            off = await client.put(
                "/api/kernel/notifications/preferences",
                json={site.key("ready"): {"in_site": True, "email": True}},
                headers=headers,
            )
        finally:
            await db.delete(await db.get(ModuleState, site.module))
            await db.commit()
    assert [item["key"] for item in listed["items"]] == kernel_keys
    assert (off.status_code, _code(off)) == (422, "kernel.invalid_request")
    assert notifications.Sent(False, True) == await notifications.notify(
        db, ana.id, site.key("reply"), _reply(), link="/x"
    )
    await db.rollback()


# --- one-click unsubscribe -------------------------------------------------------------


async def _mailed_token(site: Site, db: AsyncSession, person: User) -> str:
    await notifications.notify(db, person.id, site.key("reply"), _reply(), link="/x")
    await db.commit()
    [message] = await site.mail(person.email)
    return _token(message)


async def test_one_click_turns_email_off_for_that_key_without_a_session(
    site: Site, db: AsyncSession
) -> None:
    ana = await _person(db)
    token = await _mailed_token(site, db, ana)
    async with Client(site.app) as client:
        looked = await client.get(UNSUBSCRIBE_API, params={"token": token})
        assert looked.json() == {
            "key": site.key("reply"),
            "description": "Someone replied to you",
            "email": True,
        }
        assert await db.get(NotificationPreference, (ana.id, site.key("reply"))) is None
        clicked = await client.post(
            UNSUBSCRIBE_API,
            params={"token": token},
            content="List-Unsubscribe=One-Click",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://mail.example.test",
                "sec-fetch-site": "cross-site",
            },
        )
        assert clicked.status_code == 200
        assert (await client.get(UNSUBSCRIBE_API, params={"token": token})).json()["email"] is False
        # The exemption is this route's alone.
        elsewhere = await client.post(
            "/api/kernel/notifications/read",
            json={"all": True},
            headers={"origin": "https://mail.example.test", "sec-fetch-site": "cross-site"},
        )
        assert (elsewhere.status_code, _code(elsewhere)) == (403, "kernel.cross_site_write")
    Sent = notifications.Sent
    ana_id = ana.id  # a rollback expires the row
    assert await notifications.notify(db, ana_id, site.key("reply"), _reply(), link="/x") == Sent(
        True, False
    )
    await db.rollback()
    receipt = await notifications.notify(db, ana_id, site.key("receipt"), {"number": "1"})
    assert receipt == Sent(False, True)  # another key keeps its email
    await db.rollback()


async def test_a_forged_or_altered_token_is_a_404(site: Site, db: AsyncSession) -> None:
    ana, ben = await _person(db), await _person(db)
    token = await _mailed_token(site, db, ana)
    person, _, rest = token.partition(".")
    key, _, mac = rest.rpartition(".")
    forged = [
        f"{person}.{key}.{'0' * len(mac)}",
        f"{ben.id.hex}.{key}.{mac}",
        f"{person}.{site.key('receipt')}.{mac}",
        f"{uuid.uuid4().hex}.{key}.{mac}",
        "nonsense",
        "",
    ]
    async with Client(site.app) as client:
        for bad in forged:
            for method in ("GET", "POST"):
                response = await client.request(method, UNSUBSCRIBE_API, params={"token": bad})
                assert (response.status_code, _code(response)) == (404, "kernel.not_found"), bad
    assert await db.get(NotificationPreference, (ana.id, key)) is None
    assert await db.get(NotificationPreference, (ben.id, key)) is None


# --- pruning -------------------------------------------------------------------------


async def test_pruning_keeps_a_notice_90_days_after_it_s_read_and_a_year_at_most(
    site: Site, db: AsyncSession, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notifications, "BATCH", 1)
    ana = await _person(db)
    now = clock.now()
    day = timedelta(days=1)
    rows: dict[str, tuple[Any, Any]] = {
        "read-long-ago": (now - 200 * day, now - 91 * day),
        "read-lately": (now - 200 * day, now - 89 * day),
        "old-unread": (now - 366 * day, None),
        "young-unread": (now - 364 * day, None),
        "old-read-lately": (now - 366 * day, now - 1 * day),
    }
    for title, (created, read) in rows.items():
        await db.execute(
            insert(Notification).values(
                id=uuid.uuid4(),
                user_id=ana.id,
                key=site.key("ready"),
                title=title,
                created_at=created,
                read_at=read,
            )
        )
    await db.commit()
    context = jobs.Context(
        job_id=uuid.uuid4(),
        name="kernel.prune_notifications",
        try_number=1,
        _database=database,
        _mailer=LogMailer(),
    )
    await notifications.PRUNE.run(context, {})
    assert sorted(n.title for n in await _notices(db, ana.id)) == ["read-lately", "young-unread"]


def test_the_module_template_s_keys_have_their_templates() -> None:
    folder = Path(__file__).resolve().parents[2] / "modules" / "_template"
    listed = json.loads((folder / "module.json").read_text("utf-8"))
    spec = importlib.util.spec_from_file_location(
        f"template_emails_{uuid.uuid4().hex[:8]}", folder / "backend" / "my_module" / "emails.py"
    )
    assert spec is not None
    assert spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    kinds = notifications.build([(listed["id"], listed["notifications"])], loaded.EMAILS)
    assert list(kinds) == ["my-module.something_happened"]


@pytest.mark.parametrize(
    "entry",
    [
        {"key": "news.reply", "description": "Replies", "default": "loud"},
        {"key": "news.reply", "default": "both"},
        "news.reply",
    ],
)
def test_build_refuses_a_key_without_a_description_or_a_default(entry: Any) -> None:
    with pytest.raises(ValueError, match="news"):
        notifications.build([("news", [entry])], {"news.reply": REPLY})


async def test_a_title_past_a_subject_s_length_is_refused(site: Site, db: AsyncSession) -> None:
    ana = await _person(db)
    ana_id = ana.id
    with pytest.raises(ValueError, match="title"):
        await notifications.notify(
            db, ana_id, site.key("reply"), {"who": "B" * 300, "post": "x"}, link="/x"
        )
    await db.rollback()
    assert await _notices(db, ana_id) == []


async def test_an_unsubscribe_link_for_an_account_gone_is_a_404(
    site: Site, db: AsyncSession
) -> None:
    gone = await _person(db)
    token = notifications.unsubscribe_token(gone.id, site.key("reply"))
    await db.delete(gone)
    await db.commit()
    async with Client(site.app) as client:
        for method in ("GET", "POST"):
            response = await client.request(method, UNSUBSCRIBE_API, params={"token": token})
            assert (response.status_code, _code(response)) == (404, "kernel.not_found")


@pytest.mark.parametrize("name", ["reply", "ready"])
async def test_a_nul_in_a_value_is_refused_before_anything_is_added(
    site: Site, db: AsyncSession, name: str
) -> None:
    """CodeRabbit on #69: the notice was added before the email's checks
    refused a NUL, so a caller that caught the error could still commit it."""
    ana = await _person(db)
    ana_id, address = ana.id, ana.email
    context = {"who": f"B{chr(0)}", "post": "x", "thing": f"x{chr(0)}"}
    with pytest.raises(ValueError, match="NUL"):
        await notifications.notify(db, ana_id, site.key(name), context, link="/x")
    assert list(db.new) == []
    await db.commit()  # a caller that catches it and carries on writes nothing of it
    assert await _notices(db, ana_id) == []
    assert await site.mail(address) == []


async def test_unsubscribing_never_undoes_a_choice_made_meanwhile(
    site: Site, db: AsyncSession, database: Database
) -> None:
    """CodeRabbit on #69: unsubscribe read `in_site`, then wrote it back. Here
    a change to `in_site` holds the row while the one-click runs; once it
    commits, the one-click must leave it as the change made it."""
    ana = await _person(db)
    ana_id = ana.id
    key = site.key("reply")
    db.add(NotificationPreference(user_id=ana_id, key=key, in_site=True, email=True))
    await db.commit()
    token = notifications.unsubscribe_token(ana_id, key)
    async with database.sessions() as holder:
        await holder.execute(
            update(NotificationPreference)
            .where(NotificationPreference.user_id == ana_id, NotificationPreference.key == key)
            .values(in_site=False)
        )
        async with Client(site.app) as client:
            clicked = asyncio.create_task(client.post(UNSUBSCRIBE_API, params={"token": token}))
            for _ in range(200):  # until the one-click waits on the held row
                waiting = await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                        "AND query LIKE '%kernel_notification_preference%'"
                    )
                )
                await db.rollback()
                if waiting:
                    break
                await asyncio.sleep(0.025)
            else:
                pytest.fail("the one-click never waited on the held row")
            await holder.commit()
            response = await clicked
    assert response.status_code == 200
    row = await db.get(NotificationPreference, (ana_id, key), populate_existing=True)
    assert row is not None
    assert (row.in_site, row.email) == (False, False)


async def test_an_email_the_checks_refuse_adds_no_notice_either(
    site: Site, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CodeRabbit on #69: the email is queued first, so when its checks refuse
    it, nothing of the notice is left in the caller's session."""
    ana = await _person(db)
    ana_id = ana.id

    async def refused(*args: object, **kwargs: object) -> None:
        raise ValueError("A message's text must hold 1 to 262144 characters and no NUL.")

    monkeypatch.setattr(notifications.email, "queue_message", refused)
    with pytest.raises(ValueError, match="text"):
        await notifications.notify(db, ana_id, site.key("reply"), _reply(), link="/x")
    assert list(db.new) == []
    await db.rollback()
