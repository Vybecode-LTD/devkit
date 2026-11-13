"""The auth contract suite: one or more tests per line of SPEC.md 14.13, and
for the rules decision 0013 added to section 14.

HTTP only (docs/contracts/auth-api.md); nothing here imports the kernel.
Written before auth exists, as KICKOFF.md K2 step 1 asks. A test whose code
hasn't landed carries `@not_built`: it must fail with `NotBuilt` (a route the
contract names doesn't exist yet) and nothing else, and `strict` turns a pass
into a failure until the mark is removed. Every expiry test has a positive
control, so a server that refuses everything doesn't pass.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Awaitable, Callable

import httpx
import pyotp
import pytest

from .conftest import (
    NEW_PASSWORD,
    OTHER_PASSWORD,
    PASSWORD,
    UNCHECKED,
    Api,
    NotBuilt,
    code_in,
    not_built,
    query_param,
    token_in,
    wrong_totp,
)

UNKNOWN = "nobody-here@site.test"
ZERO_ID = "00000000-0000-0000-0000-000000000000"
MINUTE = 60
DAY = 24 * 3600


def _shape(response: httpx.Response) -> tuple[int, object]:
    body = response.json() if response.content else None
    if isinstance(body, dict):
        body = {key: value for key, value in body.items() if key != "instance"}
    return response.status_code, body


# 1. Sign-in, sign-up and reset answer the same for a known and an unknown email


@not_built
async def test_sign_in_answers_the_same_for_known_and_unknown(api: Api) -> None:
    user = await api.make_user()
    known = await api.http.post(
        "/api/auth/sign-in", json={"email": user.email, "password": "a wrong password 1"}
    )
    unknown = await api.http.post(
        "/api/auth/sign-in", json={"email": UNKNOWN, "password": "a wrong password 1"}
    )
    assert _shape(known) == _shape(unknown)
    assert (known.status_code, known.json()["code"]) == (401, "auth.invalid_credentials")


@not_built
async def test_sign_up_answers_the_same_and_mails_a_notice_to_a_known_address(api: Api) -> None:
    user = await api.make_user()
    new = f"new-{user.id[:8]}@site.test"
    known = await api.http.post(
        "/api/auth/sign-up", json={"email": user.email, "password": PASSWORD}
    )
    unknown = await api.http.post("/api/auth/sign-up", json={"email": new, "password": PASSWORD})
    assert _shape(known) == _shape(unknown) == (202, {"status": "check_email"})
    assert "/auth/verify?token=" not in (await api.last_mail(user.email))["text"]
    assert token_in((await api.last_mail(new))["text"], "/auth/verify")


@not_built
async def test_reset_answers_the_same_for_known_and_unknown(api: Api) -> None:
    user = await api.make_user()
    known = await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    unknown = await api.http.post("/api/auth/password/reset-request", json={"email": UNKNOWN})
    assert _shape(known) == _shape(unknown) == (202, {"status": "check_email"})


@not_built
async def test_codes_answer_the_same_and_staff_are_sent_nothing(api: Api) -> None:
    member = await api.make_user()
    staff = await api.make_user(roles=["admin"], totp=True)
    answers = [
        _shape(await api.http.post("/api/auth/code", json={"email": email}))
        for email in (member.email, UNKNOWN, staff.email)
    ]
    assert answers == [(202, {"status": "check_email"})] * 3
    assert len(await api.mail(member.email)) == 1
    assert await api.mail(staff.email) == []


@not_built
async def test_a_missing_account_reaches_its_failure_limit_the_same_way(api: Api) -> None:
    user = await api.make_user()
    real = [await api.another_browser().sign_in(user, "a wrong password 1") for _ in range(6)]
    await api.http.post("/api/_test/reset")
    ghost = [
        await api.another_browser().http.post(
            "/api/auth/sign-in", json={"email": UNKNOWN, "password": "a wrong password 1"}
        )
        for _ in range(6)
    ]
    assert [r.status_code for r in real] == [r.status_code for r in ghost] == [401] * 5 + [429]
    assert _shape(real[-1])[1].keys() == _shape(ghost[-1])[1].keys()  # type: ignore[union-attr]


async def _median(timed: Callable[[], Awaitable[object]], runs: int) -> float:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        await timed()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


@not_built
@pytest.mark.parametrize("route", ["sign-in", "sign-up", "password/reset-request"])
async def test_a_missing_account_takes_similar_time(api: Api, route: str) -> None:
    """Interleaved, against a baseline that hashes nothing: an unknown email
    is answered in neither half nor twice the time of a known one."""
    user = await api.make_user()
    password = {"sign-in": "a wrong password 1", "sign-up": PASSWORD}.get(route)

    def body(email: str) -> dict[str, str]:
        return {"email": email} | ({"password": password} if password else {})

    known, unknown, baseline = [], [], []
    for _ in range(7):
        await api.http.post("/api/_test/reset")  # counts start over: no 429s skew it
        baseline.append(await _median(api.session, 1))
        known.append(
            await _median(lambda: api.http.post(f"/api/auth/{route}", json=body(user.email)), 1)
        )
        unknown.append(
            await _median(lambda: api.http.post(f"/api/auth/{route}", json=body(UNKNOWN)), 1)
        )
    base = statistics.median(baseline)
    known_cost = max(statistics.median(known) - base, 1e-4)
    unknown_cost = max(statistics.median(unknown) - base, 1e-4)
    assert 0.5 <= unknown_cost / known_cost <= 2.0, (known_cost, unknown_cost)


# 2. A reset, code or link token works once, and never after it expires


@not_built
async def test_a_reset_token_works_once(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/reset")
    first = await api.http.post(
        "/api/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}
    )
    again = await api.http.post(
        "/api/auth/password/reset", json={"token": token, "password": OTHER_PASSWORD}
    )
    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (400, "auth.token_invalid")


@not_built
async def test_a_reset_token_lasts_30_minutes(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    early = token_in((await api.last_mail(user.email))["text"], "/auth/reset")
    await api.advance(29 * MINUTE)
    still = await api.http.post(
        "/api/auth/password/reset", json={"token": early, "password": NEW_PASSWORD}
    )
    assert still.status_code == 200  # the control: alive at 29 minutes

    await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    late = token_in((await api.last_mail(user.email))["text"], "/auth/reset")
    assert late != early
    await api.advance(31 * MINUTE)
    gone = await api.http.post(
        "/api/auth/password/reset", json={"token": late, "password": OTHER_PASSWORD}
    )
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")


@not_built
async def test_a_sign_in_code_works_once(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    code = code_in((await api.last_mail(user.email))["text"])
    first = await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": code})
    again = await api.another_browser().http.post(
        "/api/auth/code/verify", json={"email": user.email, "code": code}
    )
    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (401, "auth.invalid_code")


@not_built
async def test_a_sign_in_code_lasts_10_minutes(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    early = code_in((await api.last_mail(user.email))["text"])
    await api.advance(9 * MINUTE)
    still = await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": early})
    assert still.status_code == 200  # the control: alive at 9 minutes

    other = api.another_browser()
    await other.http.post("/api/auth/code", json={"email": user.email})  # past the resend wait
    assert len(await api.mail(user.email)) == 2
    late = code_in((await api.last_mail(user.email))["text"])
    await api.advance(11 * MINUTE)
    gone = await other.http.post("/api/auth/code/verify", json={"email": user.email, "code": late})
    assert (gone.status_code, gone.json()["code"]) == (401, "auth.invalid_code")


@not_built
async def test_five_wrong_tries_end_a_code(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    code = code_in((await api.last_mail(user.email))["text"])
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(5):
        await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": wrong})
    ended = await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": code})
    assert (ended.status_code, ended.json()["code"]) == (401, "auth.invalid_code")


@not_built
async def test_a_resend_within_60_seconds_sends_nothing(api: Api) -> None:
    user = await api.make_user()
    first = await api.http.post("/api/auth/code", json={"email": user.email})
    second = await api.http.post("/api/auth/code", json={"email": user.email})
    assert _shape(first) == _shape(second) == (202, {"status": "check_email"})
    assert len(await api.mail(user.email)) == 1
    await api.advance(61)
    await api.http.post("/api/auth/code", json={"email": user.email})
    assert len(await api.mail(user.email)) == 2


@not_built
async def test_a_magic_link_works_once(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/link")
    first = await api.http.post("/api/auth/link/confirm", json={"token": token})
    again = await api.another_browser().http.post("/api/auth/link/confirm", json={"token": token})
    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (401, "auth.invalid_link")


@not_built
async def test_a_magic_link_lasts_10_minutes(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    early = token_in((await api.last_mail(user.email))["text"], "/auth/link")
    await api.advance(9 * MINUTE)
    assert (await api.http.post("/api/auth/link/confirm", json={"token": early})).status_code == 200

    other = api.another_browser()
    await other.http.post("/api/auth/code", json={"email": user.email})
    late = token_in((await api.last_mail(user.email))["text"], "/auth/link")
    await api.advance(11 * MINUTE)
    gone = await other.http.post("/api/auth/link/confirm", json={"token": late})
    assert (gone.status_code, gone.json()["code"]) == (401, "auth.invalid_link")


# 3. Opening a magic link with GET alone signs nobody in


@not_built
async def test_a_get_on_a_magic_link_signs_nobody_in(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/link")
    scanner = api.another_browser()
    for path in (
        f"/auth/link?token={token}",
        f"/api/auth/link?token={token}",
        f"/api/auth/link/confirm?token={token}",
    ):
        response = await scanner.http.get(path, extensions=UNCHECKED)
        assert "__Host-dk_session" not in response.headers.get("set-cookie", "")
    assert (await scanner.session()).status_code == 401
    # The scanner used nothing up: the person's own click still works.
    assert (await api.http.post("/api/auth/link/confirm", json={"token": token})).status_code == 200


# 4. A TOTP code can't be replayed within its step


@not_built
async def test_a_totp_code_cant_be_replayed(api: Api) -> None:
    user = await api.make_user(totp=True)
    assert user.totp_secret
    code = pyotp.TOTP(user.totp_secret).now()
    for attempt in range(2):
        browser = api if attempt == 0 else api.another_browser()
        first = (await browser.sign_in(user)).json()
        assert first["status"] == "second_factor"
        response = await browser.http.post(
            "/api/auth/sign-in/second-factor", json={"challenge": first["challenge"], "totp": code}
        )
        if attempt == 0:
            assert response.status_code == 200
        else:
            assert (response.status_code, response.json()["code"]) == (
                401,
                "auth.invalid_second_factor",
            )


# 5. Staff without a second factor can't reach any admin route


async def _admin_routes(api: Api) -> list[tuple[str, str]]:
    listed = (await api.test_routes()).get("admin", [])
    routes = [tuple(entry.split(" ", 1)) for entry in listed]
    if ("GET", "/api/auth/admin/users") not in routes:
        raise NotBuilt("the auth admin routes aren't built yet")
    assert ("PUT", "/api/auth/admin/users/{id}/roles") in routes
    return [(method, path) for method, path in routes]  # type: ignore[misc]


def _filled(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", ZERO_ID, path)


@not_built
async def test_staff_without_a_second_factor_reach_no_admin_route(api: Api) -> None:
    admin = await api.make_user(roles=["admin"])
    await api.signed_in_as(admin)
    for method, path in await _admin_routes(api):
        response = await api.http.request(method, _filled(path), json={}, extensions=UNCHECKED)
        assert (response.status_code, response.json()["code"]) == (
            403,
            "auth.second_factor_required",
        ), f"{method} {path}"


@not_built
async def test_members_and_strangers_reach_no_admin_route(api: Api) -> None:
    routes = await _admin_routes(api)
    for method, path in routes:
        response = await api.http.request(method, _filled(path), json={}, extensions=UNCHECKED)
        assert (response.status_code, response.json()["code"]) == (401, "kernel.not_signed_in")
    await api.signed_in_as(await api.make_user())
    for method, path in routes:
        response = await api.http.request(method, _filled(path), json={}, extensions=UNCHECKED)
        assert (response.status_code, response.json()["code"]) == (403, "kernel.forbidden")


@not_built
async def test_staff_with_a_second_factor_reach_the_admin(api: Api) -> None:
    admin = await api.make_user(roles=["admin"], totp=True)
    await api.signed_in_as(admin)
    assert (await api.http.get("/api/auth/admin/users")).status_code == 200


@not_built
async def test_an_unconfirmed_totp_is_no_second_factor(api: Api) -> None:
    admin = await api.make_user(roles=["admin"])
    await api.signed_in_as(admin)
    assert (await api.http.post("/api/auth/totp/setup")).status_code == 200  # never confirmed
    refused = await api.http.get("/api/auth/admin/users")
    assert (refused.status_code, refused.json()["code"]) == (403, "auth.second_factor_required")


# 6. Every action listed under step-up (14.4) demands it

STEP_UP = [
    (
        "POST",
        "/api/auth/password/change",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    ),
    ("POST", "/api/auth/email/change", {"email": "new-address@site.test"}),
    ("POST", "/api/auth/totp/setup", None),
    ("DELETE", "/api/auth/totp", None),
    ("POST", "/api/auth/recovery-codes", None),
    ("POST", "/api/auth/passkeys/register/start", {"name": "Laptop"}),
    ("DELETE", f"/api/auth/passkeys/{ZERO_ID}", None),
    ("POST", "/api/auth/api-keys", {"name": "CI", "scopes": []}),
    ("POST", "/api/auth/account/delete", None),
]
STEP_UP_IDS = [f"{m} {p}" for m, p, _ in STEP_UP]


@not_built
@pytest.mark.parametrize(("method", "path", "body"), STEP_UP, ids=STEP_UP_IDS)
async def test_step_up_actions_demand_a_recent_sign_in(
    api: Api, method: str, path: str, body: dict[str, str] | None
) -> None:
    await api.signed_in_as(await api.make_user(totp=True))
    await api.advance(11 * MINUTE)
    response = await api.http.request(method, path, json=body)
    assert (response.status_code, response.json()["code"]) == (403, "auth.step_up_required")


@not_built
@pytest.mark.parametrize(("method", "path", "body"), STEP_UP, ids=STEP_UP_IDS)
async def test_step_up_actions_go_through_after_a_recent_sign_in(
    api: Api, method: str, path: str, body: dict[str, str] | None
) -> None:
    """The control: within 10 minutes of signing in, none is refused for it."""
    await api.signed_in_as(await api.make_user(totp=True))
    await api.advance(9 * MINUTE)
    response = await api.http.request(method, path, json=body)
    code = response.json().get("code") if response.content else None
    assert code != "auth.step_up_required", response.text


@not_built
async def test_every_step_up_action_is_marked(api: Api) -> None:
    listed = set((await api.test_routes()).get("step_up", []))
    if not listed:
        raise NotBuilt("no step-up routes yet")
    expected = {f"{m} {p}".replace(ZERO_ID, "{id}") for m, p, _ in STEP_UP}
    expected.add("PUT /api/auth/admin/users/{id}/roles")
    assert expected <= listed


@not_built
async def test_step_up_counts_from_signing_in_not_from_activity(api: Api) -> None:
    await api.signed_in_as(await api.make_user(totp=True))
    for _ in range(2):
        await api.advance(5 * MINUTE)
        assert (await api.session()).status_code == 200  # busy all along
    await api.advance(1 * MINUTE)
    response = await api.http.post("/api/auth/recovery-codes")
    assert (response.status_code, response.json()["code"]) == (403, "auth.step_up_required")


@not_built
async def test_changing_roles_demands_a_recent_sign_in(api: Api) -> None:
    owner = await api.make_user(roles=["owner"], totp=True)
    member = await api.make_user()
    await api.signed_in_as(owner)
    await api.advance(11 * MINUTE)
    response = await api.http.put(
        f"/api/auth/admin/users/{member.id}/roles", json={"roles": ["editor"]}
    )
    assert (response.status_code, response.json()["code"]) == (403, "auth.step_up_required")


@not_built
async def test_stepping_up_lets_the_action_through_with_a_new_token(api: Api) -> None:
    await api.signed_in_as(await api.make_user(totp=True))
    await api.advance(11 * MINUTE)
    before = api.session_cookie
    stepped = await api.http.post("/api/auth/step-up", json={"password": PASSWORD})
    assert stepped.status_code == 200
    assert api.session_cookie not in {None, before}
    codes = await api.http.post("/api/auth/recovery-codes")
    assert codes.status_code == 200
    assert len(codes.json()["recovery_codes"]) == 10


@not_built
async def test_five_failed_step_ups_end_the_session(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    await api.advance(11 * MINUTE)
    for _ in range(5):
        await api.http.post("/api/auth/step-up", json={"password": "a wrong password 1"})
    assert (await api.session()).status_code == 401


# 7. A password change ends every other session (and a reset ends them all)


@not_built
async def test_a_password_change_ends_every_other_session(api: Api) -> None:
    user = await api.make_user()
    other = api.another_browser()
    await api.signed_in_as(user)
    await other.signed_in_as(user)
    response = await api.http.post(
        "/api/auth/password/change",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    assert (await api.session()).status_code == 200
    assert (await other.session()).status_code == 401


@not_built
async def test_a_reset_ends_every_session(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    stranger = api.another_browser()
    await stranger.http.post("/api/auth/password/reset-request", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/reset")
    reset = await stranger.http.post(
        "/api/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}
    )
    assert reset.status_code == 200
    assert (await api.session()).status_code == 401


# 8. A provider identity with an unverified email never links automatically


async def _oauth(
    browser: Api, subject: str, email: str, verified: bool, next_: str = "/"
) -> httpx.Response:
    grant = await browser.http.post(
        "/api/_test/oauth/grant",
        json={"provider": "test", "subject": subject, "email": email, "email_verified": verified},
    )
    assert grant.status_code == 200, grant.text
    start = await browser.http.get("/api/auth/oauth/test/start", params={"next": next_})
    state = query_param(start.headers["location"], "state")
    return await browser.http.get(
        "/api/auth/oauth/test/callback", params={"code": grant.json()["code"], "state": state}
    )


@not_built
async def test_an_unverified_provider_email_never_links(api: Api) -> None:
    user = await api.make_user()
    callback = await _oauth(api, "sub-1", user.email, verified=False, next_="/account")
    assert callback.status_code == 302
    assert callback.headers["location"].startswith("/sign-in?link=test")
    assert (await api.session()).status_code == 401


@not_built
async def test_a_verified_provider_email_never_links_to_an_unverified_account(api: Api) -> None:
    user = await api.make_user(verified=False)
    callback = await _oauth(api, "sub-4", user.email, verified=True, next_="/account")
    assert callback.status_code == 302
    assert callback.headers["location"].startswith("/sign-in?link=test")
    assert (await api.session()).status_code == 401


@not_built
async def test_a_verified_provider_email_links_to_a_verified_account(api: Api) -> None:
    user = await api.make_user()
    callback = await _oauth(api, "sub-2", user.email, verified=True, next_="/account")
    assert (callback.status_code, callback.headers["location"]) == (302, "/account")
    assert (await api.session()).json()["user"]["id"] == user.id


@not_built
@pytest.mark.parametrize("path", ["/api/auth/totp/setup", "/api/auth/passkeys/register/start"])
async def test_an_unverified_account_adds_no_second_factor(api: Api, path: str) -> None:
    """No pre-claiming an address (14.3): whoever signed up with someone else's
    email can't leave a factor behind for the real owner to inherit."""
    await api.signed_in_as(await api.make_user(verified=False))
    response = await api.http.post(path, json={"name": "Laptop"})
    assert (response.status_code, response.json()["code"]) == (403, "auth.email_unverified")


# 9. An OAuth callback with a wrong or missing state is refused


@not_built
@pytest.mark.parametrize("state", [None, "", "not-the-state"])
async def test_a_callback_with_a_bad_state_is_refused(api: Api, state: str | None) -> None:
    grant = await api.http.post(
        "/api/_test/oauth/grant",
        json={
            "provider": "test",
            "subject": "sub-3",
            "email": "x@site.test",
            "email_verified": True,
        },
    )
    await api.http.get("/api/auth/oauth/test/start", params={"next": "/"})
    params = {"code": grant.json()["code"]}
    if state is not None:
        params["state"] = state
    response = await api.http.get("/api/auth/oauth/test/callback", params=params)
    assert (response.status_code, response.json()["code"]) == (400, "auth.oauth_state_invalid")
    assert (await api.session()).status_code == 401


@not_built
async def test_another_browsers_state_is_refused(api: Api) -> None:
    victim, attacker = api, api.another_browser()
    start = await attacker.http.get("/api/auth/oauth/test/start", params={"next": "/"})
    state = query_param(start.headers["location"], "state")
    grant = await attacker.http.post(
        "/api/_test/oauth/grant",
        json={
            "provider": "test",
            "subject": "sub-5",
            "email": "y@site.test",
            "email_verified": True,
        },
    )
    response = await victim.http.get(
        "/api/auth/oauth/test/callback", params={"code": grant.json()["code"], "state": state}
    )
    assert (response.status_code, response.json()["code"]) == (400, "auth.oauth_state_invalid")


@not_built
async def test_a_state_works_once(api: Api) -> None:
    user = await api.make_user()
    grant = await api.http.post(
        "/api/_test/oauth/grant",
        json={"provider": "test", "subject": "sub-6", "email": user.email, "email_verified": True},
    )
    start = await api.http.get("/api/auth/oauth/test/start", params={"next": "/"})
    state = query_param(start.headers["location"], "state")
    first = await api.http.get(
        "/api/auth/oauth/test/callback", params={"code": grant.json()["code"], "state": state}
    )
    assert first.status_code == 302
    again_grant = await api.http.post(
        "/api/_test/oauth/grant",
        json={"provider": "test", "subject": "sub-6", "email": user.email, "email_verified": True},
    )
    again = await api.http.get(
        "/api/auth/oauth/test/callback", params={"code": again_grant.json()["code"], "state": state}
    )
    assert (again.status_code, again.json()["code"]) == (400, "auth.oauth_state_invalid")


@not_built
@pytest.mark.parametrize("next_", ["//evil.test/x", "https://evil.test/x", "javascript:alert(1)"])
async def test_next_stays_on_this_site(api: Api, next_: str) -> None:
    user = await api.make_user()
    callback = await _oauth(api, f"sub-7-{len(next_)}", user.email, verified=True, next_=next_)
    assert (callback.status_code, callback.headers["location"]) == (302, "/")


# 10. A state-changing request from another origin is refused


@not_built
@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.test"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
async def test_a_write_from_another_origin_is_refused(api: Api, headers: dict[str, str]) -> None:
    await api.signed_in_as(await api.make_user())
    forged = {"Origin": api.http.headers["Origin"], "Sec-Fetch-Site": "same-origin", **headers}
    response = await api.http.post("/api/auth/sign-out", headers=forged)
    assert (response.status_code, response.json()["code"]) == (403, "kernel.cross_site_write")
    assert (await api.session()).status_code == 200


# 11. The session token changes at sign-in and on a role change


@not_built
async def test_the_token_changes_at_sign_in(api: Api) -> None:
    user = await api.make_user()
    api.plant_cookie("__Host-dk_session", "planted-by-an-attacker")
    await api.signed_in_as(user)
    assert api.session_cookie not in {None, "planted-by-an-attacker"}
    first = api.session_cookie
    await api.http.post("/api/auth/sign-out")
    await api.signed_in_as(user)
    assert api.session_cookie != first


@not_built
async def test_the_token_changes_on_a_role_change(api: Api) -> None:
    owner = await api.make_user(roles=["owner"], totp=True)
    member = await api.make_user()
    staff_side, member_side = api, api.another_browser()
    await staff_side.signed_in_as(owner)
    await member_side.signed_in_as(member)
    before = member_side.session_cookie
    assert before
    response = await staff_side.http.put(
        f"/api/auth/admin/users/{member.id}/roles", json={"roles": ["editor"]}
    )
    assert response.status_code == 200
    assert (await member_side.session()).status_code == 200
    assert member_side.session_cookie not in {None, before}
    stale = api.another_browser()
    stale.plant_cookie("__Host-dk_session", before)
    assert (await stale.session()).status_code == 401


# Who can grant what (14.1, decision 0013)


@not_built
async def test_an_admin_cant_grant_owner_or_suspend_one(api: Api) -> None:
    owner = await api.make_user(roles=["owner"], totp=True)
    admin = await api.make_user(roles=["admin"], totp=True)
    await api.signed_in_as(admin)
    grant = await api.http.put(f"/api/auth/admin/users/{admin.id}/roles", json={"roles": ["owner"]})
    assert (grant.status_code, grant.json()["code"]) == (403, "auth.role_not_yours")
    suspend = await api.http.post(f"/api/auth/admin/users/{owner.id}/suspend")
    assert (suspend.status_code, suspend.json()["code"]) == (403, "auth.role_not_yours")


@not_built
async def test_the_last_owner_stays(api: Api) -> None:
    owner = await api.make_user(roles=["owner"], totp=True)
    await api.signed_in_as(owner)
    demote = await api.http.put(
        f"/api/auth/admin/users/{owner.id}/roles", json={"roles": ["admin"]}
    )
    assert (demote.status_code, demote.json()["code"]) == (409, "auth.last_owner")


# 12. Each rate limit in 14.6 triggers at its threshold


@not_built
async def test_password_sign_in_10_per_ip_per_minute(api: Api) -> None:
    codes = [
        (
            await api.http.post(
                "/api/auth/sign-in",
                json={"email": f"n{i}@site.test", "password": "a wrong password 1"},
            )
        ).status_code
        for i in range(11)
    ]
    assert codes == [401] * 10 + [429]


@not_built
async def test_five_failures_on_one_account_slow_it_down(api: Api) -> None:
    user = await api.make_user()
    browsers = [api.another_browser() for _ in range(6)]
    codes = [(await b.sign_in(user, "a wrong password 1")).status_code for b in browsers]
    assert codes == [401] * 5 + [429]
    refused = await api.sign_in(user)  # the right password, on a browser that never signed in
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) >= 1


async def _over_the_limit(api: Api, email: str) -> None:
    for _ in range(5):
        await api.another_browser().http.post(
            "/api/auth/sign-in", json={"email": email, "password": "a wrong password 1"}
        )


@not_built
async def test_a_known_browser_still_signs_in_over_the_limit(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.http.post("/api/auth/sign-out")
    await _over_the_limit(api, user.email)
    assert (await api.another_browser().sign_in(user)).status_code == 429
    assert (await api.sign_in(user)).status_code == 200


@not_built
async def test_a_known_browser_with_a_wrong_password_is_still_refused(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.http.post("/api/auth/sign-out")
    await _over_the_limit(api, user.email)
    assert (await api.sign_in(user, "a wrong password 1")).status_code in {401, 429}
    assert (await api.sign_in(user)).status_code == 200


@not_built
async def test_a_device_cookie_helps_only_its_own_account(api: Api) -> None:
    mine, theirs = await api.make_user(), await api.make_user()
    await api.signed_in_as(mine)
    await api.http.post("/api/auth/sign-out")
    await _over_the_limit(api, theirs.email)
    assert (await api.sign_in(theirs)).status_code == 429
    forged = api.another_browser()
    forged.plant_cookie("__Host-dk_device", "forged")
    assert (await forged.sign_in(theirs)).status_code == 429


@not_built
async def test_the_device_cookie_outlives_sign_out_and_is_no_session(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    await api.http.post("/api/auth/sign-out")
    device = api.http.cookies.get("__Host-dk_device")
    assert device
    assert device != api.session_cookie
    assert (await api.session()).status_code == 401


@not_built
async def test_codes_3_per_email_per_15_minutes(api: Api) -> None:
    user = await api.make_user()
    for _ in range(3):
        await api.http.post("/api/auth/code", json={"email": user.email})
        await api.advance(61)  # past the resend wait
    assert len(await api.mail(user.email)) == 3
    fourth = await api.http.post("/api/auth/code", json={"email": user.email})
    assert fourth.status_code == 429


@not_built
async def test_code_limits_ignore_the_case_of_an_address(api: Api) -> None:
    user = await api.make_user()
    for variant in (user.email, user.email.upper(), user.email.title()):
        await api.http.post("/api/auth/code", json={"email": variant})
        await api.advance(61)
    fourth = await api.http.post("/api/auth/code", json={"email": user.email.swapcase()})
    assert fourth.status_code == 429


@not_built
async def test_codes_10_per_ip_per_hour(api: Api) -> None:
    codes = [
        (await api.http.post("/api/auth/code", json={"email": f"c{i}@site.test"})).status_code
        for i in range(11)
    ]
    assert codes == [202] * 10 + [429]


@not_built
async def test_resets_are_limited_as_codes_are(api: Api) -> None:
    user = await api.make_user()
    for _ in range(3):
        await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
        await api.advance(61)
    fourth = await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    assert fourth.status_code == 429
    await api.http.post("/api/_test/reset")
    by_ip = [
        (
            await api.http.post(
                "/api/auth/password/reset-request", json={"email": f"r{i}@site.test"}
            )
        ).status_code
        for i in range(11)
    ]
    assert by_ip == [202] * 10 + [429]


@not_built
async def test_sign_up_5_per_ip_per_hour(api: Api) -> None:
    codes = [
        (
            await api.http.post(
                "/api/auth/sign-up", json={"email": f"s{i}@site.test", "password": PASSWORD}
            )
        ).status_code
        for i in range(6)
    ]
    assert codes == [202] * 5 + [429]


@not_built
async def test_a_breached_password_is_refused_with_its_reason(api: Api) -> None:
    await api.mark_breached(OTHER_PASSWORD)
    response = await api.http.post(
        "/api/auth/sign-up", json={"email": "breached@site.test", "password": OTHER_PASSWORD}
    )
    assert (response.status_code, response.json()["code"]) == (422, "auth.password_rejected")
    assert "breach" in response.json()["detail"]


@not_built
async def test_five_second_factor_failures_end_the_sign_in(api: Api) -> None:
    user = await api.make_user(totp=True)
    assert user.totp_secret
    challenge = (await api.sign_in(user)).json()["challenge"]
    wrong = wrong_totp(user.totp_secret)
    for _ in range(5):
        response = await api.http.post(
            "/api/auth/sign-in/second-factor", json={"challenge": challenge, "totp": wrong}
        )
        assert response.status_code == 401
    right = pyotp.TOTP(user.totp_secret).now()
    ended = await api.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, "totp": right}
    )
    assert (ended.status_code, ended.json()["code"]) == (401, "auth.challenge_ended")


# 13. A route with no declared access fails the route audit: test_route_audit_contract.py


# 14. Deleting an account runs every module's delete hook


@not_built
async def test_deleting_an_account_runs_every_delete_hook(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    scheduled = await api.http.post("/api/auth/account/delete")
    assert (scheduled.status_code, scheduled.json()["status"]) == (202, "deletion_scheduled")
    await api.advance(14 * DAY + MINUTE)
    await api.run_jobs()
    assert user.id in (await api.http.get("/api/_test/delete-hooks")).json()["deleted"]
    assert (await api.sign_in(user)).status_code == 401


@not_built
async def test_nothing_is_deleted_before_the_14_days(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.http.post("/api/auth/account/delete")
    await api.advance(13 * DAY)
    await api.run_jobs()
    assert user.id not in (await api.http.get("/api/_test/delete-hooks")).json()["deleted"]


@not_built
async def test_signing_in_cancels_a_deletion(api: Api) -> None:
    keeps, leaves = await api.make_user(), await api.make_user()
    for user in (keeps, leaves):
        browser = api.another_browser()
        await browser.signed_in_as(user)
        await browser.http.post("/api/auth/account/delete")
    await api.advance(3 * DAY)
    await api.another_browser().signed_in_as(keeps)  # cancels its deletion
    await api.advance(12 * DAY)
    await api.run_jobs()
    deleted = (await api.http.get("/api/_test/delete-hooks")).json()["deleted"]
    assert leaves.id in deleted  # the jobs ran
    assert keeps.id not in deleted
