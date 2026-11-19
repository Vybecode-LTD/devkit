// The admin's People (K4.7): everyone with an account, found by address,
// fifty at a time, and a person's roles changed within what you may grant.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import type { components } from "../api/schema";
import { problem, routedFetch, type Answer } from "../test-fetch";
import { roleName, roleWords, whyNotGrant } from "./roleAccess";

type Person = components["schemas"]["Person"];
type RoleView = components["schemas"]["RoleView"];

beforeAll(async () => {
  await import("./People");
});

const ADMIN_HOLDS = ["auth.user.manage", "auth.role.assign", "auth.audit.read"];
const admin = testUser({ roles: ["member", "admin"], second_factor: true, permissions: ADMIN_HOLDS });

const ROLES: RoleView[] = [
  { id: "owner", name: "Owner", description: "", permissions: ["auth.audit.read", "auth.role.assign", "auth.user.manage", "kernel.jobs.manage"], people: 1, builtin: true },
  { id: "admin", name: "Admin", description: "", permissions: ADMIN_HOLDS, people: 1, builtin: true },
  { id: "editor", name: "Editor", description: "Content", permissions: [], people: 0, builtin: true },
  { id: "member", name: "Member", description: "", permissions: [], people: 3, builtin: true },
  { id: "jobs-crew", name: "Jobs crew", description: "Retries jobs", permissions: ["kernel.jobs.manage"], people: 0, builtin: false },
];

function person(id: string, fields: Partial<Person>): Person {
  return {
    id: `00000000-0000-4000-8000-0000000000${id}`,
    email: `${id}@site.test`,
    name: null,
    roles: ["member"],
    verified: true,
    second_factor: false,
    status: "active",
    created_at: "2026-11-01T10:00:00Z",
    last_seen_at: "2026-11-18T10:00:00Z",
    ...fields,
  };
}

const ANN = person("a1", { name: "Ann Example", roles: ["admin", "member"], second_factor: true });
const BO = person("b2", { roles: ["editor"] });
const CY = person("c3", { verified: false, last_seen_at: null });
const DI = person("d4", { status: "suspended" });

function page(items: Person[], next: string | null = null): Answer {
  return { status: 200, body: { items, next_cursor: next } };
}

const BASE = {
  "GET /api/kernel/notifications": { status: 200, body: { items: [], next_cursor: null, unread: 0 } },
  "GET /api/auth/admin/roles": { status: 200, body: { roles: ROLES, permissions: [] } },
};

async function opened(session = admin) {
  renderApp({ path: "/admin/people", session });
  await screen.findByRole("heading", { level: 1, name: "People" });
  return within(await screen.findByRole("table", { name: "People, newest first" }));
}

describe("the people list", () => {
  it("names each person's roles, second factor, last visit and standing", async () => {
    routedFetch({ ...BASE, "GET /api/auth/admin/users": page([ANN, BO, CY, DI]) });
    const table = await opened();
    await table.findAllByRole("button", { name: /^Open / });
    const rows = table.getAllByRole("row").slice(1);
    const cells = rows.map((row) =>
      within(row)
        .getAllByRole("cell")
        .filter((_, index) => index !== 3)
        .slice(0, 4)
        .map((cell) => cell.textContent),
    );
    expect(cells).toEqual([
      ["Ann Examplea1@site.test", "Admin", "On", "Active"],
      ["b2@site.test", "Editor", "Not set up", "Active"],
      ["c3@site.test", "Member", "Off", "Email not confirmed"],
      ["d4@site.test", "Member", "Off", "Suspended"],
    ]);
    expect(within(rows[2] as HTMLElement).getByText("Never")).toBeInTheDocument();
    expect(rows[0]?.querySelector("time")).toHaveAttribute("dateTime", "2026-11-18T10:00:00Z");
  });

  it("finds people by address once typing rests, and shows more on asking", async () => {
    const { sent } = routedFetch({
      ...BASE,
      "GET /api/auth/admin/users": (request) => {
        const query = new URL(request.url).searchParams;
        if (query.get("q") === "bo") return page([BO]);
        return query.get("cursor") === "next" ? page([CY]) : page([ANN], "next");
      },
    });
    const table = await opened();
    await userEvent.click(screen.getByRole("button", { name: "Show more" }));
    await table.findByText("c3@site.test");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search by email" }), "bo");
    const found = within(await screen.findByRole("table", { name: 'People whose email holds "bo", newest first' }));
    expect(found.getByText("b2@site.test")).toBeInTheDocument();
    const asked = sent.filter((request) => request.url.includes("/api/auth/admin/users")).map((r) => new URL(r.url).search);
    expect(asked).toEqual(["", "?cursor=next", "?q=bo"]);
  });

  it("offers another try when the list can't be read", async () => {
    routedFetch({ ...BASE, "GET /api/auth/admin/users": problem(500, "kernel.internal_error") });
    renderApp({ path: "/admin/people", session: admin });
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("offers no Open without auth.role.assign", async () => {
    routedFetch({ ...BASE, "GET /api/auth/admin/users": page([ANN]) });
    const reader = testUser({ roles: ["member", "helper"], second_factor: true, permissions: ["auth.user.manage"] });
    const table = await opened(reader);
    await table.findByText("Admin");
    expect(table.queryByRole("button", { name: /^Open / })).toBeNull();
  });
});

describe("a person's roles", () => {
  it("are switched on and saved, a role you couldn't grant left as it is with its reason", async () => {
    const { sent } = routedFetch({
      ...BASE,
      "GET /api/auth/admin/users": page([BO]),
      "PUT /api/auth/admin/users/00000000-0000-4000-8000-0000000000b2/roles": { status: 200, body: { ...BO, roles: ["editor", "member"] } },
    });
    const table = await opened();
    await userEvent.click(await table.findByRole("button", { name: "Open b2@site.test" }));
    const dialog = within(await screen.findByRole("dialog", { name: "b2@site.test" }));
    expect(dialog.getByRole("switch", { name: /^Owner/ })).toBeDisabled();
    expect(dialog.getByText("Only an owner grants or removes it.")).toBeInTheDocument();
    expect(dialog.getByRole("switch", { name: /^Jobs crew/ })).toBeDisabled();
    expect(dialog.getByRole("switch", { name: /^Editor/ })).toBeChecked();
    expect(dialog.getByRole("button", { name: "Save roles" })).toBeDisabled();
    await userEvent.click(dialog.getByRole("switch", { name: /^Member/ }));
    await userEvent.click(dialog.getByRole("button", { name: "Save roles" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    const put = sent.find((request) => request.method === "PUT");
    expect(await put?.json()).toEqual({ roles: ["editor", "member"] });
    expect(await screen.findByText("Saved b2@site.test's roles.")).toBeInTheDocument();
  });

  it("says why the server refused, and stays open", async () => {
    routedFetch({
      ...BASE,
      "GET /api/auth/admin/users": page([ANN]),
      "PUT /api/auth/admin/users/00000000-0000-4000-8000-0000000000a1/roles": problem(409, "auth.last_owner"),
    });
    const table = await opened();
    await userEvent.click(await table.findByRole("button", { name: "Open Ann Example" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Ann Example" }));
    await userEvent.click(dialog.getByRole("switch", { name: /^Admin/ }));
    await userEvent.click(dialog.getByRole("button", { name: "Save roles" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent("The site's last owner stays an owner.");
  });
});

describe("role words", () => {
  it("leaves a member's role out of a row beside any other", async () => {
    const { shownRoles } = await import("./People");
    expect(shownRoles(["admin", "member"])).toEqual(["admin"]);
    expect(shownRoles(["member"])).toEqual(["member"]);
    expect(shownRoles([])).toEqual([]);
  });

  it("names a role from the roles read, or from its id without it", () => {
    expect(roleName("jobs-crew", ROLES)).toBe("Jobs crew");
    expect(roleName("beat-makers")).toBe("Beat makers");
    expect(roleWords(["member", "jobs-crew"], ROLES)).toBe("Jobs crew");
    expect(roleWords(["member"])).toBe("Member");
  });

  it("says ahead what the server will refuse to grant", () => {
    const held = new Set(ADMIN_HOLDS);
    const [owner, adminRole, , member, crew] = ROLES as [RoleView, RoleView, RoleView, RoleView, RoleView];
    expect(whyNotGrant(owner, held, false)).toBe("Only an owner grants or removes it.");
    expect(whyNotGrant(adminRole, held, false)).toBeNull();
    expect(whyNotGrant({ ...member, permissions: ["shop.order.manage"] }, held, false)).toBeNull();
    expect(whyNotGrant(crew, held, false)).toBe("It carries permissions you don't hold.");
    expect(whyNotGrant(crew, held, true)).toBeNull();
  });
});
