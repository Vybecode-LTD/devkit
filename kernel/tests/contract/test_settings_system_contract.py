"""The admin's settings, features and System (K4 contract §2, additions 6 to
8, change 19; docs/contracts/auth-api.md, Staff), over HTTP only, like the
rest of the contract suite.

The tests work on the harness's probe modules (`probe` and `probe-addon`,
which requires it) and their settings section, so the site's own sections
keep their values for the rest of the suite. Settings outlive a test, so each
reads the version it starts from; switches are put back and failed jobs
discarded before a test ends.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from .conftest import PASSWORD, Api, User

SETTINGS = "/api/kernel/admin/settings"
PROBE = f"{SETTINGS}/probe"
AUTH = f"{SETTINGS}/kernel.auth"
MODULES = "/api/kernel/admin/modules"
SYSTEM = "/api/kernel/admin/system"
DEAD = "/api/kernel/admin/jobs/dead"
JOBS = "/api/kernel/admin/jobs"
ROLES = "/api/auth/admin/roles"
AUDIT = "/api/kernel/admin/audit"
PING = "/api/probe/ping"
MINUTE = 60


def _code(response: httpx.Response) -> tuple[int, str | None]:
    body = response.json() if response.content else {}
    return response.status_code, body.get("code")


async def _as_owner(api: Api) -> User:
    owner = await api.make_user(roles=["owner"], totp=True)
    await api.signed_in_as(owner)
    return owner


async def _staff_holding(api: Api, *permissions: str) -> Api:
    """A browser signed in as staff whose one role carries `permissions`."""
    owner_side = api.another_browser()
    await _as_owner(owner_side)
    made = await owner_side.http.post(
        ROLES,
        json={
            "id": f"r-{uuid.uuid4().hex[:10]}",
            "name": "Helper",
            "description": "",
            "permissions": list(permissions),
        },
    )
    assert made.status_code == 201, made.text
    person = await api.make_user(roles=[made.json()["id"]], totp=True)
    staff = api.another_browser()
    await staff.signed_in_as(person)
    return staff


async def _logged(api: Api, kind: str, ident: str) -> list[dict[str, Any]]:
    response = await api.http.get(AUDIT, params={"target_type": kind, "target_id": ident})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def _form(api: Api, path: str = PROBE) -> dict[str, Any]:
    response = await api.http.get(path)
    assert response.status_code == 200, response.text
    form: dict[str, Any] = response.json()
    return form


async def _save(api: Api, changes: dict[str, Any], *, version: int, path: str = PROBE) -> Any:
    return await api.http.put(path, json={"version": version, "changes": changes})


def _word() -> str:
    return f"hello {uuid.uuid4().hex[:8]}"


# --- settings: GET and PUT /api/kernel/admin/settings/{id}, and its history -------------------


async def test_a_section_reads_as_its_version_and_values(api: Api) -> None:
    await _as_owner(api)
    form = await _form(api)
    assert set(form) == {"version", "values"}
    assert isinstance(form["version"], int)
    assert form["version"] >= 0
    assert set(form["values"]) == {"greeting", "count", "token"}
    # A secret reads as whether one is kept and how often it changed, never its value.
    assert set(form["values"]["token"]) == {"kept", "changes"}


async def test_a_section_no_module_registers_is_404(api: Api) -> None:
    await _as_owner(api)
    for response in (
        await api.http.get(f"{SETTINGS}/nothing-here"),
        await api.http.put(f"{SETTINGS}/nothing-here", json={"version": 0, "changes": {}}),
        await api.http.get(f"{SETTINGS}/nothing-here/history"),
    ):
        assert _code(response) == (404, "kernel.settings_unknown"), response.text


async def test_a_save_changes_its_fields_moves_the_version_on_and_is_logged(api: Api) -> None:
    owner = await _as_owner(api)
    start = (await _form(api))["version"]
    word = _word()
    saved = await _save(api, {"greeting": word}, version=start)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"version": start + 1, "changed": ["greeting"], "merged": []}
    form = await _form(api)
    assert form["version"] == start + 1
    assert form["values"]["greeting"] == word

    history = await api.http.get(f"{PROBE}/history")
    assert history.status_code == 200, history.text
    newest = history.json()["items"][0]
    assert newest == {
        "number": start + 1,
        "changed": ["greeting"],
        "via": "form",
        "saved_at": newest["saved_at"],
        "saved_by_id": owner.id,
    }
    assert history.json()["people"][owner.id] == {"name": None, "email": owner.email}
    assert "values" not in newest

    logged = await _logged(api, "kernel.settings", "probe")
    assert logged[0]["action"] == "kernel.settings_saved"
    assert logged[0]["actor_id"] == owner.id
    assert logged[0]["details"]["changed"] == ["greeting"]


async def test_a_save_that_changes_nothing_keeps_the_version(api: Api) -> None:
    await _as_owner(api)
    form = await _form(api)
    same = await _save(api, {"greeting": form["values"]["greeting"]}, version=form["version"])
    assert same.status_code == 200, same.text
    assert same.json() == {"version": form["version"], "changed": [], "merged": []}


async def test_a_stale_save_keeps_others_changes_and_says_so(api: Api) -> None:
    await _as_owner(api)
    other = api.another_browser()
    await _as_owner(other)
    opened = await _form(api)
    # Someone else saves the greeting after this form was read.
    theirs = _word()
    first = await _save(other, {"greeting": theirs}, version=opened["version"])
    assert first.status_code == 200, first.text
    # This form sends the greeting as it read it, and a new count.
    count = (opened["values"]["count"] % 50) + 1
    mine = await _save(
        api,
        {"greeting": opened["values"]["greeting"], "count": count},
        version=opened["version"],
    )
    assert mine.status_code == 200, mine.text
    assert mine.json() == {
        "version": opened["version"] + 2,
        "changed": ["count"],
        "merged": ["greeting"],
    }
    values = (await _form(api))["values"]
    assert values["greeting"] == theirs
    assert values["count"] == count


async def test_a_stale_save_of_a_field_others_changed_is_a_conflict(api: Api) -> None:
    await _as_owner(api)
    other = api.another_browser()
    them = await _as_owner(other)
    opened = await _form(api)
    theirs = _word()
    assert (await _save(other, {"greeting": theirs}, version=opened["version"])).status_code == 200
    refused = await _save(api, {"greeting": _word()}, version=opened["version"])
    assert _code(refused) == (409, "kernel.settings_conflict"), refused.text
    body = refused.json()
    assert body["version"] == opened["version"] + 1
    assert body["conflicts"] == [
        {"field": "greeting", "yours": body["conflicts"][0]["yours"], "theirs": theirs}
    ]
    assert body["by"] == them.id
    assert body["at"]
    # Nothing was saved.
    assert (await _form(api))["values"]["greeting"] == theirs


async def test_a_version_not_saved_yet_is_refused(api: Api) -> None:
    await _as_owner(api)
    form = await _form(api)
    refused = await _save(api, {"greeting": _word()}, version=form["version"] + 5)
    assert _code(refused) == (422, "kernel.settings_version_unknown"), refused.text


async def test_an_unknown_field_or_a_refused_value_saves_nothing(api: Api) -> None:
    await _as_owner(api)
    form = await _form(api)
    unknown = await _save(api, {"colour": "red"}, version=form["version"])
    assert _code(unknown) == (422, "kernel.invalid_request"), unknown.text
    assert "colour" in unknown.json()["errors"]
    refused = await _save(api, {"count": 1000}, version=form["version"])
    assert _code(refused) == (422, "kernel.invalid_request"), refused.text
    assert "count" in refused.json()["errors"]
    assert (await _form(api))["version"] == form["version"]


async def test_a_secret_is_never_shown_and_changes_only_when_typed(api: Api) -> None:
    await _as_owner(api)
    form = await _form(api)
    secret = f"s3cret-{uuid.uuid4().hex}"
    typed = await _save(api, {"token": secret}, version=form["version"])
    assert typed.status_code == 200, typed.text
    assert typed.json()["changed"] == ["token"]
    after = await _form(api)
    changes = form["values"]["token"]["changes"] + 1
    assert after["values"]["token"] == {"kept": True, "changes": changes}
    # null keeps it.
    kept = await _save(api, {"token": None, "count": 3}, version=after["version"])
    assert kept.status_code == 200, kept.text
    assert "token" not in kept.json()["changed"]
    # "" removes it.
    now = await _form(api)
    removed = await _save(api, {"token": ""}, version=now["version"])
    assert removed.json()["changed"] == ["token"]
    assert (await _form(api))["values"]["token"] == {"kept": False, "changes": changes + 1}
    history = await api.http.get(f"{PROBE}/history")
    for response in (typed, kept, removed, history, await api.http.get(PROBE)):
        assert secret not in response.text


async def test_the_history_comes_newest_first_in_pages(api: Api) -> None:
    await _as_owner(api)
    for _ in range(3):
        form = await _form(api)
        saved = await _save(api, {"greeting": _word()}, version=form["version"])
        assert saved.status_code == 200, saved.text
    top = (await _form(api))["version"]
    first = await api.http.get(f"{PROBE}/history", params={"limit": 2})
    assert first.status_code == 200, first.text
    page = first.json()
    assert [item["number"] for item in page["items"]] == [top, top - 1]
    assert page["next_cursor"]
    rest = await api.http.get(
        f"{PROBE}/history", params={"limit": 2, "cursor": page["next_cursor"]}
    )
    assert rest.json()["items"][0]["number"] == top - 2
    bad = await api.http.get(f"{PROBE}/history", params={"cursor": "not-a-page"})
    assert _code(bad) == (422, "kernel.invalid_request"), bad.text


async def test_settings_need_their_permission(api: Api) -> None:
    staff = await _staff_holding(api, "auth.audit.read")
    for response in (
        await staff.http.get(PROBE),
        await staff.http.put(PROBE, json={"version": 0, "changes": {}}),
        await staff.http.get(f"{PROBE}/history"),
    ):
        assert _code(response) == (403, "kernel.forbidden"), response.text


# --- the sign-up mode: the settings section kernel.auth (change 19) ---------------------------


@asynccontextmanager
async def _sign_up_mode(api: Api, mode: str) -> AsyncIterator[dict[str, Any]]:
    """The sign-up mode saved as `mode` for the block, then put back as it was."""
    before = await _form(api, AUTH)
    saved = await _save(api, {"sign_up_mode": mode}, version=before["version"], path=AUTH)
    assert saved.status_code == 200, saved.text
    try:
        yield before
    finally:
        now = await _form(api, AUTH)
        back = before["values"]["sign_up_mode"]
        restored = await _save(api, {"sign_up_mode": back}, version=now["version"], path=AUTH)
        assert restored.status_code == 200, restored.text


async def _sign_up(api: Api) -> httpx.Response:
    return await api.another_browser().http.post(
        "/api/auth/sign-up",
        json={"email": f"join-{uuid.uuid4().hex[:10]}@site.test", "password": PASSWORD},
    )


async def test_the_sign_up_mode_is_a_setting_sign_up_follows(api: Api) -> None:
    await _as_owner(api)
    form = await _form(api, AUTH)
    assert set(form["values"]) == {"sign_up_mode"}
    # Until saved otherwise, the harness's SIGN_UP_MODE, open.
    assert form["values"]["sign_up_mode"] in ("open", "invite", "closed")
    async with _sign_up_mode(api, "closed"):
        assert _code(await _sign_up(api)) == (403, "auth.sign_up_closed")
    async with _sign_up_mode(api, "invite"):
        assert _code(await _sign_up(api)) == (403, "auth.invite_required")
    async with _sign_up_mode(api, "open"):
        assert (await _sign_up(api)).status_code == 202
    refused = await _save(api, {"sign_up_mode": "everyone"}, version=form["version"], path=AUTH)
    assert _code(refused) == (422, "kernel.invalid_request"), refused.text


# --- features: GET and PUT /api/kernel/admin/modules -------------------------------------------


async def _modules(api: Api) -> dict[str, dict[str, Any]]:
    response = await api.http.get(MODULES)
    assert response.status_code == 200, response.text
    return {item["id"]: item for item in response.json()["items"]}


@asynccontextmanager
async def _switched_off(api: Api, module_id: str) -> AsyncIterator[httpx.Response]:
    response = await api.http.put(f"{MODULES}/{module_id}", json={"on": False})
    try:
        yield response
    finally:
        back = await api.http.put(f"{MODULES}/{module_id}", json={"on": True})
        assert back.status_code == 200, back.text


async def test_the_modules_list_names_each_module_and_what_it_needs(api: Api) -> None:
    await _as_owner(api)
    response = await api.http.get(MODULES)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["name"] for item in items] == sorted(item["name"] for item in items)
    listed = {item["id"]: item for item in items}
    assert listed["probe"] == {
        "id": "probe",
        "name": "Probe",
        "summary": listed["probe"]["summary"],
        "category": "admin",
        "on": True,
        "switched": True,
        "requires": [],
        "required_by": ["probe-addon"],
    }
    assert listed["probe"]["summary"]
    assert listed["probe-addon"]["requires"] == ["probe"]
    assert listed["probe-addon"]["required_by"] == []


async def test_switching_a_module_off_turns_off_what_needs_it_and_back(api: Api) -> None:
    owner = await _as_owner(api)
    assert (await api.http.get(PING)).status_code == 200
    async with _switched_off(api, "probe") as off:
        assert off.status_code == 200, off.text
        listed = {item["id"]: item for item in off.json()["items"]}
        assert (listed["probe"]["on"], listed["probe"]["switched"]) == (False, False)
        # The add-on goes off with it and keeps its own switch.
        assert (listed["probe-addon"]["on"], listed["probe-addon"]["switched"]) == (False, True)
        assert _code(await api.http.get(PING)) == (404, "kernel.module_off")
        public = (await api.another_browser().http.get("/api/kernel/modules")).json()["on"]
        assert "probe" not in public
        assert "probe-addon" not in public
        logged = await _logged(api, "kernel.module", "probe")
        assert logged[0]["action"] == "kernel.module.disabled"
        assert logged[0]["actor_id"] == owner.id
    listed = await _modules(api)
    assert listed["probe"]["on"]
    assert listed["probe-addon"]["on"]
    assert (await api.http.get(PING)).status_code == 200
    assert (await _logged(api, "kernel.module", "probe"))[0]["action"] == "kernel.module.enabled"


async def test_a_module_whose_requirement_is_off_stays_off_when_switched_on(api: Api) -> None:
    await _as_owner(api)
    async with _switched_off(api, "probe"):
        on = await api.http.put(f"{MODULES}/probe-addon", json={"on": True})
        assert on.status_code == 200, on.text
        addon = {item["id"]: item for item in on.json()["items"]}["probe-addon"]
        assert (addon["on"], addon["switched"]) == (False, True)


async def test_a_switch_to_where_it_already_is_changes_nothing(api: Api) -> None:
    await _as_owner(api)
    before = len(await _logged(api, "kernel.module", "probe-addon"))
    same = await api.http.put(f"{MODULES}/probe-addon", json={"on": True})
    assert same.status_code == 200, same.text
    assert len(await _logged(api, "kernel.module", "probe-addon")) == before


async def test_an_unknown_module_is_404(api: Api) -> None:
    await _as_owner(api)
    response = await api.http.put(f"{MODULES}/nothing-here", json={"on": False})
    assert _code(response) == (404, "kernel.module_unknown"), response.text


async def test_switching_modules_needs_its_permission(api: Api) -> None:
    staff = await _staff_holding(api, "kernel.settings.manage")
    for response in (
        await staff.http.get(MODULES),
        await staff.http.put(f"{MODULES}/probe", json={"on": False}),
    ):
        assert _code(response) == (403, "kernel.forbidden"), response.text
    assert (await staff.http.get(PING)).status_code == 200


# --- System: GET /api/kernel/admin/system, the failed jobs, retry and discard -----------------


async def _job(api: Api, name: str, **fields: Any) -> str:
    response = await api.http.post("/api/_test/jobs", json={"name": name} | fields)
    assert response.status_code == 201, response.text
    ident: str = response.json()["id"]
    return ident


async def _dead(api: Api, **params: Any) -> dict[str, Any]:
    response = await api.http.get(DEAD, params=params)
    assert response.status_code == 200, response.text
    page: dict[str, Any] = response.json()
    return page


async def _system(api: Api) -> dict[str, Any]:
    response = await api.http.get(SYSTEM)
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


@asynccontextmanager
async def _failed(api: Api, count: int = 1, **fields: Any) -> AsyncIterator[list[str]]:
    """`count` probe jobs that failed for good, discarded at the end. What
    else is due runs first, so these are the newest failures."""
    await api.run_jobs()
    made = [await _job(api, "probe.fail", **fields) for _ in range(count)]
    await api.run_jobs()
    try:
        yield made
    finally:
        for ident in made:
            await api.http.delete(f"{JOBS}/{ident}")


async def test_system_reads_the_queue_the_services_and_the_build(api: Api) -> None:
    await _as_owner(api)
    found = await _system(api)
    assert set(found) == {"jobs", "services", "version", "modules"}
    assert set(found["jobs"]) == {"queued", "running", "dead", "worker"}
    assert all(isinstance(found["jobs"][key], int) for key in ("queued", "running", "dead"))
    assert found["jobs"]["worker"] in ("ok", "behind")
    assert found["services"]["email"] in ("smtp", "resend", "log")
    assert set(found["services"]["storage"]) == {"configured", "public"}
    assert isinstance(found["version"], str)
    assert found["version"]
    assert found["modules"]["installed"] >= 2
    assert 0 <= found["modules"]["on"] <= found["modules"]["installed"]


async def test_the_worker_is_behind_while_a_job_it_would_take_is_overdue(api: Api) -> None:
    await _as_owner(api)
    await api.run_jobs()
    assert (await _system(api))["jobs"]["worker"] == "ok"
    await _job(api, "probe.ok")
    await api.advance(3 * MINUTE)
    behind = await _system(api)
    assert behind["jobs"]["worker"] == "behind"
    assert behind["jobs"]["queued"] >= 1
    await api.run_jobs()
    assert (await _system(api))["jobs"]["worker"] == "ok"


async def test_a_switched_off_module_s_waiting_jobs_never_read_as_behind(api: Api) -> None:
    await _as_owner(api)
    await api.run_jobs()
    async with _switched_off(api, "probe-addon"):
        await _job(api, "probe-addon.ok")
        await api.advance(3 * MINUTE)
        await api.run_jobs()  # runs every other job; the add-on's waits
        found = await _system(api)
        assert found["jobs"]["worker"] == "ok"
        assert found["jobs"]["queued"] >= 1
    await api.run_jobs()


async def test_a_failed_job_is_listed_without_its_payload_and_retried(api: Api) -> None:
    owner = await _as_owner(api)
    async with _failed(api) as (ident,):
        page = await _dead(api)
        item = next(item for item in page["items"] if item["id"] == ident)
        assert item == {
            "id": ident,
            "name": "probe.fail",
            "module": "probe",
            "tries": 1,
            "last_error": "ProbeFailure",
            "failed_at": item["failed_at"],
            "retryable": True,
        }
        assert (await _system(api))["jobs"]["dead"] >= 1
        retried = await api.http.post(f"{JOBS}/{ident}/retry")
        assert retried.status_code == 200, retried.text
        # Queued again as a job of its own, so no claim of the old one can
        # ever match the new run (CodeRabbit on #87).
        anew = retried.json()["id"]
        assert retried.json() == {"state": "queued", "id": anew}
        assert anew != ident
        assert ident not in [item["id"] for item in (await _dead(api))["items"]]
        logged = await _logged(api, "kernel.job", ident)
        assert logged[0]["action"] == "kernel.job.retried"
        assert logged[0]["actor_id"] == owner.id
        assert logged[0]["details"]["queued_as"] == anew
        # It has all its tries: it ran once more and failed again.
        await api.run_jobs()
        again = next(item for item in (await _dead(api))["items"] if item["id"] == anew)
        assert again["tries"] == 1
        await api.http.delete(f"{JOBS}/{anew}")


async def test_a_failed_job_can_be_discarded(api: Api) -> None:
    owner = await _as_owner(api)
    async with _failed(api) as (ident,):
        gone = await api.http.delete(f"{JOBS}/{ident}")
        assert gone.status_code == 204, gone.text
        assert ident not in [item["id"] for item in (await _dead(api))["items"]]
        assert _code(await api.http.delete(f"{JOBS}/{ident}")) == (404, "kernel.job_not_found")
        assert _code(await api.http.post(f"{JOBS}/{ident}/retry")) == (404, "kernel.job_not_found")
        logged = await _logged(api, "kernel.job", ident)
        assert logged[0]["action"] == "kernel.job.discarded"
        assert logged[0]["actor_id"] == owner.id


async def test_a_job_that_hasn_t_failed_is_left_alone(api: Api) -> None:
    await _as_owner(api)
    waiting = await _job(api, "probe.ok")
    for response in (
        await api.http.post(f"{JOBS}/{waiting}/retry"),
        await api.http.delete(f"{JOBS}/{waiting}"),
    ):
        assert _code(response) == (409, "kernel.job_not_dead"), response.text
    await api.run_jobs()


async def test_a_sealed_failed_job_can_only_be_discarded(api: Api) -> None:
    await _as_owner(api)
    async with _failed(api, sealed=True) as (ident,):
        item = next(item for item in (await _dead(api))["items"] if item["id"] == ident)
        assert item["retryable"] is False
        refused = await api.http.post(f"{JOBS}/{ident}/retry")
        assert _code(refused) == (409, "kernel.job_not_retryable"), refused.text


async def test_a_retry_while_another_run_of_it_waits_is_refused(api: Api) -> None:
    await _as_owner(api)
    key = uuid.uuid4().hex
    async with _failed(api, key=key) as (ident,):
        waiting = await _job(api, "probe.fail", key=key)
        try:
            refused = await api.http.post(f"{JOBS}/{ident}/retry")
            assert _code(refused) == (409, "kernel.job_not_retryable"), refused.text
        finally:
            await api.run_jobs()
            await api.http.delete(f"{JOBS}/{waiting}")


async def test_the_failed_jobs_come_newest_first_in_pages(api: Api) -> None:
    await _as_owner(api)
    async with _failed(api, 3) as made:
        seen: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(200):  # every page, two at a time
            page = await _dead(api, limit=2, **({"cursor": cursor} if cursor else {}))
            assert len(page["items"]) <= 2
            seen += page["items"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        ids = [item["id"] for item in seen]
        assert len(ids) == len(set(ids))
        assert set(made) <= set(ids)
        assert [item["failed_at"] for item in seen] == sorted(
            (item["failed_at"] for item in seen), reverse=True
        )
    bad = await api.http.get(DEAD, params={"cursor": "not-a-page"})
    assert _code(bad) == (422, "kernel.invalid_request"), bad.text


async def test_system_is_read_with_settings_and_jobs_are_acted_on_with_their_own(
    api: Api,
) -> None:
    reader = await _staff_holding(api, "kernel.settings.manage")
    async with _failed(api) as (ident,):
        assert (await reader.http.get(SYSTEM)).status_code == 200
        assert (await reader.http.get(DEAD)).status_code == 200
        for response in (
            await reader.http.post(f"{JOBS}/{ident}/retry"),
            await reader.http.delete(f"{JOBS}/{ident}"),
        ):
            assert _code(response) == (403, "kernel.forbidden"), response.text
        actor = await _staff_holding(api, "kernel.jobs.manage")
        for response in (await actor.http.get(SYSTEM), await actor.http.get(DEAD)):
            assert _code(response) == (403, "kernel.forbidden"), response.text
        assert (await actor.http.delete(f"{JOBS}/{ident}")).status_code == 204
