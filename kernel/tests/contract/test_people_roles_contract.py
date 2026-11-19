"""The admin's people and roles (K4 contract §2, additions 4 and 5; SPEC.md
14.1 and 14.8; docs/contracts/auth-api.md, Staff), over HTTP only, like the
rest of the contract suite.

Role editing has a test for each refusal, and one showing that a holder's
next request carries a new session token (K4 contract §7). Each test makes
its own roles, under ids no other test uses: roles outlive a test's accounts.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from .conftest import UNCHECKED, Api, User

USERS = "/api/auth/admin/users"
ROLES = "/api/auth/admin/roles"
AUDIT = "/api/kernel/admin/audit"
ZERO_ID = "00000000-0000-0000-0000-000000000000"
MINUTE = 60


def _code(response: httpx.Response) -> tuple[int, str | None]:
    body = response.json() if response.content else {}
    return response.status_code, body.get("code")


def _role_id() -> str:
    return f"r-{uuid.uuid4().hex[:10]}"


def _role_body(permissions: list[str], **fields: Any) -> dict[str, Any]:
    return {"id": _role_id(), "name": "Helper", "description": "", "permissions": permissions} | (
        fields
    )


async def _as_owner(api: Api) -> User:
    owner = await api.make_user(roles=["owner"], totp=True)
    await api.signed_in_as(owner)
    return owner


async def _new_role(api: Api, permissions: list[str], **fields: Any) -> dict[str, Any]:
    response = await api.http.post(ROLES, json=_role_body(permissions, **fields))
    assert response.status_code == 201, response.text
    role: dict[str, Any] = response.json()
    return role


async def _staff_holding(api: Api, *permissions: str) -> Api:
    """A browser signed in as staff whose one role carries `permissions`,
    the role made by an owner in a browser of its own."""
    owner_side = api.another_browser()
    await _as_owner(owner_side)
    role = await _new_role(owner_side, list(permissions))
    person = await api.make_user(roles=[role["id"]], totp=True)
    staff = api.another_browser()
    await staff.signed_in_as(person)
    return staff


async def _listed(api: Api, user: User) -> dict[str, Any]:
    response = await api.http.get(USERS, params={"q": user.email})
    assert response.status_code == 200, response.text
    found = [item for item in response.json()["items"] if item["id"] == user.id]
    assert len(found) == 1, response.text
    return found[0]


async def _logged(api: Api, kind: str, ident: str) -> list[dict[str, Any]]:
    response = await api.http.get(AUDIT, params={"target_type": kind, "target_id": ident})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# --- People: GET /api/auth/admin/users ------------------------------------------------


async def test_the_people_list_finds_by_address_newest_first_in_pages(api: Api) -> None:
    await _as_owner(api)
    tag = uuid.uuid4().hex[:8]
    made = [await api.make_user(email=f"p{i}-{tag}@site.test") for i in range(3)]
    first = await api.http.get(USERS, params={"q": tag.upper(), "limit": 2})
    assert first.status_code == 200, first.text
    page = first.json()
    assert [item["email"] for item in page["items"]] == [made[2].email, made[1].email]
    assert page["next_cursor"]
    rest = await api.http.get(USERS, params={"q": tag, "limit": 2, "cursor": page["next_cursor"]})
    assert [item["email"] for item in rest.json()["items"]] == [made[0].email]
    assert rest.json()["next_cursor"] is None
    # What's typed is matched as written, never as a pattern.
    wild = await api.http.get(USERS, params={"q": f"p_-{tag}"})
    assert wild.json()["items"] == []


async def test_a_person_as_the_list_gives_them(api: Api) -> None:
    await _as_owner(api)
    member = await api.make_user(totp=True)
    await api.another_browser().signed_in_as(member)
    item = await _listed(api, member)
    assert item == {
        "id": member.id,
        "email": member.email,
        "name": None,
        "roles": ["member"],
        "verified": True,
        "second_factor": True,
        "status": "active",
        "created_at": item["created_at"],
        "last_seen_at": item["last_seen_at"],
    }
    assert item["last_seen_at"] is not None
    fresh = await api.make_user(verified=False)
    item = await _listed(api, fresh)
    assert (item["verified"], item["second_factor"], item["last_seen_at"]) == (False, False, None)


async def test_the_people_list_refuses_a_bad_cursor_or_search(api: Api) -> None:
    await _as_owner(api)
    response = await api.http.get(USERS, params={"cursor": "not-a-page"})
    assert _code(response) == (422, "kernel.invalid_request")
    longest = await api.http.get(USERS, params={"q": "x" * 254})
    assert longest.status_code == 200, longest.text  # the control
    too_long = await api.http.get(USERS, params={"q": "x" * 255})
    assert _code(too_long) == (422, "kernel.invalid_request")


async def test_the_people_list_needs_its_permission(api: Api) -> None:
    staff = await _staff_holding(api, "auth.audit.read")
    assert _code(await staff.http.get(USERS)) == (403, "kernel.forbidden")
    assert _code(await staff.http.get(ROLES)) == (403, "kernel.forbidden")


# --- Granting and removing: PUT /api/auth/admin/users/{id}/roles --------------------------


async def test_changing_roles_answers_the_person_and_is_logged(api: Api) -> None:
    await _as_owner(api)
    member = await api.make_user()
    response = await api.http.put(
        f"{USERS}/{member.id}/roles", json={"roles": ["member", "editor"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["roles"] == ["editor", "member"]
    assert response.json()["id"] == member.id
    again = await api.http.put(f"{USERS}/{member.id}/roles", json={"roles": ["editor"]})
    assert again.json()["roles"] == ["editor"]
    logged = await _logged(api, "auth.user", member.id)
    assert [(e["action"], e["details"]) for e in logged] == [
        ("auth.user.roles_changed", {"added": [], "removed": ["member"]}),
        ("auth.user.roles_changed", {"added": ["editor"], "removed": []}),
    ]


async def test_only_a_role_you_hold_all_of_is_granted_or_removed(api: Api) -> None:
    staff = await _staff_holding(api, "auth.user.manage", "auth.role.assign")
    member = await api.make_user()
    admin = await api.make_user(roles=["member", "admin"])
    grant = await staff.http.put(f"{USERS}/{member.id}/roles", json={"roles": ["admin"]})
    assert _code(grant) == (403, "auth.role_not_yours")
    remove = await staff.http.put(f"{USERS}/{admin.id}/roles", json={"roles": ["member"]})
    assert _code(remove) == (403, "auth.role_not_yours")
    # The control: a role within what they hold goes through, and a role they
    # couldn't grant may stay where it is, since only what changes is judged.
    owner_side = api.another_browser()
    await _as_owner(owner_side)
    small = await _new_role(owner_side, ["auth.user.manage"])
    kept = await staff.http.put(
        f"{USERS}/{admin.id}/roles", json={"roles": ["member", "admin", small["id"]]}
    )
    assert kept.status_code == 200, kept.text
    assert sorted(kept.json()["roles"]) == sorted(["member", "admin", small["id"]])


async def test_an_unknown_role_or_person_is_refused(api: Api) -> None:
    await _as_owner(api)
    member = await api.make_user()
    unknown = await api.http.put(
        f"{USERS}/{member.id}/roles", json={"roles": ["member", _role_id()]}
    )
    assert _code(unknown) == (422, "auth.role_unknown")
    nobody = await api.http.put(
        f"{USERS}/{ZERO_ID}/roles", json={"roles": ["member"]}, extensions=UNCHECKED
    )
    assert _code(nobody) == (404, "kernel.not_found")


# --- The roles read: GET /api/auth/admin/roles ---------------------------------------


async def test_the_roles_read_gives_every_role_and_permission(api: Api) -> None:
    await _as_owner(api)
    role = await _new_role(api, ["auth.user.manage"], name="Helper", description="Helps out")
    await api.make_user(roles=[role["id"]])
    response = await api.http.get(ROLES)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["id"] for r in body["roles"]][:4] == ["owner", "admin", "editor", "member"]
    roles = {r["id"]: r for r in body["roles"]}
    declared = [p["key"] for p in body["permissions"]]
    assert len(declared) == len(set(declared))
    assert {"auth.user.manage", "auth.role.assign", "auth.role.manage"} <= set(declared)
    kernels = [p for p in body["permissions"] if p["key"].split(".")[0] in {"auth", "kernel"}]
    assert {p["owner"] for p in kernels} == {"kernel"}
    assert all(isinstance(p["description"], str) and p["description"] for p in kernels)
    assert sorted(roles["owner"]["permissions"]) == sorted(declared)
    assert roles["owner"]["builtin"]
    assert roles["member"]["builtin"]
    assert roles["owner"]["people"] >= 1
    assert "auth.role.manage" in roles["admin"]["permissions"]  # kernel_0012's grant
    assert "auth.role.manage" not in roles["editor"]["permissions"]
    assert roles[role["id"]] == {
        "id": role["id"],
        "name": "Helper",
        "description": "Helps out",
        "permissions": ["auth.user.manage"],
        "people": 1,
        "builtin": False,
    }


# --- Editing roles: POST, PUT and DELETE /api/auth/admin/roles ------------------------


async def test_a_role_is_made_changed_and_deleted_and_each_is_logged(api: Api) -> None:
    await _as_owner(api)
    body = _role_body(["auth.user.manage", "auth.audit.read"], name="Helper")
    made = await api.http.post(ROLES, json=body)
    assert made.status_code == 201, made.text
    role = made.json()
    assert role == {
        "id": body["id"],
        "name": "Helper",
        "description": "",
        "permissions": ["auth.audit.read", "auth.user.manage"],
        "people": 0,
        "builtin": False,
    }
    changed = await api.http.put(
        f"{ROLES}/{role['id']}",
        json={"name": "Aide", "description": "Reads the log", "permissions": ["auth.audit.read"]},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json() == role | {
        "name": "Aide",
        "description": "Reads the log",
        "permissions": ["auth.audit.read"],
    }
    deleted = await api.http.delete(f"{ROLES}/{role['id']}")
    assert deleted.status_code == 204, deleted.text
    assert role["id"] not in [r["id"] for r in (await api.http.get(ROLES)).json()["roles"]]
    logged = await _logged(api, "auth.role", role["id"])
    assert [(e["action"], e["details"]) for e in logged] == [
        ("auth.role.deleted", {}),
        ("auth.role.changed", {"added": [], "removed": ["auth.user.manage"]}),
        ("auth.role.created", {"permissions": ["auth.audit.read", "auth.user.manage"]}),
    ]


async def test_a_holders_next_request_carries_a_new_token(api: Api) -> None:
    await _as_owner(api)
    role = await _new_role(api, ["auth.user.manage"])
    holder = await api.make_user(roles=[role["id"]], totp=True)
    side = api.another_browser()
    await side.signed_in_as(holder)
    assert "auth.user.manage" in (await side.session()).json()["user"]["permissions"]
    before = side.session_cookie
    assert before
    changed = await api.http.put(
        f"{ROLES}/{role['id']}",
        json={"name": "Helper", "description": "", "permissions": ["auth.audit.read"]},
    )
    assert changed.status_code == 200, changed.text
    session = await side.session()
    assert session.status_code == 200
    assert side.session_cookie not in {None, before}
    assert "auth.audit.read" in session.json()["user"]["permissions"]
    assert "auth.user.manage" not in session.json()["user"]["permissions"]
    stale = api.another_browser()
    stale.plant_cookie("__Host-mf_session", before)
    assert (await stale.session()).status_code == 401


async def test_a_permission_you_dont_hold_is_refused(api: Api) -> None:
    staff = await _staff_holding(api, "auth.user.manage", "auth.role.manage")
    refused = await staff.http.post(ROLES, json=_role_body(["auth.audit.read"]))
    assert _code(refused) == (403, "auth.role_not_yours")
    mine = await staff.http.post(ROLES, json=_role_body(["auth.user.manage"]))
    assert mine.status_code == 201, mine.text  # the control
    grown = await staff.http.put(
        f"{ROLES}/{mine.json()['id']}",
        json={"name": "Helper", "description": "", "permissions": ["auth.audit.read"]},
    )
    assert _code(grown) == (403, "auth.role_not_yours")
    owner_side = api.another_browser()
    await _as_owner(owner_side)
    theirs = await _new_role(owner_side, ["auth.user.manage", "auth.audit.read"])
    renamed = await staff.http.put(
        f"{ROLES}/{theirs['id']}",
        json={"name": "Renamed", "description": "", "permissions": ["auth.user.manage"]},
    )
    assert _code(renamed) == (403, "auth.role_not_yours")
    assert _code(await staff.http.delete(f"{ROLES}/{theirs['id']}")) == (403, "auth.role_not_yours")


async def test_an_unknown_permission_is_refused(api: Api) -> None:
    await _as_owner(api)
    made = await api.http.post(ROLES, json=_role_body(["nobody.thing.do"]))
    assert _code(made) == (422, "auth.permission_unknown")
    role = await _new_role(api, [])
    changed = await api.http.put(
        f"{ROLES}/{role['id']}",
        json={"name": "Helper", "description": "", "permissions": ["nobody.thing.do"]},
    )
    assert _code(changed) == (422, "auth.permission_unknown")


async def test_an_id_taken_is_refused(api: Api) -> None:
    await _as_owner(api)
    body = _role_body([])
    assert (await api.http.post(ROLES, json=body)).status_code == 201
    assert _code(await api.http.post(ROLES, json=body)) == (409, "auth.role_exists")
    builtin = await api.http.post(ROLES, json=_role_body([], id="admin"))
    assert _code(builtin) == (409, "auth.role_exists")


@pytest.mark.parametrize("bad", ["Helper", "a", "9lives", "under_score", "x" * 65])
async def test_an_id_out_of_pattern_is_refused(api: Api, bad: str) -> None:
    await _as_owner(api)
    made = await api.http.post(ROLES, json=_role_body([], id=bad))
    assert _code(made) == (422, "kernel.invalid_request")


async def test_the_built_in_roles_stay_as_declared(api: Api) -> None:
    await _as_owner(api)
    for role in ("owner", "admin", "editor", "member"):
        changed = await api.http.put(
            f"{ROLES}/{role}", json={"name": "Mine", "description": "", "permissions": []}
        )
        assert _code(changed) == (409, "auth.role_builtin"), role
        assert _code(await api.http.delete(f"{ROLES}/{role}")) == (409, "auth.role_builtin")


async def test_a_role_someone_holds_isnt_deleted(api: Api) -> None:
    await _as_owner(api)
    role = await _new_role(api, [])
    holder = await api.make_user(roles=["member", role["id"]])
    assert _code(await api.http.delete(f"{ROLES}/{role['id']}")) == (409, "auth.role_in_use")
    removed = await api.http.put(f"{USERS}/{holder.id}/roles", json={"roles": ["member"]})
    assert removed.status_code == 200, removed.text
    assert (await api.http.delete(f"{ROLES}/{role['id']}")).status_code == 204  # the control


async def test_an_unknown_role_isnt_found(api: Api) -> None:
    await _as_owner(api)
    missing = f"{ROLES}/{_role_id()}"
    changed = await api.http.put(
        missing, json={"name": "Helper", "description": "", "permissions": []}
    )
    assert _code(changed) == (404, "auth.role_not_found")
    assert _code(await api.http.delete(missing)) == (404, "auth.role_not_found")


async def test_editing_roles_needs_its_permission(api: Api) -> None:
    staff = await _staff_holding(api, "auth.user.manage")
    assert _code(await staff.http.post(ROLES, json=_role_body([]))) == (403, "kernel.forbidden")


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
async def test_editing_roles_demands_a_recent_sign_in(api: Api, method: str) -> None:
    await _as_owner(api)
    role = await _new_role(api, [])
    await api.advance(11 * MINUTE)
    path, body = {
        "POST": (ROLES, _role_body([])),
        "PUT": (f"{ROLES}/{role['id']}", {"name": "Helper", "description": "", "permissions": []}),
        "DELETE": (f"{ROLES}/{role['id']}", None),
    }[method]
    response = await api.http.request(method, path, json=body)
    assert _code(response) == (403, "auth.step_up_required")


async def test_a_role_written_from_another_origin_is_refused(api: Api) -> None:
    """A forged page can't make a role or grant one with an owner's cookie
    (SPEC 14.5's Origin check, on the routes that hand out permissions)."""
    await _as_owner(api)
    member = await api.make_user()
    forged = {"Origin": "https://evil.test", "Sec-Fetch-Site": "cross-site"}
    body = _role_body(["auth.audit.read"])
    made = await api.http.post(ROLES, json=body, headers=forged)
    assert _code(made) == (403, "kernel.cross_site_write")
    granted = await api.http.put(
        f"{USERS}/{member.id}/roles", json={"roles": ["admin"]}, headers=forged
    )
    assert _code(granted) == (403, "kernel.cross_site_write")
    roles = (await api.http.get(ROLES)).json()["roles"]
    assert body["id"] not in [r["id"] for r in roles]
    assert (await _listed(api, member))["roles"] == ["member"]
