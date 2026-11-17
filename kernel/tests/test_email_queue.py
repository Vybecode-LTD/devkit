"""Mail through the jobs queue (decision 0035; contract k3-jobs): `email.queue`
renders now and adds a sealed `kernel.send_mail` job to the caller's
transaction; the worker sends it, retrying what the provider says may work
later and giving up on a refusal. The kernel's own mails go this way."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select

from kernel import clock, crypto, email
from kernel.app import create_app
from kernel.auth.accounts import normal_email
from kernel.auth.models import User, UserRole
from kernel.email import CapturingMailer, MailError, Template
from kernel.models import Job as JobRow
from kernel.modules import InstalledModule

from .conftest import SITE, make_config, manifest

REPLY = Template(
    subject="$name replied on $site_name",
    text="$name wrote: $body\n",
    html="<p><b>$name</b> wrote: $body</p>",
)
CONTEXT = {"name": "Ana", "body": "Nice beat"}
KERNEL = Path(__file__).resolve().parents[1] / "backend" / "kernel"


class Failing:
    """A mailer whose provider answers with `error`."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        raise self.error


Build = Callable[[Any], FastAPI]


@pytest_asyncio.fixture(loop_scope="session")
async def build(migrated_url: str) -> AsyncIterator[Build]:
    """Apps on the test database with `mailer`, each disposed after the test."""
    made: list[FastAPI] = []

    def app(mailer: Any) -> FastAPI:
        module = InstalledModule(manifest("blog"), emails={"blog.comment_reply": REPLY})
        built = create_app(
            modules=[module], config=make_config(database_url=migrated_url), mailer=mailer
        )
        made.append(built)
        return built

    yield app
    for built in made:
        await built.state.database.dispose()


def _address() -> str:
    return f"reader.{uuid.uuid4().hex[:10]}@site.test"


async def _mail_jobs(app: FastAPI) -> set[uuid.UUID]:
    async with app.state.database.sessions() as db:
        found = await db.scalars(select(JobRow.id).where(JobRow.name == email.SEND_MAIL.name))
        return set(found.all())


async def _queued(app: FastAPI, to: str) -> uuid.UUID:
    """Queues blog.comment_reply for `to` and returns its job's id."""
    before = await _mail_jobs(app)
    async with app.state.database.sessions() as db:
        await email.queue(db, "blog.comment_reply", to, CONTEXT)
        await db.commit()
    [made] = await _mail_jobs(app) - before
    return made


async def _row(app: FastAPI, job_id: uuid.UUID) -> JobRow:
    async with app.state.database.sessions() as db:
        row = await db.get(JobRow, job_id)
        assert row is not None
        return row


async def test_a_queued_mail_is_rendered_now_and_sent_by_the_worker(build: Build) -> None:
    captured = CapturingMailer()
    app = build(captured)
    to = _address()
    await _queued(app, to)
    assert captured.to(to) == []
    await app.state.worker.run_due()
    [sent] = captured.to(to)
    assert (sent.subject, sent.text, sent.html) == (
        f"Ana replied on {app.state.config.site_name}",
        "Ana wrote: Nice beat\n",
        "<p><b>Ana</b> wrote: Nice beat</p>",
    )


async def test_a_queued_mail_is_sealed_and_wiped_once_sent(build: Build) -> None:
    app = build(CapturingMailer())
    to = _address()
    job_id = await _queued(app, to)
    row = await _row(app, job_id)
    assert row.sealed is True
    assert to not in (row.payload or "")
    assert json.loads(crypto.open(row.payload or ""))["to"] == to
    await app.state.worker.run_due()
    row = await _row(app, job_id)
    assert (row.state, row.payload) == ("done", None)


async def test_a_rolled_back_mail_is_never_sent(build: Build) -> None:
    captured = CapturingMailer()
    app = build(captured)
    to = _address()
    before = await _mail_jobs(app)
    async with app.state.database.sessions() as db:
        await email.queue(db, "blog.comment_reply", to, CONTEXT)
        await db.rollback()
    await app.state.worker.run_due()
    assert captured.to(to) == []
    assert await _mail_jobs(app) == before


async def test_a_bad_message_is_refused_before_anything_is_queued(build: Build) -> None:
    app = build(CapturingMailer())
    before = await _mail_jobs(app)
    async with app.state.database.sessions() as db:
        with pytest.raises(ValueError, match="address"):
            await email.queue(db, "blog.comment_reply", "one@a.test, two@b.test", CONTEXT)
        with pytest.raises(ValueError, match=r"blog\.missing"):
            await email.queue(db, "blog.missing", _address(), CONTEXT)
        await db.commit()
    assert await _mail_jobs(app) == before


async def test_a_retryable_failure_waits_the_provider_s_retry_after(build: Build) -> None:
    app = build(Failing(MailError("rate limited", retryable=True, retry_after=120)))
    job_id = await _queued(app, _address())
    before = clock.now()
    await app.state.worker.run_due()
    row = await _row(app, job_id)
    assert (row.state, row.tries, row.last_error) == ("queued", 1, "Retry")
    assert 119 <= (row.run_at - before).total_seconds() <= 125
    assert row.payload is not None  # still sealed, for the next try


async def test_a_retryable_failure_without_a_wait_backs_off(build: Build) -> None:
    app = build(Failing(MailError("connection lost", retryable=True)))
    job_id = await _queued(app, _address())
    before = clock.now()
    await app.state.worker.run_due()
    row = await _row(app, job_id)
    assert row.state == "queued"
    assert 27 <= (row.run_at - before).total_seconds() <= 34


async def test_a_refusal_is_dead_at_once_and_wiped(build: Build) -> None:
    app = build(Failing(MailError("address refused", retryable=False)))
    job_id = await _queued(app, _address())
    await app.state.worker.run_due()
    row = await _row(app, job_id)
    assert (row.state, row.tries, row.last_error, row.payload) == ("dead", 1, "Abandon", None)


async def test_a_mail_is_tried_five_times(build: Build) -> None:
    app = build(Failing(MailError("down", retryable=True, retry_after=0)))
    job_id = await _queued(app, _address())
    for _ in range(5):
        await app.state.worker.run_due()
    row = await _row(app, job_id)
    assert (row.state, row.tries) == ("dead", 5)


# --- the kernel's own mails --------------------------------------------------------------


async def test_a_kernel_mail_waits_in_the_queue_until_the_worker_runs(build: Build) -> None:
    captured = CapturingMailer()
    app = build(captured)
    address = f"Kim.{uuid.uuid4().hex[:10]}@Site.test"
    async with app.state.database.sessions() as db:
        user = User(
            email=address, email_normal=normal_email(address), email_verified_at=clock.now()
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role_id="member"))
        await db.commit()
    before = await _mail_jobs(app)
    # A plain transport: nothing runs the queue after the answer.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    headers = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}
    async with httpx.AsyncClient(transport=transport, base_url=SITE, headers=headers) as http:
        asked = await http.post("/api/auth/password/reset-request", json={"email": address})
    assert asked.status_code == 202
    assert captured.to(address) == []
    assert len(await _mail_jobs(app) - before) == 1
    await app.state.worker.run_due()
    [sent] = captured.to(address)
    assert "/auth/reset?token=" in sent.text


def test_no_kernel_code_sends_mail_around_the_queue() -> None:
    """Only the queue's job and `email.send` hand a message to a mailer; no
    route sends after its answer any more."""
    for path in KERNEL.rglob("*.py"):
        source = path.read_text("utf-8")
        assert "BackgroundTasks" not in source, path.name
        if path.name not in ("email.py", "mail_adapters.py"):
            assert "mailer.send(" not in source, path.name


async def test_any_message_check_accepts_fits_the_queue(build: Build) -> None:
    """The longest bodies `check` takes, in the characters that grow most
    as UTF-8 and as JSON, still queue and arrive whole (Codex on #63)."""
    captured = CapturingMailer()
    app = build(captured)
    to = _address()
    wide = chr(0x6C49) * email.MAX_BODY  # three bytes each in UTF-8
    escaped = chr(1) * (email.MAX_BODY - 1) + "x"  # six bytes each in JSON
    async with app.state.database.sessions() as db:
        await email.queue_message(db, to, chr(0x1F4E8) * email.MAX_SUBJECT, wide, escaped)
        await db.commit()
    await app.state.worker.run_due()
    [sent] = captured.to(to)
    assert (sent.text, sent.html) == (wide, escaped)
