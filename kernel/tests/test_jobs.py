"""kernel.jobs: declaring handlers, enqueueing in the caller's transaction, and
the checks create_app makes (contract k3-jobs, decision 0035). The worker
that runs them is test_worker.py's."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto, jobs
from kernel.app import create_app
from kernel.models import Job as JobRow
from kernel.modules import InstalledModule, Manifest
from kernel.tests.conftest import make_config, unique_id


async def _nothing(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    return None


async def _tick(ctx: jobs.Context) -> None:
    return None


def _module(
    module_id: str, *declared: jobs.Job, scheduled: list[dict[str, str]] | None = None
) -> InstalledModule:
    raw: dict[str, Any] = {
        "id": module_id,
        "name": module_id.title(),
        "version": "0.1.0",
        "requires": {"kernel": "^0.1", "modules": {}},
    }
    if scheduled is not None:
        raw["jobs"] = scheduled
    return InstalledModule(Manifest.from_dict(raw), jobs=tuple(declared))


# --- declaring ------------------------------------------------------------------------


def test_a_handler_is_a_job_named_by_its_owner() -> None:
    job = jobs.handler("blog.send_digest", tries=3, timeout=60)(_nothing)
    assert isinstance(job, jobs.Job)
    assert (job.name, job.owner, job.tries, job.timeout, job.schedule) == (
        "blog.send_digest",
        "blog",
        3,
        60,
        None,
    )


def test_a_handler_s_defaults() -> None:
    job = jobs.handler("blog.send_digest")(_nothing)
    assert (job.tries, job.timeout) == (5, 300)


def test_a_scheduled_job_carries_its_cron_line_and_runs_once_by_default() -> None:
    job = jobs.scheduled("*/5 * * * *", "print-on-demand.sync_catalog")(_tick)
    assert job.owner == "print-on-demand"
    assert job.schedule is not None
    assert job.schedule.line == "*/5 * * * *"
    assert job.tries == 1


@pytest.mark.parametrize(
    "name",
    [
        "blog",
        "Blog.digest",
        "blog.Digest",
        "blog.",
        ".digest",
        "blog.dig-est",
        "blog.9digest",
        "-blog.digest",
        "blog-.digest",
        "blog.digest.more",
        "a" * 70 + ".b" * 40,
    ],
)
def test_a_badly_named_job_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        jobs.handler(name)(_nothing)


@pytest.mark.parametrize(("tries", "timeout"), [(0, 300), (101, 300), (5, 0), (5, 6 * 3600 + 1)])
def test_tries_and_timeouts_have_bounds(tries: int, timeout: float) -> None:
    with pytest.raises(ValueError, match=r"tries|timeout"):
        jobs.handler("blog.send_digest", tries=tries, timeout=timeout)(_nothing)


def test_a_bad_cron_line_is_refused_when_declared() -> None:
    with pytest.raises(ValueError, match="cron"):
        jobs.scheduled("61 * * * *", "blog.publish_scheduled")(_tick)


def test_a_handler_must_be_a_coroutine_function() -> None:
    def plain(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        return None

    with pytest.raises(TypeError, match="async"):
        jobs.handler("blog.send_digest")(plain)  # type: ignore[arg-type]


# --- create_app's checks --------------------------------------------------------------


def _refused(*installed: InstalledModule) -> str:
    with pytest.raises(RuntimeError, match="Refusing to start") as refused:
        create_app(modules=list(installed), config=make_config())
    return str(refused.value)


def test_a_module_declares_only_its_own_jobs() -> None:
    owner = unique_id()
    message = _refused(_module(owner, jobs.handler("other.send")(_nothing)))
    assert owner in message
    assert "other.send" in message


def test_a_module_can_t_declare_the_kernel_s_jobs() -> None:
    message = _refused(_module(unique_id(), jobs.handler("kernel.send_mail")(_nothing)))
    assert "kernel.send_mail" in message


def test_a_job_declared_twice_is_refused() -> None:
    owner = unique_id()
    job = jobs.handler(f"{owner}.send")(_nothing)
    assert f"{owner}.send" in _refused(_module(owner, job, job))


def test_a_scheduled_job_must_be_in_the_manifest() -> None:
    owner = unique_id()
    job = jobs.scheduled("*/5 * * * *", f"{owner}.sweep")(_tick)
    message = _refused(_module(owner, job, scheduled=[]))
    assert f"{owner}.sweep" in message
    assert "module.json" in message


def test_a_scheduled_job_must_keep_the_manifest_s_schedule() -> None:
    owner = unique_id()
    job = jobs.scheduled("*/5 * * * *", f"{owner}.sweep")(_tick)
    message = _refused(_module(owner, job, scheduled=[{"name": "sweep", "schedule": "0 * * * *"}]))
    assert "0 * * * *" in message
    assert "*/5 * * * *" in message


def test_a_manifest_job_needs_its_code() -> None:
    owner = unique_id()
    message = _refused(_module(owner, scheduled=[{"name": "sweep", "schedule": "0 * * * *"}]))
    assert f"{owner}.sweep" in message


def test_a_manifest_s_scheduled_job_isnt_a_plain_handler() -> None:
    owner = unique_id()
    job = jobs.handler(f"{owner}.sweep")(_nothing)
    message = _refused(_module(owner, job, scheduled=[{"name": "sweep", "schedule": "0 * * * *"}]))
    assert f"{owner}.sweep" in message


def test_a_module_s_jobs_reach_the_app_s_worker() -> None:
    owner = unique_id()
    sweep = jobs.scheduled("0 * * * *", f"{owner}.sweep")(_tick)
    send = jobs.handler(f"{owner}.send")(_nothing)
    app = create_app(
        modules=[
            _module(owner, sweep, send, scheduled=[{"name": "sweep", "schedule": "0 * * * *"}])
        ],
        config=make_config(),
    )
    names = app.state.worker.names
    assert {
        f"{owner}.sweep",
        f"{owner}.send",
        "kernel.send_mail",
        "kernel.prune_jobs",
        "kernel.remove_unverified",
    } <= names


# --- enqueueing -------------------------------------------------------------------------


async def _row(db: AsyncSession, job_id: uuid.UUID) -> JobRow:
    row = await db.get(JobRow, job_id, populate_existing=True)
    assert row is not None
    return row


async def test_enqueue_adds_a_queued_row_in_the_caller_s_transaction(db: AsyncSession) -> None:
    owner = unique_id()
    job_id = await jobs.enqueue(db, f"{owner}.send", {"post_id": 7})
    assert job_id is not None
    await db.commit()
    row = await _row(db, job_id)
    assert (row.name, row.module, row.state, row.tries, row.sealed) == (
        f"{owner}.send",
        owner,
        "queued",
        0,
        False,
    )
    assert json.loads(row.payload or "") == {"post_id": 7}
    assert abs((row.run_at - clock.now()).total_seconds()) < 5


async def test_a_rolled_back_enqueue_leaves_no_job(db: AsyncSession) -> None:
    owner = unique_id()
    await jobs.enqueue(db, f"{owner}.send", {"post_id": 7})
    await db.rollback()
    count = await db.scalar(select(func.count()).select_from(JobRow).where(JobRow.module == owner))
    assert count == 0


async def test_run_at_sets_when_it_s_due(db: AsyncSession) -> None:
    later = datetime(2030, 1, 2, 3, 4, tzinfo=UTC)
    job_id = await jobs.enqueue(db, f"{unique_id()}.send", run_at=later)
    await db.commit()
    assert job_id is not None
    assert (await _row(db, job_id)).run_at == later


async def test_run_at_must_say_its_zone(db: AsyncSession) -> None:
    with pytest.raises(ValueError, match="UTC"):
        await jobs.enqueue(db, f"{unique_id()}.send", run_at=datetime(2030, 1, 2))


async def test_a_key_dedupes_while_the_job_is_live(db: AsyncSession) -> None:
    name = f"{unique_id()}.send"
    first = await jobs.enqueue(db, name, {"n": 1}, key="post-7")
    second = await jobs.enqueue(db, name, {"n": 2}, key="post-7")
    other_key = await jobs.enqueue(db, name, {"n": 3}, key="post-8")
    await db.commit()
    assert first is not None
    assert second is None
    assert other_key is not None


async def test_a_key_is_free_again_once_its_job_ended(db: AsyncSession) -> None:
    name = f"{unique_id()}.send"
    first = await jobs.enqueue(db, name, key="post-7")
    await db.commit()
    assert first is not None
    for state in ("done", "dead"):
        row = await _row(db, first)
        row.state = state
        await db.commit()
        again = await jobs.enqueue(db, name, key="post-7")
        await db.commit()
        assert again is not None
        first = again


async def test_the_same_key_under_another_name_is_another_job(db: AsyncSession) -> None:
    owner = unique_id()
    assert await jobs.enqueue(db, f"{owner}.send", key="k") is not None
    assert await jobs.enqueue(db, f"{owner}.other", key="k") is not None
    await db.commit()


async def test_a_sealed_payload_isn_t_readable_in_the_table(db: AsyncSession) -> None:
    job_id = await jobs.enqueue(db, f"{unique_id()}.send", {"code": "481516"}, sealed=True)
    await db.commit()
    assert job_id is not None
    row = await _row(db, job_id)
    assert row.sealed is True
    assert "481516" not in (row.payload or "")
    assert json.loads(crypto.open(row.payload or "")) == {"code": "481516"}


@pytest.mark.parametrize(
    "payload",
    [
        {"when": datetime(2030, 1, 1, tzinfo=UTC)},
        {"n": float("nan")},
        {"x": object()},
        {1: "a number as a key"},
    ],
)
async def test_a_payload_must_be_plain_json(db: AsyncSession, payload: dict[Any, Any]) -> None:
    with pytest.raises(ValueError, match="JSON"):
        await jobs.enqueue(db, f"{unique_id()}.send", payload)


async def test_a_payload_is_an_object(db: AsyncSession) -> None:
    with pytest.raises(ValueError, match="object"):
        await jobs.enqueue(db, f"{unique_id()}.send", ["a", "list"])  # type: ignore[arg-type]


async def test_a_payload_holds_at_most_64_kib(db: AsyncSession) -> None:
    name = f"{unique_id()}.send"
    fits = {"x": "a" * (64 * 1024 - len('{"x":""}'))}
    assert await jobs.enqueue(db, name, fits) is not None
    with pytest.raises(ValueError, match="64 KiB"):
        await jobs.enqueue(db, name, {"x": "a" * (64 * 1024)})
    await db.rollback()


@pytest.mark.parametrize("key", ["", "a" * 201, "line\nbreak", "tab\tbed"])
async def test_a_bad_key_is_refused(db: AsyncSession, key: str) -> None:
    with pytest.raises(ValueError, match="key"):
        await jobs.enqueue(db, f"{unique_id()}.send", key=key)


async def test_enqueue_checks_the_name(db: AsyncSession) -> None:
    with pytest.raises(ValueError, match="name"):
        await jobs.enqueue(db, "no-owner", {})


async def test_a_refusal_never_holds_the_payload(db: AsyncSession) -> None:
    secret = "do-not-print-" + uuid.uuid4().hex
    with pytest.raises(ValueError, match="64 KiB") as refused:
        await jobs.enqueue(db, f"{unique_id()}.send", {"secret": secret, "x": "a" * (64 * 1024)})
    assert secret not in str(refused.value)


def test_a_job_s_retry_carries_its_wait() -> None:
    assert jobs.Retry(after=12.5).after == 12.5
    assert jobs.Retry().after is None
    with pytest.raises(ValueError, match="seconds"):
        jobs.Retry(after=-1)


def test_backoff_doubles_from_30_seconds_to_an_hour_with_jitter() -> None:
    for tries, base in ((1, 30), (2, 60), (3, 120), (7, 1920), (8, 3600), (20, 3600)):
        for _ in range(20):
            delay = jobs.backoff(tries)
            assert base * 0.9 <= delay <= base * 1.1, (tries, delay)


def test_the_jobs_lease_is_longer_than_its_renewal() -> None:
    assert jobs.LEASE > 2 * jobs.RENEW_EVERY
