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

import asyncio
import base64
import statistics
import time
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

import httpx
import pyotp
import pytest

from .authenticator import Authenticator, Credential, b64url, unb64url
from .conftest import (
    NEW_PASSWORD,
    OTHER_PASSWORD,
    PASSWORD,
    UNCHECKED,
    Api,
    NotBuilt,
    User,
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


async def test_reset_answers_the_same_for_known_and_unknown(api: Api) -> None:
    user = await api.make_user()
    known = await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    unknown = await api.http.post("/api/auth/password/reset-request", json={"email": UNKNOWN})
    assert _shape(known) == _shape(unknown) == (202, {"status": "check_email"})


async def test_codes_answer_the_same_and_staff_are_sent_nothing(api: Api) -> None:
    member = await api.make_user()
    staff = await api.make_user(roles=["admin"], totp=True)
    answers = [
        _shape(await api.http.post("/api/auth/code", json={"email": email}))
        for email in (member.email, UNKNOWN, staff.email)
    ]
    assert answers == [(202, {"status": "check_email"})] * 3
    assert len(await api.mail(member.email, at_least=1)) == 1
    assert await api.mail(staff.email) == []


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


@pytest.mark.parametrize(
    "route",
    [
        "sign-in",
        "sign-up",
        "code",
        "password/reset-request",
    ],
)
async def test_a_missing_account_takes_similar_time(api: Api, route: str) -> None:
    """Interleaved, against a baseline that hashes nothing: an unknown email
    is answered in neither half nor twice the time of a known one. A sign-up
    makes its address known, so each of its rounds signs up a new one. Each
    round moves the clock past the last one's resend wait, so a known address
    is sent a code or a reset link every round, not answered from the wait."""
    user = await api.make_user()
    password = {"sign-in": "a wrong password 1", "sign-up": PASSWORD}.get(route)

    def body(email: str) -> dict[str, str]:
        return {"email": email} | ({"password": password} if password else {})

    known, unknown, baseline = [], [], []
    for round_ in range(7):
        await api.http.post("/api/_test/reset")  # counts start over: no 429s skew it
        await api.advance(61 * (round_ + 1))  # the reset put the clock back
        baseline.append(await _median(api.session, 1))
        known.append(
            await _median(lambda: api.http.post(f"/api/auth/{route}", json=body(user.email)), 1)
        )
        if route in {"code", "password/reset-request"}:  # the positive control: it sent mail
            assert len(await api.mail(user.email, at_least=1)) == 1
        missing = f"new-{uuid.uuid4().hex[:12]}@site.test" if route == "sign-up" else UNKNOWN
        unknown.append(
            await _median(partial(api.http.post, f"/api/auth/{route}", json=body(missing)), 1)
        )
    base = statistics.median(baseline)
    known_cost = max(statistics.median(known) - base, 1e-4)
    unknown_cost = max(statistics.median(unknown) - base, 1e-4)
    assert 0.5 <= unknown_cost / known_cost <= 2.0, (known_cost, unknown_cost)


# 2. A reset, code or link token works once, and never after it expires


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
    late = await api.new_token(user.email, "/auth/reset", not_=early)
    assert late != early
    await api.advance(31 * MINUTE)
    gone = await api.http.post(
        "/api/auth/password/reset", json={"token": late, "password": OTHER_PASSWORD}
    )
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")


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


async def test_a_sign_in_code_lasts_10_minutes(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    early = code_in((await api.last_mail(user.email))["text"])
    await api.advance(9 * MINUTE)
    still = await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": early})
    assert still.status_code == 200  # the control: alive at 9 minutes

    other = api.another_browser()
    sent = len(await api.mail(user.email, at_least=2))  # the code and the sign-in's notice
    await other.http.post("/api/auth/code", json={"email": user.email})  # past the resend wait
    assert len(await api.mail(user.email, at_least=sent + 1)) == sent + 1
    late = code_in((await api.last_mail(user.email))["text"])
    await api.advance(11 * MINUTE)
    gone = await other.http.post("/api/auth/code/verify", json={"email": user.email, "code": late})
    assert (gone.status_code, gone.json()["code"]) == (401, "auth.invalid_code")


async def test_five_wrong_tries_end_a_code(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    code = code_in((await api.last_mail(user.email))["text"])
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(5):
        await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": wrong})
    ended = await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": code})
    assert (ended.status_code, ended.json()["code"]) == (401, "auth.invalid_code")


async def test_a_resend_within_60_seconds_sends_nothing(api: Api) -> None:
    user = await api.make_user()
    first = await api.http.post("/api/auth/code", json={"email": user.email})
    second = await api.http.post("/api/auth/code", json={"email": user.email})
    assert _shape(first) == _shape(second) == (202, {"status": "check_email"})
    assert len(await api.mail(user.email, at_least=1)) == 1
    await api.advance(61)
    await api.http.post("/api/auth/code", json={"email": user.email})
    assert len(await api.mail(user.email, at_least=2)) == 2


async def test_a_magic_link_works_once(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/link")
    first = await api.http.post("/api/auth/link/confirm", json={"token": token})
    again = await api.another_browser().http.post("/api/auth/link/confirm", json={"token": token})
    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (401, "auth.invalid_link")


async def test_a_magic_link_lasts_10_minutes(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    early = token_in((await api.last_mail(user.email))["text"], "/auth/link")
    await api.advance(9 * MINUTE)
    assert (await api.http.post("/api/auth/link/confirm", json={"token": early})).status_code == 200

    other = api.another_browser()
    await other.http.post("/api/auth/code", json={"email": user.email})
    late = await api.new_token(user.email, "/auth/link", not_=early)
    await api.advance(11 * MINUTE)
    gone = await other.http.post("/api/auth/link/confirm", json={"token": late})
    assert (gone.status_code, gone.json()["code"]) == (401, "auth.invalid_link")


# 3. Opening a magic link with GET alone signs nobody in


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


def _step_up(
    method: str, path: str, body: dict[str, object] | None, *, built: bool = False
) -> object:
    """One step-up action; each is marked not built until its route lands."""
    return pytest.param(method, path, body, id=f"{method} {path}", marks=() if built else not_built)


STEP_UP = [
    _step_up(
        "POST",
        "/api/auth/password/change",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        built=True,
    ),
    _step_up("POST", "/api/auth/email/change", {"email": "new-address@site.test"}, built=True),
    _step_up("POST", "/api/auth/totp/setup", None, built=True),
    _step_up("DELETE", "/api/auth/totp", None, built=True),
    _step_up("POST", "/api/auth/recovery-codes", None, built=True),
    _step_up("POST", "/api/auth/passkeys/register/start", {"name": "Laptop"}, built=True),
    _step_up("PATCH", f"/api/auth/passkeys/{ZERO_ID}", {"name": "Desk"}, built=True),
    _step_up("DELETE", f"/api/auth/passkeys/{ZERO_ID}", None, built=True),
    _step_up("POST", "/api/auth/api-keys", {"name": "CI", "scopes": []}),
    _step_up("POST", "/api/auth/account/delete", None),
]


def _route(param: object) -> str:
    method, path, _ = param.values  # type: ignore[attr-defined]
    return f"{method} {path}".replace(ZERO_ID, "{id}")


@pytest.mark.parametrize(("method", "path", "body"), STEP_UP)
async def test_step_up_actions_demand_a_recent_sign_in(
    api: Api, method: str, path: str, body: dict[str, str] | None
) -> None:
    await api.signed_in_as(await api.make_user(totp=True))
    await api.advance(11 * MINUTE)
    response = await api.http.request(method, path, json=body)
    assert (response.status_code, response.json()["code"]) == (403, "auth.step_up_required")


@pytest.mark.parametrize(("method", "path", "body"), STEP_UP)
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
    """Every built step-up action is marked now; the rest are not built."""
    listed = set((await api.test_routes()).get("step_up", []))
    built = {_route(p) for p in STEP_UP if not p.marks}  # type: ignore[attr-defined]
    assert built <= listed
    expected = {_route(p) for p in STEP_UP} | {"PUT /api/auth/admin/users/{id}/roles"}
    if not expected <= listed:
        raise NotBuilt(f"not built yet: {sorted(expected - listed)}")


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


async def test_five_failed_step_ups_end_the_session(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    await api.advance(11 * MINUTE)
    for _ in range(5):
        await api.http.post("/api/auth/step-up", json={"password": "a wrong password 1"})
    assert (await api.session()).status_code == 401


# 7. A password change ends every other session (and a reset ends them all)


async def test_a_password_change_ends_every_other_session(api: Api) -> None:
    user = await api.make_user()
    other = api.another_browser()
    await api.signed_in_as(user)
    await other.signed_in_as(user)
    response = await api.http.post(
        "/api/auth/password/change",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert _shape(response) == (200, {"status": "password_changed"})
    assert (await api.session()).status_code == 200
    assert (await other.session()).status_code == 401


async def test_after_a_password_change_only_the_new_one_signs_in(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.http.post(
        "/api/auth/password/change",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert (await api.another_browser().sign_in(user)).status_code == 401
    assert (await api.another_browser().sign_in(user, NEW_PASSWORD)).status_code == 200


async def test_a_password_change_needs_the_current_password(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    refused = await api.http.post(
        "/api/auth/password/change",
        json={"current_password": OTHER_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_credentials")
    assert (await api.session()).status_code == 200  # the session is kept
    assert (await api.another_browser().sign_in(user)).status_code == 200


async def test_a_password_change_judges_the_new_one(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    refused = await api.http.post(
        "/api/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "too short"},
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "auth.password_rejected")
    assert refused.json()["detail"]


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


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/totp/setup",
        "/api/auth/passkeys/register/start",
    ],
)
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
    suspend = await api.http.post(
        f"/api/auth/admin/users/{owner.id}/suspend", json={"reason": "other"}
    )
    assert (suspend.status_code, suspend.json()["code"]) == (403, "auth.role_not_yours")


@not_built
async def test_the_last_owner_stays(api: Api) -> None:
    await api.forget_every_account()  # earlier tests made owners of their own
    owner = await api.make_user(roles=["owner"], totp=True)
    await api.signed_in_as(owner)
    demote = await api.http.put(
        f"/api/auth/admin/users/{owner.id}/roles", json={"roles": ["admin"]}
    )
    assert (demote.status_code, demote.json()["code"]) == (409, "auth.last_owner")


# 12. Each rate limit in 14.6 triggers at its threshold


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


async def test_a_known_browser_still_signs_in_over_the_limit(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.http.post("/api/auth/sign-out")
    await _over_the_limit(api, user.email)
    assert (await api.another_browser().sign_in(user)).status_code == 429
    assert (await api.sign_in(user)).status_code == 200


async def test_a_known_browser_with_a_wrong_password_is_still_refused(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.http.post("/api/auth/sign-out")
    await _over_the_limit(api, user.email)
    assert (await api.sign_in(user, "a wrong password 1")).status_code in {401, 429}
    assert (await api.sign_in(user)).status_code == 200


async def test_a_device_cookie_helps_only_its_own_account(api: Api) -> None:
    mine, theirs = await api.make_user(), await api.make_user()
    await api.signed_in_as(mine)
    await api.http.post("/api/auth/sign-out")
    await _over_the_limit(api, theirs.email)
    assert (await api.sign_in(theirs)).status_code == 429
    forged = api.another_browser()
    forged.plant_cookie("__Host-dk_device", "forged")
    assert (await forged.sign_in(theirs)).status_code == 429


async def test_the_device_cookie_outlives_sign_out_and_is_no_session(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    await api.http.post("/api/auth/sign-out")
    device = api.http.cookies.get("__Host-dk_device")
    assert device
    assert device != api.session_cookie
    assert (await api.session()).status_code == 401


async def test_codes_3_per_email_per_15_minutes(api: Api) -> None:
    user = await api.make_user()
    for _ in range(3):
        await api.http.post("/api/auth/code", json={"email": user.email})
        await api.advance(61)  # past the resend wait
    assert len(await api.mail(user.email, at_least=3)) == 3
    fourth = await api.http.post("/api/auth/code", json={"email": user.email})
    assert fourth.status_code == 429


async def test_code_limits_ignore_the_case_of_an_address(api: Api) -> None:
    user = await api.make_user()
    for variant in (user.email, user.email.upper(), user.email.title()):
        await api.http.post("/api/auth/code", json={"email": variant})
        await api.advance(61)
    fourth = await api.http.post("/api/auth/code", json={"email": user.email.swapcase()})
    assert fourth.status_code == 429


async def test_codes_10_per_ip_per_hour(api: Api) -> None:
    codes = [
        (await api.http.post("/api/auth/code", json={"email": f"c{i}@site.test"})).status_code
        for i in range(11)
    ]
    assert codes == [202] * 10 + [429]


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


async def test_a_breached_password_is_refused_with_its_reason(api: Api) -> None:
    await api.mark_breached(OTHER_PASSWORD)
    response = await api.http.post(
        "/api/auth/sign-up", json={"email": "breached@site.test", "password": OTHER_PASSWORD}
    )
    assert (response.status_code, response.json()["code"]) == (422, "auth.password_rejected")
    assert "breach" in response.json()["detail"]


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


# A signed-in account can ask for a new verification link (decision 0023)


async def test_a_signed_in_account_can_ask_for_a_new_verification_link(api: Api) -> None:
    user = await api.make_user(verified=False)
    await api.signed_in_as(user)
    sent = await api.http.post("/api/auth/verify-email/resend")
    assert _shape(sent) == (202, {"status": "check_email"})
    token = await api.new_token(user.email, "/auth/verify", not_="")
    verified = await api.http.post("/api/auth/verify-email", json={"token": token})
    assert _shape(verified) == (200, {"status": "verified"})
    assert (await api.session()).json()["user"]["verified"] is True


async def test_a_verified_account_is_sent_no_new_link(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    refused = await api.http.post("/api/auth/verify-email/resend")
    assert (refused.status_code, refused.json()["code"]) == (409, "auth.already_verified")


async def test_a_new_verification_link_needs_a_session(api: Api) -> None:
    refused = await api.http.post("/api/auth/verify-email/resend")
    assert (refused.status_code, refused.json()["code"]) == (401, "kernel.not_signed_in")


async def test_a_new_verification_link_voids_the_last(api: Api) -> None:
    user = await api.make_user(verified=False)
    await api.signed_in_as(user)
    await api.http.post("/api/auth/verify-email/resend")
    first = await api.new_token(user.email, "/auth/verify", not_="")
    await api.advance(61)  # past the wait
    await api.http.post("/api/auth/verify-email/resend")
    second = await api.new_token(user.email, "/auth/verify", not_=first)
    gone = await api.http.post("/api/auth/verify-email", json={"token": first})
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")
    kept = await api.http.post("/api/auth/verify-email", json={"token": second})
    assert _shape(kept) == (200, {"status": "verified"})


async def test_a_new_verification_link_within_60_seconds_sends_nothing(api: Api) -> None:
    user = await api.make_user(verified=False)
    await api.signed_in_as(user)
    first = await api.http.post("/api/auth/verify-email/resend")
    assert len(await api.mail(user.email, at_least=2)) == 2  # the sign-in's notice, the link
    second = await api.http.post("/api/auth/verify-email/resend")
    assert _shape(first) == _shape(second) == (202, {"status": "check_email"})
    assert len(await api.mail(user.email)) == 2
    await api.advance(61)
    await api.http.post("/api/auth/verify-email/resend")
    assert len(await api.mail(user.email, at_least=3)) == 3


async def test_new_verification_links_3_per_account_per_15_minutes(api: Api) -> None:
    user = await api.make_user(verified=False)
    await api.signed_in_as(user)
    for _ in range(3):
        assert (await api.http.post("/api/auth/verify-email/resend")).status_code == 202
        await api.advance(61)  # past the wait
    fourth = await api.http.post("/api/auth/verify-email/resend")
    assert (fourth.status_code, fourth.json()["code"]) == (429, "kernel.rate_limited")


# Email change (14.7; decision 0024)


def _moved(user: User) -> str:
    return f"moved-{user.id[:8]}-{uuid.uuid4().hex[:6]}@site.test"


async def _change_and_confirm(api: Api, user: User) -> str:
    """Move the signed-in account to a new address; give that address."""
    new = _moved(user)
    asked = await api.http.post("/api/auth/email/change", json={"email": new})
    assert _shape(asked) == (202, {"status": "check_email"})
    token = await api.new_token(new, "/auth/email", not_="")
    confirmed = await api.http.post("/api/auth/email/confirm", json={"token": token})
    assert _shape(confirmed) == (200, {"status": "email_changed"})
    return new


async def test_an_email_change_is_confirmed_by_the_new_address(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    new = _moved(user)
    await api.http.post("/api/auth/email/change", json={"email": new})
    token = await api.new_token(new, "/auth/email", not_="")
    assert (await api.session()).json()["user"]["email"] == user.email  # until it's confirmed
    confirmed = await api.http.post("/api/auth/email/confirm", json={"token": token})
    assert _shape(confirmed) == (200, {"status": "email_changed"})
    shown = (await api.session()).json()["user"]
    assert (shown["email"], shown["verified"]) == (new, True)
    assert await api.new_token(user.email, "/auth/email/undo", not_="")
    again = await api.http.post("/api/auth/email/confirm", json={"token": token})
    assert (again.status_code, again.json()["code"]) == (400, "auth.token_invalid")


async def test_the_old_address_can_undo_a_change(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    new = await _change_and_confirm(api, user)
    token = await api.new_token(user.email, "/auth/email/undo", not_="")
    undone = await api.another_browser().http.post("/api/auth/email/undo", json={"token": token})
    assert _shape(undone) == (200, {"status": "email_restored"})
    assert (await api.session()).status_code == 401  # every session ended
    assert (await api.another_browser().sign_in(user)).status_code == 200
    moved = User(id=user.id, email=new, password=user.password)
    assert (await api.another_browser().sign_in(moved)).status_code == 401


async def test_an_undo_link_lasts_7_days(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await _change_and_confirm(api, user)
    early = await api.new_token(user.email, "/auth/email/undo", not_="")
    await api.advance(7 * DAY - MINUTE)
    kept = await api.http.post("/api/auth/email/undo", json={"token": early})
    assert kept.status_code == 200  # the control: alive just under 7 days

    await api.signed_in_as(user)
    await _change_and_confirm(api, user)
    late = await api.new_token(user.email, "/auth/email/undo", not_=early)
    await api.advance(7 * DAY + MINUTE)
    gone = await api.http.post("/api/auth/email/undo", json={"token": late})
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")


async def test_a_change_link_lasts_24_hours(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    first = _moved(user)
    await api.http.post("/api/auth/email/change", json={"email": first})
    early = await api.new_token(first, "/auth/email", not_="")
    await api.advance(DAY - MINUTE)
    kept = await api.http.post("/api/auth/email/confirm", json={"token": early})
    assert kept.status_code == 200  # the control: alive just under a day

    await api.signed_in_as(User(id=user.id, email=first, password=user.password))
    second = _moved(user)
    await api.http.post("/api/auth/email/change", json={"email": second})
    late = await api.new_token(second, "/auth/email", not_="")
    await api.advance(DAY + MINUTE)
    gone = await api.http.post("/api/auth/email/confirm", json={"token": late})
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")


async def test_opening_a_change_link_with_get_changes_nothing(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    new = _moved(user)
    await api.http.post("/api/auth/email/change", json={"email": new})
    token = await api.new_token(new, "/auth/email", not_="")
    scanner = api.another_browser()
    for path in (f"/auth/email?token={token}", f"/api/auth/email/confirm?token={token}"):
        await scanner.http.get(path, extensions=UNCHECKED)
    assert (await api.session()).json()["user"]["email"] == user.email
    confirmed = await api.http.post("/api/auth/email/confirm", json={"token": token})
    assert confirmed.status_code == 200  # the scanner used nothing up


async def test_a_change_to_an_address_with_an_account_sends_it_no_link(api: Api) -> None:
    mine, theirs = await api.make_user(), await api.make_user()
    await api.signed_in_as(mine)
    asked = await api.http.post("/api/auth/email/change", json={"email": theirs.email})
    assert _shape(asked) == (202, {"status": "check_email"})
    notices = await api.mail(theirs.email, at_least=1)
    assert all("/auth/email?token=" not in m["text"] for m in notices)


async def test_email_changes_3_per_account_per_15_minutes(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    for _ in range(3):
        asked = await api.http.post("/api/auth/email/change", json={"email": _moved(user)})
        assert asked.status_code == 202
        await api.advance(61)  # past the wait
    fourth = await api.http.post("/api/auth/email/change", json={"email": _moved(user)})
    assert (fourth.status_code, fourth.json()["code"]) == (429, "kernel.rate_limited")


# TOTP setup and confirm (14.4; decision 0026)


async def _set_up_totp(api: Api) -> str:
    """Set up a TOTP on the signed-in account: its secret."""
    response = await api.http.post("/api/auth/totp/setup")
    assert response.status_code == 200, response.text
    secret: str = response.json()["secret"]
    return secret


async def _confirm_totp(api: Api, code: str) -> httpx.Response:
    return await api.http.post("/api/auth/totp/confirm", json={"code": code})


def _next_step(secret: str) -> str:
    """The code of the step after this one: within the drift, and never a
    step a code was already taken for."""
    return pyotp.TOTP(secret).at(time.time() + 30)


async def _second_factor(api: Api, user: User) -> tuple[Api, dict[str, object]]:
    """A sign-in on a new browser, as far as its second factor."""
    browser = api.another_browser()
    first = await browser.sign_in(user)
    assert first.status_code == 200, first.text
    body: dict[str, object] = first.json()
    assert body["status"] == "second_factor", body
    return browser, body


async def test_setting_up_a_totp_gives_its_secret_and_uri(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    response = await api.http.post("/api/auth/totp/setup")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"secret", "otpauth_uri"}
    secret = body["secret"]
    assert len(base64.b32decode(secret + "=" * (-len(secret) % 8))) >= 20  # 160 bits
    parsed = pyotp.parse_uri(body["otpauth_uri"])
    assert isinstance(parsed, pyotp.TOTP)
    assert (parsed.secret, parsed.digits, parsed.interval) == (secret, 6, 30)
    assert parsed.name == user.email
    assert parsed.issuer


async def test_a_confirmed_totp_is_a_second_factor_with_ten_recovery_codes(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    secret = await _set_up_totp(api)
    confirmed = await _confirm_totp(api, pyotp.TOTP(secret).now())
    assert (confirmed.status_code, set(confirmed.json())) == (200, {"recovery_codes"})
    codes = confirmed.json()["recovery_codes"]
    assert len(codes) == len(set(codes)) == 10
    assert (await api.session()).json()["user"]["second_factor"] is True
    browser, first = await _second_factor(api, user)
    assert {"totp", "recovery_code"} <= set(first["methods"])  # type: ignore[arg-type]
    finished = await browser.http.post(
        "/api/auth/sign-in/second-factor",
        json={"challenge": first["challenge"], "totp": _next_step(secret)},
    )
    assert (finished.status_code, finished.json()["status"]) == (200, "signed_in")


async def test_each_recovery_code_works_once(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    secret = await _set_up_totp(api)
    codes = (await _confirm_totp(api, pyotp.TOTP(secret).now())).json()["recovery_codes"]
    for code, status in ((codes[0], 200), (codes[0], 401), (codes[1], 200)):
        browser, first = await _second_factor(api, user)
        response = await browser.http.post(
            "/api/auth/sign-in/second-factor",
            json={"challenge": first["challenge"], "recovery_code": code},
        )
        assert response.status_code == status, response.text


async def test_an_unconfirmed_totp_leaves_signing_in_as_it_was(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await _set_up_totp(api)  # never confirmed
    assert (await api.session()).json()["user"]["second_factor"] is False
    signed = await api.another_browser().sign_in(user)
    assert (signed.status_code, signed.json()["status"]) == (200, "signed_in")


async def test_a_wrong_code_confirms_nothing(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    secret = await _set_up_totp(api)
    wrong = await _confirm_totp(api, wrong_totp(secret))
    assert (wrong.status_code, wrong.json()["code"]) == (401, "auth.invalid_second_factor")
    assert (await api.session()).json()["user"]["second_factor"] is False
    assert (await _confirm_totp(api, pyotp.TOTP(secret).now())).status_code == 200  # the control


async def test_five_wrong_codes_end_the_session(api: Api) -> None:
    """A wrong code counts as a failed step-up (14.6)."""
    await api.signed_in_as(await api.make_user())
    secret = await _set_up_totp(api)
    for _ in range(4):
        wrong = await _confirm_totp(api, wrong_totp(secret))
        assert (wrong.status_code, wrong.json()["code"]) == (401, "auth.invalid_second_factor")
    assert (await api.session()).status_code == 200  # four leave it
    fifth = await _confirm_totp(api, wrong_totp(secret))
    assert (fifth.status_code, fifth.json()["code"]) == (401, "kernel.not_signed_in")
    assert (await api.session()).status_code == 401


async def test_the_code_that_confirms_cant_be_used_again(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    secret = await _set_up_totp(api)
    code = pyotp.TOTP(secret).now()
    assert (await _confirm_totp(api, code)).status_code == 200
    browser, first = await _second_factor(api, user)
    again = await browser.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": first["challenge"], "totp": code}
    )
    assert (again.status_code, again.json()["code"]) == (401, "auth.invalid_second_factor")
    later = await browser.http.post(
        "/api/auth/sign-in/second-factor",
        json={"challenge": first["challenge"], "totp": _next_step(secret)},
    )
    assert later.status_code == 200  # the control: the challenge and the TOTP work


async def test_setting_up_again_replaces_the_unconfirmed_secret(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    first, second = await _set_up_totp(api), await _set_up_totp(api)
    assert first != second
    stale = await _confirm_totp(api, pyotp.TOTP(first).now())
    assert (stale.status_code, stale.json()["code"]) == (401, "auth.invalid_second_factor")
    assert (await _confirm_totp(api, pyotp.TOTP(second).now())).status_code == 200


async def test_a_confirmed_totp_isnt_set_up_over(api: Api) -> None:
    user = await api.make_user(totp=True)
    assert user.totp_secret
    await api.signed_in_as(user)
    refused = await api.http.post("/api/auth/totp/setup")
    assert (refused.status_code, refused.json()["code"]) == (409, "auth.totp_exists")
    browser, first = await _second_factor(api, user)  # the TOTP it has still works
    finished = await browser.http.post(
        "/api/auth/sign-in/second-factor",
        json={"challenge": first["challenge"], "totp": _next_step(user.totp_secret)},
    )
    assert finished.status_code == 200


async def test_confirming_with_nothing_set_up_is_refused(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    nothing = await _confirm_totp(api, "123456")
    assert (nothing.status_code, nothing.json()["code"]) == (409, "auth.no_pending_totp")
    secret = await _set_up_totp(api)
    assert (await _confirm_totp(api, pyotp.TOTP(secret).now())).status_code == 200  # the control
    again = await _confirm_totp(api, _next_step(secret))
    assert (again.status_code, again.json()["code"]) == (409, "auth.no_pending_totp")


async def test_confirming_needs_a_session(api: Api) -> None:
    refused = await _confirm_totp(api, "123456")
    assert (refused.status_code, refused.json()["code"]) == (401, "kernel.not_signed_in")


# Removing a TOTP and new recovery codes (14.4, 14.5; decision 0027)


async def _finish(browser: Api, challenge: object, **factor: str) -> httpx.Response:
    return await browser.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, **factor}
    )


async def test_removing_a_totp_ends_every_other_session(api: Api) -> None:
    """The owner's answer: removing a TOTP is the second-factor reset that
    14.5 says ends every other session. This one stays."""
    user = await api.make_user(totp=True)
    assert user.totp_secret
    await api.signed_in_as(user)
    other, first = await _second_factor(api, user)
    assert (await _finish(other, first["challenge"], totp=_next_step(user.totp_secret))).is_success
    assert (await other.session()).status_code == 200  # the control
    removed = await api.http.delete("/api/auth/totp")
    assert (removed.status_code, removed.content) == (204, b"")
    assert (await other.session()).status_code == 401
    mine = await api.session()
    assert mine.status_code == 200
    assert mine.json()["user"]["second_factor"] is False
    signed = await api.another_browser().sign_in(user)
    assert (signed.status_code, signed.json()["status"]) == (200, "signed_in")


async def test_removing_a_totp_voids_its_recovery_codes(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    first = await _set_up_totp(api)
    old = (await _confirm_totp(api, pyotp.TOTP(first).now())).json()["recovery_codes"]
    assert (await api.http.delete("/api/auth/totp")).status_code == 204
    second = await _set_up_totp(api)
    new = (await _confirm_totp(api, pyotp.TOTP(second).now())).json()["recovery_codes"]
    browser, started = await _second_factor(api, user)
    stale = await _finish(browser, started["challenge"], recovery_code=old[0])
    assert (stale.status_code, stale.json()["code"]) == (401, "auth.invalid_second_factor")
    fresh = await _finish(browser, started["challenge"], recovery_code=new[0])
    assert fresh.status_code == 200  # the control


async def test_removing_with_no_totp_ends_nothing(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    other = api.another_browser()
    await other.signed_in_as(user)
    assert (await api.http.delete("/api/auth/totp")).status_code == 204
    assert (await other.session()).status_code == 200


async def test_new_recovery_codes_replace_the_old(api: Api) -> None:
    user = await api.make_user(totp=True)
    await api.signed_in_as(user)
    first = await api.http.post("/api/auth/recovery-codes")
    assert (first.status_code, set(first.json())) == (200, {"recovery_codes"})
    old = first.json()["recovery_codes"]
    assert len(old) == len(set(old)) == 10
    new = (await api.http.post("/api/auth/recovery-codes")).json()["recovery_codes"]
    assert len(new) == 10
    assert not set(old) & set(new)
    browser, started = await _second_factor(api, user)
    stale = await _finish(browser, started["challenge"], recovery_code=old[0])
    assert (stale.status_code, stale.json()["code"]) == (401, "auth.invalid_second_factor")
    fresh = await _finish(browser, started["challenge"], recovery_code=new[0])
    assert fresh.status_code == 200  # the control


async def test_new_recovery_codes_need_a_confirmed_totp(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    for _ in range(2):  # with no TOTP, then with one set up but not confirmed
        refused = await api.http.post("/api/auth/recovery-codes")
        assert (refused.status_code, refused.json()["code"]) == (409, "auth.no_second_factor")
        await _set_up_totp(api)


# Passkeys (14.2, 14.4, 14.5; decision 0028)

REGISTER_START = "/api/auth/passkeys/register/start"
REGISTER_FINISH = "/api/auth/passkeys/register/finish"
PASSKEY_START = "/api/auth/passkeys/sign-in/start"
PASSKEY_FINISH = "/api/auth/passkeys/sign-in/finish"
SECOND_FACTOR_PASSKEY = "/api/auth/sign-in/second-factor/passkey"
STEP_UP_PASSKEY = "/api/auth/step-up/passkey"


def _key(api: Api, *, counter: bool = False) -> Authenticator:
    """An authenticator for this site: a synced passkey, or with `counter` a
    hardware key whose sign count rises."""
    return Authenticator(str(api.http.base_url), counter=counter)


async def _register(api: Api, key: Authenticator, name: str = "Laptop") -> dict[str, Any]:
    """Register a passkey on the signed-in account: what finish answered."""
    start = await api.http.post(REGISTER_START, json={"name": name})
    assert start.status_code == 200, start.text
    finish = await api.http.post(REGISTER_FINISH, json=key.create(start.json()))
    assert finish.status_code == 201, finish.text
    body: dict[str, Any] = finish.json()
    return body


async def _passkey_options(browser: Api) -> dict[str, Any]:
    start = await browser.http.post(PASSKEY_START)
    assert start.status_code == 200, start.text
    options: dict[str, Any] = start.json()
    return options


async def _sign_in_by_passkey(browser: Api, key: Authenticator, **knobs: Any) -> httpx.Response:
    options = await _passkey_options(browser)
    return await browser.http.post(PASSKEY_FINISH, json=key.get(options, **knobs))


async def _with_a_passkey(api: Api, **fields: Any) -> tuple[User, Authenticator, dict[str, Any]]:
    """A signed-in account holding one passkey."""
    user = await api.make_user(**fields)
    await api.signed_in_as(user)
    key = _key(api)
    return user, key, await _register(api, key)


def _code(response: httpx.Response) -> tuple[int, object]:
    return response.status_code, response.json().get("code")


async def test_registering_asks_for_a_discoverable_passkey_with_user_verification(
    api: Api,
) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    start = await api.http.post(REGISTER_START, json={"name": "Laptop"})
    assert start.status_code == 200, start.text
    options = start.json()
    assert options["rp"]["id"] == api.http.base_url.host
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["attestation"] == "none"
    assert len(unb64url(options["challenge"])) >= 32
    assert options["user"]["name"] == user.email
    assert user.email.encode() not in unb64url(options["user"]["id"])  # nothing personal


async def test_a_registered_passkey_is_named_and_listed_oldest_first(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    first = await _register(api, _key(api), "  Work laptop ")
    assert set(first) == {"id", "name", "created_at", "last_used_at"}
    assert (first["name"], first["last_used_at"]) == ("Work laptop", None)
    second = await _register(api, _key(api), "Phone")
    listed = await api.http.get("/api/auth/passkeys")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [(item["id"], item["name"]) for item in items] == [
        (first["id"], "Work laptop"),
        (second["id"], "Phone"),
    ]
    assert set(items[0]) == {"id", "name", "created_at", "last_used_at"}


async def test_registering_excludes_the_accounts_passkeys(api: Api) -> None:
    _, key, _ = await _with_a_passkey(api)
    options = (await api.http.post(REGISTER_START, json={"name": "Again"})).json()
    excluded = [item["id"] for item in options["excludeCredentials"]]
    assert excluded == [b64url(key.credentials[0].id)]


async def test_a_registration_finishes_once_and_only_in_its_own_session(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    other = api.another_browser()
    await other.signed_in_as(user)
    key = _key(api)
    options = (await api.http.post(REGISTER_START, json={"name": "Laptop"})).json()
    credential = key.create(options)
    elsewhere = await other.http.post(REGISTER_FINISH, json=credential)
    assert _code(elsewhere) == (400, "auth.invalid_passkey")
    here = await api.http.post(REGISTER_FINISH, json=credential)
    assert here.status_code == 201, here.text  # the other session's try used nothing up
    again = await api.http.post(REGISTER_FINISH, json=key.create(options))
    assert _code(again) == (400, "auth.invalid_passkey")


async def test_a_registration_challenge_lasts_5_minutes(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    key = _key(api)
    late = (await api.http.post(REGISTER_START, json={"name": "Laptop"})).json()
    await api.advance(5 * MINUTE + 1)
    refused = await api.http.post(REGISTER_FINISH, json=key.create(late))
    assert _code(refused) == (400, "auth.invalid_passkey")
    await _register(api, key)  # the control: a new challenge works


async def test_a_passkey_without_user_verification_isnt_registered(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    key = _key(api)
    options = (await api.http.post(REGISTER_START, json={"name": "Laptop"})).json()
    refused = await api.http.post(REGISTER_FINISH, json=key.create(options, uv=False))
    assert _code(refused) == (400, "auth.invalid_passkey")
    assert (await api.http.get("/api/auth/passkeys")).json()["items"] == []


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
async def test_a_passkey_needs_a_name_of_1_to_80_characters(api: Api, name: str) -> None:
    await api.signed_in_as(await api.make_user())
    refused = await api.http.post(REGISTER_START, json={"name": name})
    assert _code(refused) == (422, "kernel.invalid_request")


async def test_an_account_holds_at_most_20_passkeys(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    key = _key(api)
    for number in range(20):
        await _register(api, key, f"Key {number}")
    refused = await api.http.post(REGISTER_START, json={"name": "One more"})
    assert _code(refused) == (409, "auth.too_many_passkeys")


@pytest.mark.parametrize("roles", [["member"], ["editor"]], ids=["member", "staff"])
async def test_a_passkey_alone_signs_anyone_in(api: Api, roles: list[str]) -> None:
    """Staff too, and with no second-factor step: a verified passkey is two
    factors (the owner's answer)."""
    user, key, _ = await _with_a_passkey(api, roles=roles, totp=True)
    browser = api.another_browser()
    options = await _passkey_options(browser)
    assert not options.get("allowCredentials")  # no email asked, so nothing to name
    assert options["userVerification"] == "required"
    signed = await browser.http.post(PASSKEY_FINISH, json=key.get(options))
    assert signed.status_code == 200, signed.text
    assert (signed.json()["status"], signed.json()["user"]["id"]) == ("signed_in", user.id)
    assert browser.session_cookie is not None
    assert (await browser.session()).json()["user"]["id"] == user.id
    [listed] = (await api.http.get("/api/auth/passkeys")).json()["items"]
    assert listed["last_used_at"] is not None


async def test_every_wrong_passkey_sign_in_gets_the_same_answer(api: Api) -> None:
    _, key, _ = await _with_a_passkey(api)
    registered = key.credentials[0]
    stranger: Credential = key.make(registered.rp_id, registered.user_handle)  # never registered
    wrongs: list[dict[str, Any]] = [
        {"credential": registered, "uv": False},
        {"credential": registered, "origin": "https://elsewhere.test"},
        {"credential": registered, "rp_id": "elsewhere.test"},
        {"credential": registered, "tamper": True},
        {"credential": registered, "user_handle": bytes(16)},
        {"credential": stranger},
    ]
    answers = [_shape(await _sign_in_by_passkey(api.another_browser(), key, **w)) for w in wrongs]
    assert answers[0][0] == 401
    assert answers[0][1]["code"] == "auth.invalid_passkey"  # type: ignore[index]
    assert all(answer == answers[0] for answer in answers), answers
    signed = await _sign_in_by_passkey(api.another_browser(), key, credential=registered)
    assert signed.status_code == 200  # the control


async def test_a_passkey_sign_in_challenge_works_once_and_for_5_minutes(api: Api) -> None:
    _, key, _ = await _with_a_passkey(api)
    options = await _passkey_options(api.another_browser())
    first = await api.another_browser().http.post(PASSKEY_FINISH, json=key.get(options))
    assert first.status_code == 200, first.text
    again = await api.another_browser().http.post(PASSKEY_FINISH, json=key.get(options))
    assert _code(again) == (401, "auth.invalid_passkey")
    late = await _passkey_options(api.another_browser())
    await api.advance(5 * MINUTE + 1)
    expired = await api.another_browser().http.post(PASSKEY_FINISH, json=key.get(late))
    assert _code(expired) == (401, "auth.invalid_passkey")


async def test_one_passkey_answer_sent_twice_at_once_signs_in_once(api: Api) -> None:
    _, key, _ = await _with_a_passkey(api)
    answer = key.get(await _passkey_options(api.another_browser()))
    browsers = [api.another_browser(), api.another_browser()]
    answers = await asyncio.gather(
        *(browser.http.post(PASSKEY_FINISH, json=answer) for browser in browsers)
    )
    assert sorted(response.status_code for response in answers) == [200, 401]
    [winner] = [b for b, response in zip(browsers, answers, strict=True) if response.is_success]
    assert (await winner.session()).status_code == 200


async def test_a_passkey_whose_sign_count_goes_back_is_refused(api: Api) -> None:
    """A hardware key counts its uses; a count that doesn't rise is a clone."""
    await api.signed_in_as(await api.make_user())
    key = _key(api, counter=True)
    await _register(api, key)
    assert (await _sign_in_by_passkey(api.another_browser(), key)).status_code == 200  # 1
    replayed = await _sign_in_by_passkey(api.another_browser(), key, sign_count=1)
    assert _code(replayed) == (401, "auth.invalid_passkey")
    assert (await _sign_in_by_passkey(api.another_browser(), key)).status_code == 200  # 2


async def _passkey_challenge(api: Api, user: User) -> tuple[Api, str, dict[str, Any]]:
    """A password sign-in on a new browser waiting on its second factor, and
    the passkey options for it."""
    browser, first = await _second_factor(api, user)
    challenge = str(first["challenge"])
    options = await browser.http.post(SECOND_FACTOR_PASSKEY, json={"challenge": challenge})
    assert options.status_code == 200, options.text
    return browser, challenge, options.json()


async def _finish_by_passkey(browser: Api, challenge: str, passkey: object) -> httpx.Response:
    return await browser.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, "passkey": passkey}
    )


async def test_a_passkey_is_a_second_factor_after_a_password(api: Api) -> None:
    user, key, _ = await _with_a_passkey(api)
    browser, first = await _second_factor(api, user)
    assert first["methods"] == ["passkey"]
    options = await browser.http.post(SECOND_FACTOR_PASSKEY, json={"challenge": first["challenge"]})
    assert options.status_code == 200, options.text
    allowed = [item["id"] for item in options.json()["allowCredentials"]]
    assert allowed == [b64url(key.credentials[0].id)]
    # As a second factor, user verification is preferred, not required.
    passkey = key.get(options.json(), uv=False)
    signed = await _finish_by_passkey(browser, str(first["challenge"]), passkey)
    assert (signed.status_code, signed.json()["status"]) == (200, "signed_in")
    assert signed.json()["user"]["id"] == user.id
    assert (await browser.session()).json()["user"]["id"] == user.id


async def test_second_factor_passkey_options_last_5_minutes(api: Api) -> None:
    """The sign-in waits 10 minutes; the options it gave a passkey, only 5."""
    user, key, _ = await _with_a_passkey(api)
    browser, challenge, late = await _passkey_challenge(api, user)
    await api.advance(5 * MINUTE + 1)
    expired = await _finish_by_passkey(browser, challenge, key.get(late))
    assert _code(expired) == (401, "auth.invalid_second_factor")
    fresh = await browser.http.post(SECOND_FACTOR_PASSKEY, json={"challenge": challenge})
    assert fresh.status_code == 200, fresh.text  # the control: the sign-in still waits
    signed = await _finish_by_passkey(browser, challenge, key.get(fresh.json()))
    assert signed.status_code == 200, signed.text


async def test_a_wrong_passkey_is_a_failed_second_factor(api: Api) -> None:
    user, key, _ = await _with_a_passkey(api)
    browser, challenge, options = await _passkey_challenge(api, user)
    for _ in range(4):
        wrong = await _finish_by_passkey(browser, challenge, key.get(options, tamper=True))
        assert _code(wrong) == (401, "auth.invalid_second_factor")
    right = await _finish_by_passkey(browser, challenge, key.get(options))
    assert right.status_code == 200  # four tries spent, the fifth was right


async def test_five_wrong_passkeys_end_the_sign_in(api: Api) -> None:
    user, key, _ = await _with_a_passkey(api)
    browser, challenge, options = await _passkey_challenge(api, user)
    for _ in range(5):
        await _finish_by_passkey(browser, challenge, key.get(options, tamper=True))
    ended = await _finish_by_passkey(browser, challenge, key.get(options))
    assert _code(ended) == (401, "auth.challenge_ended")


async def test_passkey_options_cost_no_try_and_replace_the_last(api: Api) -> None:
    user, key, _ = await _with_a_passkey(api)
    browser, challenge, earlier = await _passkey_challenge(api, user)
    for _ in range(5):
        latest = await browser.http.post(SECOND_FACTOR_PASSKEY, json={"challenge": challenge})
        assert latest.status_code == 200
    stale = await _finish_by_passkey(browser, challenge, key.get(earlier))
    assert _code(stale) == (401, "auth.invalid_second_factor")
    right = await _finish_by_passkey(browser, challenge, key.get(latest.json()))
    assert right.status_code == 200


async def test_second_factor_passkey_options_need_a_live_sign_in_and_a_passkey(api: Api) -> None:
    unknown = await api.http.post(SECOND_FACTOR_PASSKEY, json={"challenge": "x" * 43})
    assert _code(unknown) == (401, "auth.challenge_ended")
    browser, first = await _second_factor(api, await api.make_user(totp=True))
    none = await browser.http.post(SECOND_FACTOR_PASSKEY, json={"challenge": first["challenge"]})
    assert _code(none) == (409, "auth.no_passkey")


async def test_stepping_up_with_a_passkey(api: Api) -> None:
    _, key, made = await _with_a_passkey(api)
    await api.advance(11 * MINUTE)
    options = await api.http.post(STEP_UP_PASSKEY)
    assert options.status_code == 200, options.text
    assert options.json()["userVerification"] == "required"
    assert [item["id"] for item in options.json()["allowCredentials"]] == [
        b64url(key.credentials[0].id)
    ]
    before = api.session_cookie
    stepped = await api.http.post("/api/auth/step-up", json={"passkey": key.get(options.json())})
    assert (stepped.status_code, stepped.json()) == (200, {"status": "recent"})
    assert api.session_cookie not in {None, before}
    renamed = await api.http.patch(f"/api/auth/passkeys/{made['id']}", json={"name": "Desk"})
    assert renamed.status_code == 200, renamed.text


async def test_step_up_passkey_options_are_this_sessions_only(api: Api) -> None:
    _, key, _ = await _with_a_passkey(api)
    other = api.another_browser()
    assert (await _sign_in_by_passkey(other, key)).status_code == 200
    options = (await other.http.post(STEP_UP_PASSKEY)).json()
    refused = await api.http.post("/api/auth/step-up", json={"passkey": key.get(options)})
    assert _code(refused) == (401, "auth.invalid_passkey")
    stepped = await other.http.post("/api/auth/step-up", json={"passkey": key.get(options)})
    assert stepped.status_code == 200  # the control: the other session's try used nothing up


async def test_five_wrong_passkeys_at_step_up_end_the_session(api: Api) -> None:
    _, key, _ = await _with_a_passkey(api)
    for attempt in range(5):
        options = (await api.http.post(STEP_UP_PASSKEY)).json()
        wrong = await api.http.post(
            "/api/auth/step-up", json={"passkey": key.get(options, uv=False)}
        )
        expected = "auth.invalid_passkey" if attempt < 4 else "kernel.not_signed_in"
        assert _code(wrong) == (401, expected)
    assert (await api.session()).status_code == 401


async def test_step_up_passkey_options_need_a_passkey(api: Api) -> None:
    await api.signed_in_as(await api.make_user())
    refused = await api.http.post(STEP_UP_PASSKEY)
    assert _code(refused) == (409, "auth.no_passkey")


async def test_renaming_a_passkey(api: Api) -> None:
    _, _, made = await _with_a_passkey(api)
    renamed = await api.http.patch(f"/api/auth/passkeys/{made['id']}", json={"name": " Desk "})
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["id"], renamed.json()["name"]) == (made["id"], "Desk")
    listed = (await api.http.get("/api/auth/passkeys")).json()["items"]
    assert [item["name"] for item in listed] == ["Desk"]
    too_long = await api.http.patch(f"/api/auth/passkeys/{made['id']}", json={"name": "x" * 81})
    assert _code(too_long) == (422, "kernel.invalid_request")


async def test_removing_a_passkey_ends_every_other_session(api: Api) -> None:
    """The owner's answer: every removal is a second-factor reset (14.5),
    though another passkey and a TOTP remain."""
    _, key, made = await _with_a_passkey(api, totp=True)
    kept = await _register(api, key, "Phone")
    other = api.another_browser()
    assert (await _sign_in_by_passkey(other, key)).status_code == 200  # by the one kept
    removed = await api.http.delete(f"/api/auth/passkeys/{made['id']}")
    assert (removed.status_code, removed.content) == (204, b"")
    assert (await other.session()).status_code == 401
    assert (await api.session()).status_code == 200
    listed = (await api.http.get("/api/auth/passkeys")).json()["items"]
    assert [item["id"] for item in listed] == [kept["id"]]
    gone = await _sign_in_by_passkey(api.another_browser(), key, credential=key.credentials[0])
    assert _code(gone) == (401, "auth.invalid_passkey")
    still = await _sign_in_by_passkey(api.another_browser(), key, credential=key.credentials[1])
    assert still.status_code == 200  # the control


async def test_removing_a_passkey_voids_a_sign_in_waiting_on_it(api: Api) -> None:
    user, key, made = await _with_a_passkey(api)
    await _register(api, key, "Phone")
    browser, challenge, options = await _passkey_challenge(api, user)
    assert (await api.http.delete(f"/api/auth/passkeys/{made['id']}")).status_code == 204
    voided = await _finish_by_passkey(browser, challenge, key.get(options))
    assert _code(voided) == (401, "auth.challenge_ended")


async def test_a_passkey_is_only_its_owners_to_rename_or_remove(api: Api) -> None:
    _, key, made = await _with_a_passkey(api)
    intruder = api.another_browser()
    await intruder.signed_in_as(await api.make_user())
    path = f"/api/auth/passkeys/{made['id']}"
    renamed = await intruder.http.patch(path, json={"name": "Mine now"})
    assert _code(renamed) == (404, "auth.passkey_not_found")
    removed = await intruder.http.delete(path)
    assert _code(removed) == (404, "auth.passkey_not_found")
    assert (await intruder.http.get("/api/auth/passkeys")).json()["items"] == []
    assert (await _sign_in_by_passkey(api.another_browser(), key)).status_code == 200


async def test_passkey_sign_in_10_per_ip_per_minute(api: Api) -> None:
    starts = [(await api.http.post(PASSKEY_START)).status_code for _ in range(11)]
    assert starts == [200] * 10 + [429]
    options = {"challenge": b64url(bytes(32)), "rpId": api.http.base_url.host}
    key = _key(api)
    key.make(api.http.base_url.host, bytes(16))  # a passkey this site never saw
    finishes = [
        (await api.http.post(PASSKEY_FINISH, json=key.get(options))).status_code for _ in range(11)
    ]
    assert finishes == [401] * 10 + [429]


# Undoing a second factor from its mail (14.7; decision 0030)

UNDO = "/api/auth/second-factor/undo"
UNDO_LINK = "/auth/second-factor/undo"


async def test_a_passkey_added_is_undone_from_its_mail(api: Api) -> None:
    user, key, _ = await _with_a_passkey(api)
    token = await api.new_token(user.email, UNDO_LINK, not_="")
    undone = await api.another_browser().http.post(UNDO, json={"token": token})
    assert _shape(undone) == (200, {"status": "second_factor_undone"})
    assert (await api.session()).status_code == 401  # every session ended
    gone = await _sign_in_by_passkey(api.another_browser(), key)
    assert _code(gone) == (401, "auth.invalid_passkey")
    signed = await api.another_browser().sign_in(user)
    assert signed.json()["status"] == "signed_in"  # no second factor left
    again = await api.http.post(UNDO, json={"token": token})
    assert _code(again) == (400, "auth.token_invalid")


async def test_a_totp_added_is_undone_from_its_mail(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    secret = await _set_up_totp(api)
    assert (await _confirm_totp(api, pyotp.TOTP(secret).now())).status_code == 200
    asked = await api.another_browser().sign_in(user)
    assert asked.json()["status"] == "second_factor"  # the control
    token = await api.new_token(user.email, UNDO_LINK, not_="")
    undone = await api.another_browser().http.post(UNDO, json={"token": token})
    assert _shape(undone) == (200, {"status": "second_factor_undone"})
    assert (await api.session()).status_code == 401
    signed = await api.another_browser().sign_in(user)
    assert signed.json()["status"] == "signed_in"  # the TOTP is gone


async def test_an_undo_link_outlives_the_owners_reset(api: Api) -> None:
    """The gap it closes: a reset leaves a passkey a thief added, and the
    passkey signs in alone. The owner resets, then undoes it."""
    user, key, _ = await _with_a_passkey(api)
    token = await api.new_token(user.email, UNDO_LINK, not_="")
    await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    reset = await api.new_token(user.email, "/auth/reset", not_="")
    done = await api.http.post(
        "/api/auth/password/reset", json={"token": reset, "password": NEW_PASSWORD}
    )
    assert done.status_code == 200
    assert (await _sign_in_by_passkey(api.another_browser(), key)).status_code == 200  # the gap
    undone = await api.another_browser().http.post(UNDO, json={"token": token})
    assert undone.status_code == 200
    gone = await _sign_in_by_passkey(api.another_browser(), key)
    assert _code(gone) == (401, "auth.invalid_passkey")


async def test_each_undo_link_takes_its_own_passkey_and_outlives_the_others(api: Api) -> None:
    """Whoever added two passkeys left two links. The first undo ends every
    session and way in, but takes only its passkey and leaves the second link."""
    user, key, _ = await _with_a_passkey(api)
    first = await api.new_token(user.email, UNDO_LINK, not_="")
    await _register(api, key, "Phone")
    second = await api.new_token(user.email, UNDO_LINK, not_=first)
    assert (await api.another_browser().http.post(UNDO, json={"token": first})).status_code == 200
    first_key, second_key = key.credentials
    gone = await _sign_in_by_passkey(api.another_browser(), key, credential=first_key)
    assert _code(gone) == (401, "auth.invalid_passkey")
    kept = await _sign_in_by_passkey(api.another_browser(), key, credential=second_key)
    assert kept.status_code == 200  # only the first link's passkey went
    assert (await api.another_browser().http.post(UNDO, json={"token": second})).status_code == 200
    also = await _sign_in_by_passkey(api.another_browser(), key, credential=second_key)
    assert _code(also) == (401, "auth.invalid_passkey")


async def test_a_second_factor_undo_link_lasts_7_days(api: Api) -> None:
    user, key, _ = await _with_a_passkey(api)
    early = await api.new_token(user.email, UNDO_LINK, not_="")
    await api.advance(7 * DAY - MINUTE)
    kept = await api.http.post(UNDO, json={"token": early})
    assert kept.status_code == 200  # the control: alive just under 7 days

    await api.signed_in_as(user)
    await _register(api, key, "Phone")
    late = await api.new_token(user.email, UNDO_LINK, not_=early)
    await api.advance(7 * DAY + MINUTE)
    gone = await api.http.post(UNDO, json={"token": late})
    assert _code(gone) == (400, "auth.token_invalid")
