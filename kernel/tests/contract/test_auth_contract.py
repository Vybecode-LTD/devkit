"""The auth contract suite: one test per line of SPEC.md 14.13.

HTTP only (docs/contracts/auth-api.md); nothing here imports the kernel.
Written before auth exists, as KICKOFF.md K2 step 1 asks: every test is an
expected failure until the code it describes lands, and `strict` turns a
pass into a failure until its mark is removed.
"""

from __future__ import annotations

import time

import pyotp
import pytest

from .conftest import PASSWORD, Api, code_in, token_in

pytestmark = pytest.mark.xfail(reason="K2: auth isn't built yet", strict=True)

UNKNOWN = "nobody-here@site.test"


def _shape(response: object) -> tuple[int, object]:
    status = response.status_code  # type: ignore[attr-defined]
    body = response.json() if response.content else None  # type: ignore[attr-defined]
    if isinstance(body, dict):
        body = {key: value for key, value in body.items() if key not in {"instance"}}
    return status, body


# 1. Sign-in, sign-up and reset answer the same for a known and an unknown email


async def test_sign_in_answers_the_same_for_known_and_unknown(api: Api) -> None:
    user = await api.make_user()
    known = await api.http.post(
        "/api/auth/sign-in", json={"email": user.email, "password": "wrong password!"}
    )
    unknown = await api.http.post(
        "/api/auth/sign-in", json={"email": UNKNOWN, "password": "wrong password!"}
    )
    assert _shape(known) == _shape(unknown)
    assert known.status_code == 401
    assert known.json()["code"] == "auth.invalid_credentials"


async def test_sign_up_answers_the_same_for_known_and_unknown(api: Api) -> None:
    user = await api.make_user()
    known = await api.http.post(
        "/api/auth/sign-up", json={"email": user.email, "password": PASSWORD}
    )
    unknown = await api.http.post(
        "/api/auth/sign-up", json={"email": UNKNOWN, "password": PASSWORD}
    )
    assert _shape(known) == _shape(unknown) == (202, {"status": "check_email"})


async def test_reset_answers_the_same_for_known_and_unknown(api: Api) -> None:
    user = await api.make_user()
    known = await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    unknown = await api.http.post("/api/auth/password/reset-request", json={"email": UNKNOWN})
    assert _shape(known) == _shape(unknown) == (202, {"status": "check_email"})


async def test_a_missing_account_still_costs_a_hash(api: Api) -> None:
    """Similar time: an unknown email isn't answered in a fraction of a known one's time."""
    user = await api.make_user()
    timings = {}
    for email in (user.email, UNKNOWN):
        start = time.perf_counter()
        for _ in range(3):
            await api.http.post(
                "/api/auth/sign-in", json={"email": email, "password": "wrong password!"}
            )
        timings[email] = time.perf_counter() - start
    assert timings[UNKNOWN] > timings[user.email] * 0.5


# 2. A reset, code or link token works once, and never after it expires


async def test_a_reset_token_works_once(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/reset")
    new = "a brand new passphrase"
    first = await api.http.post("/api/auth/password/reset", json={"token": token, "password": new})
    again = await api.http.post(
        "/api/auth/password/reset", json={"token": token, "password": new + "!"}
    )
    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (400, "auth.token_invalid")


async def test_a_reset_token_expires_after_30_minutes(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/reset")
    await api.advance(31 * 60)
    late = await api.http.post(
        "/api/auth/password/reset", json={"token": token, "password": "too late now!!"}
    )
    assert (late.status_code, late.json()["code"]) == (400, "auth.token_invalid")


async def test_a_sign_in_code_works_once_and_expires(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    code = code_in((await api.last_mail(user.email))["text"])
    first = await api.http.post("/api/auth/code/verify", json={"email": user.email, "code": code})
    again = await api.another_browser().http.post(
        "/api/auth/code/verify", json={"email": user.email, "code": code}
    )
    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (401, "auth.invalid_code")

    await api.http.post("/api/auth/code", json={"email": user.email})
    late_code = code_in((await api.last_mail(user.email))["text"])
    await api.advance(11 * 60)
    late = await api.http.post(
        "/api/auth/code/verify", json={"email": user.email, "code": late_code}
    )
    assert late.status_code == 401


async def test_a_magic_link_works_once_and_expires(api: Api) -> None:
    user = await api.make_user()
    await api.http.post("/api/auth/code", json={"email": user.email})
    token = token_in((await api.last_mail(user.email))["text"], "/auth/link")
    first = await api.http.post("/api/auth/link/confirm", json={"token": token})
    again = await api.http.post("/api/auth/link/confirm", json={"token": token})
    assert first.status_code == 200
    assert (again.status_code, again.json()["code"]) == (401, "auth.invalid_link")


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
        response = await scanner.http.get(path)
        assert "__Host-dk_session" not in response.headers.get("set-cookie", "")
    assert (await scanner.session()).status_code == 401
    # The scanner used nothing up: the person's own click still works.
    assert (await api.http.post("/api/auth/link/confirm", json={"token": token})).status_code == 200


# 4. A TOTP code can't be replayed within its step


async def test_a_totp_code_cant_be_replayed(api: Api) -> None:
    user = await api.make_user(totp=True)
    totp = pyotp.TOTP(user.totp_secret)
    code = totp.now()
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


async def test_staff_without_a_second_factor_reach_no_admin_route(api: Api) -> None:
    admin = await api.make_user(roles=["admin"])
    await api.signed_in_as(admin)
    routes = (await api.http.get("/api/_test/routes")).json()["admin"]
    assert "/api/auth/admin/users" in routes
    for path in routes:
        response = await api.http.get(path)
        assert (response.status_code, response.json()["code"]) == (
            403,
            "auth.second_factor_required",
        ), path


async def test_staff_with_a_second_factor_reach_the_admin(api: Api) -> None:
    admin = await api.make_user(roles=["admin"], totp=True)
    await api.signed_in_as(admin)
    assert (await api.http.get("/api/auth/admin/users")).status_code == 200


# 6. Every action listed under step-up (14.4) demands it

STEP_UP = [
    (
        "POST",
        "/api/auth/password/change",
        {"current_password": PASSWORD, "new_password": "another long one!"},
    ),
    ("POST", "/api/auth/email/change", {"email": "new-address@site.test"}),
    ("POST", "/api/auth/totp/setup", None),
    ("DELETE", "/api/auth/totp", None),
    ("POST", "/api/auth/recovery-codes", None),
    ("POST", "/api/auth/passkeys/register/start", {"name": "Laptop"}),
    ("DELETE", "/api/auth/passkeys/00000000-0000-0000-0000-000000000000", None),
    ("POST", "/api/auth/api-keys", {"name": "CI", "scopes": []}),
    ("POST", "/api/auth/account/delete", None),
]


@pytest.mark.parametrize(
    ("method", "path", "body"), STEP_UP, ids=[f"{m} {p}" for m, p, _ in STEP_UP]
)
async def test_step_up_actions_demand_a_recent_sign_in(
    api: Api, method: str, path: str, body: dict[str, str] | None
) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.advance(11 * 60)
    response = await api.http.request(method, path, json=body)
    assert (response.status_code, response.json()["code"]) == (403, "auth.step_up_required")


async def test_changing_roles_demands_a_recent_sign_in(api: Api) -> None:
    owner = await api.make_user(roles=["owner"], totp=True)
    member = await api.make_user()
    await api.signed_in_as(owner)
    await api.advance(11 * 60)
    response = await api.http.put(
        f"/api/auth/admin/users/{member.id}/roles", json={"roles": ["editor"]}
    )
    assert (response.status_code, response.json()["code"]) == (403, "auth.step_up_required")


async def test_stepping_up_lets_the_action_through(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.advance(11 * 60)
    assert (
        await api.http.post("/api/auth/step-up", json={"password": PASSWORD})
    ).status_code == 200
    assert (await api.http.post("/api/auth/recovery-codes")).status_code in {200, 409}


# 7. A password change ends every other session


async def test_a_password_change_ends_every_other_session(api: Api) -> None:
    user = await api.make_user()
    other = api.another_browser()
    await api.signed_in_as(user)
    await other.signed_in_as(user)
    new = "a different passphrase"
    response = await api.http.post(
        "/api/auth/password/change", json={"current_password": PASSWORD, "new_password": new}
    )
    assert response.status_code == 200
    assert (await api.session()).status_code == 200
    assert (await other.session()).status_code == 401


# 8. A provider identity with an unverified email never links automatically


async def test_an_unverified_provider_email_never_links(api: Api) -> None:
    user = await api.make_user()
    grant = await api.http.post(
        "/api/_test/oauth/grant",
        json={"provider": "test", "subject": "sub-1", "email": user.email, "email_verified": False},
    )
    start = await api.http.get("/api/auth/oauth/test/start", params={"next": "/account"})
    state = httpx_param(start.headers["location"], "state")
    callback = await api.http.get(
        "/api/auth/oauth/test/callback", params={"code": grant.json()["code"], "state": state}
    )
    assert callback.status_code == 302
    assert (await api.session()).status_code == 401  # not signed in as the existing account


async def test_a_verified_provider_email_links_to_a_verified_account(api: Api) -> None:
    user = await api.make_user()
    grant = await api.http.post(
        "/api/_test/oauth/grant",
        json={"provider": "test", "subject": "sub-2", "email": user.email, "email_verified": True},
    )
    start = await api.http.get("/api/auth/oauth/test/start", params={"next": "/account"})
    state = httpx_param(start.headers["location"], "state")
    callback = await api.http.get(
        "/api/auth/oauth/test/callback", params={"code": grant.json()["code"], "state": state}
    )
    assert callback.status_code == 302
    assert (await api.session()).json()["user"]["id"] == user.id


# 9. An OAuth callback with a wrong or missing state is refused


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


# 10. A state-changing request from another origin is refused


@pytest.mark.parametrize(
    "headers",
    [{"Origin": "https://evil.test"}, {"Sec-Fetch-Site": "cross-site"}],
)
async def test_a_write_from_another_origin_is_refused(api: Api, headers: dict[str, str]) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    forged = {"Origin": api.http.headers["Origin"], "Sec-Fetch-Site": "same-origin", **headers}
    response = await api.http.post("/api/auth/sign-out", headers=forged)
    assert (response.status_code, response.json()["code"]) == (403, "kernel.cross_site_write")
    assert (await api.session()).status_code == 200


# 11. The session token changes at sign-in and on a role change


async def test_the_token_changes_at_sign_in(api: Api) -> None:
    user = await api.make_user()
    api.http.cookies.set("__Host-dk_session", "planted-by-an-attacker", domain="devkit.test")
    await api.signed_in_as(user)
    assert api.session_cookie not in {None, "planted-by-an-attacker"}
    first = api.session_cookie
    await api.http.post("/api/auth/sign-out")
    await api.signed_in_as(user)
    assert api.session_cookie != first


async def test_the_token_changes_on_a_role_change(api: Api) -> None:
    owner = await api.make_user(roles=["owner"], totp=True)
    member = await api.make_user()
    staff_side, member_side = api, api.another_browser()
    await staff_side.signed_in_as(owner)
    await member_side.signed_in_as(member)
    before = member_side.session_cookie
    response = await staff_side.http.put(
        f"/api/auth/admin/users/{member.id}/roles", json={"roles": ["editor"]}
    )
    assert response.status_code == 200
    after_request = await member_side.session()
    assert after_request.status_code == 200
    assert member_side.session_cookie not in {None, before}
    stale = api.another_browser()
    stale.http.cookies.set("__Host-dk_session", before or "", domain="devkit.test")
    assert (await stale.session()).status_code == 401


# 12. Each rate limit in 14.6 triggers at its threshold


async def test_password_sign_in_10_per_ip_per_minute(api: Api) -> None:
    codes = [
        (
            await api.http.post(
                "/api/auth/sign-in",
                json={"email": f"n{i}@site.test", "password": "wrong password!"},
            )
        ).status_code
        for i in range(11)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


async def test_five_failures_on_one_account_slow_it_down(api: Api) -> None:
    user = await api.make_user()
    browsers = [api.another_browser() for _ in range(6)]
    codes = [(await b.sign_in(user, "wrong password!")).status_code for b in browsers]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    refused = await api.sign_in(user)  # even the right password waits
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) >= 1


async def test_codes_3_per_email_per_15_minutes(api: Api) -> None:
    user = await api.make_user()
    for _ in range(3):
        await api.http.post("/api/auth/code", json={"email": user.email})
        await api.advance(61)  # past the resend wait
    assert len(await api.mail(user.email)) == 3
    fourth = await api.http.post("/api/auth/code", json={"email": user.email})
    assert fourth.status_code == 429


async def test_codes_10_per_ip_per_hour(api: Api) -> None:
    codes = [
        (await api.http.post("/api/auth/code", json={"email": f"c{i}@site.test"})).status_code
        for i in range(11)
    ]
    assert codes[:10] == [202] * 10
    assert codes[10] == 429


async def test_resets_are_limited_as_codes_are(api: Api) -> None:
    user = await api.make_user()
    for _ in range(3):
        await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
        await api.advance(61)
    fourth = await api.http.post("/api/auth/password/reset-request", json={"email": user.email})
    assert fourth.status_code == 429


async def test_sign_up_5_per_ip_per_hour(api: Api) -> None:
    codes = [
        (
            await api.http.post(
                "/api/auth/sign-up", json={"email": f"s{i}@site.test", "password": PASSWORD}
            )
        ).status_code
        for i in range(6)
    ]
    assert codes[:5] == [202] * 5
    assert codes[5] == 429


async def test_five_second_factor_failures_end_the_sign_in(api: Api) -> None:
    user = await api.make_user(totp=True)
    challenge = (await api.sign_in(user)).json()["challenge"]
    for _ in range(5):
        wrong = await api.http.post(
            "/api/auth/sign-in/second-factor", json={"challenge": challenge, "totp": "000000"}
        )
        assert wrong.status_code == 401
    right = pyotp.TOTP(user.totp_secret).now()
    ended = await api.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, "totp": right}
    )
    assert (ended.status_code, ended.json()["code"]) == (401, "auth.challenge_ended")


# 13. A route with no declared access fails the route audit: test_route_audit_contract.py


# 14. Deleting an account runs every module's delete hook


async def test_deleting_an_account_runs_every_delete_hook(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    scheduled = await api.http.post("/api/auth/account/delete")
    assert (scheduled.status_code, scheduled.json()["status"]) == (202, "deletion_scheduled")
    await api.advance(14 * 24 * 3600 + 60)
    await api.run_jobs()
    assert user.id in (await api.http.get("/api/_test/delete-hooks")).json()["deleted"]
    assert (await api.sign_in(user)).status_code == 401


async def test_signing_in_cancels_a_deletion(api: Api) -> None:
    user = await api.make_user()
    await api.signed_in_as(user)
    await api.http.post("/api/auth/account/delete")
    await api.advance(3 * 24 * 3600)
    await api.another_browser().signed_in_as(user)
    await api.advance(12 * 24 * 3600)
    await api.run_jobs()
    assert user.id not in (await api.http.get("/api/_test/delete-hooks")).json()["deleted"]


def httpx_param(url: str, name: str) -> str:
    from urllib.parse import parse_qs, urlsplit

    values = parse_qs(urlsplit(url).query).get(name)
    assert values, f"no {name} in {url}"
    return values[0]
