// The admin's Roles (K4.7): each role with how many hold it, the permissions
// in groups against the roles, and the site's own roles made, changed and
// deleted within the permissions you hold.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import type { components } from "../api/schema";
import { problem, routedFetch } from "../test-fetch";
import { permissionGroups } from "./roleAccess";
import { idFrom } from "./Roles";

type RoleView = components["schemas"]["RoleView"];
type PermissionView = components["schemas"]["PermissionView"];

beforeAll(async () => {
  await import("./Roles");
});

const PERMISSIONS: PermissionView[] = [
  { key: "auth.user.manage", description: "See and edit people's accounts", owner: "kernel" },
  { key: "auth.role.manage", description: "Create, edit and delete roles, within the permissions you hold", owner: "kernel" },
  { key: "kernel.jobs.manage", description: "Retry and discard failed background jobs", owner: "kernel" },
  { key: "kernel.moderation.act", description: "Act on moderation reports", owner: "kernel" },
  { key: "beat-store.tier.manage", description: "License tiers and prices", owner: "beat-store" },
];
const EVERY = PERMISSIONS.map((permission) => permission.key);
const ADMIN_HOLDS = ["auth.user.manage", "auth.role.manage", "kernel.moderation.act"];

const CREW: RoleView = { id: "crew", name: "Crew", description: "Moderates", permissions: ["kernel.moderation.act"], people: 0, builtin: false };
const ROLES: RoleView[] = [
  { id: "owner", name: "Owner", description: "", permissions: EVERY, people: 1, builtin: true },
  { id: "admin", name: "Admin", description: "Runs the site", permissions: ADMIN_HOLDS, people: 2, builtin: true },
  { id: "member", name: "Member", description: "", permissions: [], people: 37, builtin: true },
  CREW,
];

const admin = testUser({ roles: ["member", "admin"], second_factor: true, permissions: ADMIN_HOLDS });

const BASE = {
  "GET /api/kernel/notifications": { status: 200, body: { items: [], next_cursor: null, unread: 0 } },
  "GET /api/auth/admin/roles": { status: 200, body: { roles: ROLES, permissions: PERMISSIONS } },
};

async function opened(session = admin) {
  renderApp({ path: "/admin/roles", session });
  await screen.findByRole("heading", { level: 1, name: "Roles and permissions" });
  return screen.findByRole("list", { name: "Roles" });
}

describe("the roles page", () => {
  it("shows each role with how many hold it, and the permissions in groups against the roles", async () => {
    routedFetch(BASE);
    const cards = within(await opened());
    expect(cards.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent)).toEqual(["Owner", "Admin", "Member", "Crew"]);
    expect(cards.getByText("Everything, always")).toBeInTheDocument();
    expect(cards.getByText("37")).toBeInTheDocument();
    const captions = screen.getAllByRole("table").map((table) => table.querySelector("caption")?.textContent);
    expect(captions).toEqual(["People and access", "Site and system", "Moderation", "Beat store"]);
    const moderation = within(screen.getByRole("table", { name: "Moderation" }));
    const row = moderation.getAllByRole("row")[1] as HTMLElement;
    expect(within(row).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "Act on moderation reportskernel.moderation.act",
      "Yes",
      "Yes",
      "No",
      "Yes",
    ]);
  });

  it("offers no New role or Edit without auth.role.manage, and no Edit on a built-in role", async () => {
    routedFetch(BASE);
    const reader = testUser({ roles: ["member", "helper"], second_factor: true, permissions: ["auth.user.manage"] });
    const cards = within(await opened(reader));
    expect(screen.queryByRole("button", { name: "New role" })).toBeNull();
    expect(cards.queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  it("offers Edit only on the site's own roles", async () => {
    routedFetch(BASE);
    const cards = within(await opened());
    expect(cards.getAllByRole("button", { name: /^Edit/ }).map((button) => button.getAttribute("aria-label"))).toEqual(["Edit Crew"]);
  });
});

describe("a new role", () => {
  it("takes its id from its name, offers only the permissions you hold, and is made", async () => {
    const { sent } = routedFetch({
      ...BASE,
      "POST /api/auth/admin/roles": { status: 201, body: { id: "beat-crew", name: "Beat crew", description: "", permissions: ["auth.user.manage"], people: 0, builtin: false } },
    });
    await opened();
    await userEvent.click(screen.getByRole("button", { name: "New role" }));
    const dialog = within(await screen.findByRole("dialog", { name: "New role" }));
    await userEvent.type(dialog.getByRole("textbox", { name: "Name" }), "Beat crew");
    expect(dialog.getByRole("textbox", { name: /^Id/ })).toHaveValue("beat-crew");
    expect(dialog.getByRole("switch", { name: /^Retry and discard/ })).toBeDisabled();
    expect(dialog.getByText("kernel.jobs.manage: you don't hold this one.")).toBeInTheDocument();
    await userEvent.click(dialog.getByRole("switch", { name: /^See and edit/ }));
    await userEvent.click(dialog.getByRole("button", { name: "Make role" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    const post = sent.find((request) => request.method === "POST");
    expect(await post?.json()).toEqual({ id: "beat-crew", name: "Beat crew", description: "", permissions: ["auth.user.manage"] });
    expect(await screen.findByText("Made Beat crew.")).toBeInTheDocument();
  });

  it("asks for a name and a usable id before sending, and says when the id is taken", async () => {
    const { sent } = routedFetch({ ...BASE, "POST /api/auth/admin/roles": problem(409, "auth.role_exists") });
    await opened();
    await userEvent.click(screen.getByRole("button", { name: "New role" }));
    const dialog = within(await screen.findByRole("dialog", { name: "New role" }));
    await userEvent.click(dialog.getByRole("button", { name: "Make role" }));
    expect(dialog.getByText("Give the role a name.")).toBeInTheDocument();
    expect(sent.some((request) => request.method === "POST")).toBe(false);
    await userEvent.type(dialog.getByRole("textbox", { name: "Name" }), "Crew");
    await userEvent.click(dialog.getByRole("button", { name: "Make role" }));
    expect(await dialog.findByText("A role already has that id. Pick another.")).toBeInTheDocument();
  });
});

describe("the site's own role", () => {
  it("is changed", async () => {
    const { sent } = routedFetch({
      ...BASE,
      "PUT /api/auth/admin/roles/crew": { status: 200, body: { ...CREW, name: "Mods" } },
      "GET /api/auth/session": { status: 200, body: { user: admin } },
    });
    const cards = within(await opened());
    await userEvent.click(cards.getByRole("button", { name: "Edit Crew" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Edit Crew" }));
    expect(dialog.queryByRole("textbox", { name: /^Id/ })).toBeNull();
    const name = dialog.getByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Mods");
    await userEvent.click(dialog.getByRole("button", { name: "Save role" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    const put = sent.find((request) => request.method === "PUT");
    expect(await put?.json()).toEqual({ name: "Mods", description: "Moderates", permissions: ["kernel.moderation.act"] });
    // The editor may hold the role: their session is read again (Codex on #85).
    await waitFor(() => {
      expect(sent.some((request) => request.method === "GET" && request.url.endsWith("/api/auth/session"))).toBe(true);
    });
  });

  it("is deleted once confirmed, while no one holds it", async () => {
    const { sent } = routedFetch({ ...BASE, "DELETE /api/auth/admin/roles/crew": { status: 204 } });
    const cards = within(await opened());
    await userEvent.click(cards.getByRole("button", { name: "Edit Crew" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Edit Crew" }));
    await userEvent.click(dialog.getByRole("button", { name: "Delete role" }));
    expect(dialog.getByText("Delete Crew? This can't be undone.")).toBeInTheDocument();
    await userEvent.click(dialog.getByRole("button", { name: "Delete Crew" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(sent.some((request) => request.method === "DELETE")).toBe(true);
    expect(await screen.findByText("Deleted Crew.")).toBeInTheDocument();
  });

  it("isn't offered for deleting while someone holds it, and a refusal is said", async () => {
    const held = { ...CREW, people: 2 };
    routedFetch({
      ...BASE,
      "GET /api/auth/admin/roles": { status: 200, body: { roles: [...ROLES.slice(0, 3), held], permissions: PERMISSIONS } },
      "PUT /api/auth/admin/roles/crew": problem(403, "auth.role_not_yours"),
    });
    const cards = within(await opened());
    await userEvent.click(cards.getByRole("button", { name: "Edit Crew" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Edit Crew" }));
    expect(dialog.queryByRole("button", { name: "Delete role" })).toBeNull();
    expect(dialog.getByText(/2 people hold this role/)).toBeInTheDocument();
    await userEvent.click(dialog.getByRole("button", { name: "Save role" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent("A role can carry only permissions you hold.");
  });
});

describe("role helpers", () => {
  it("makes an id from a name", () => {
    expect(idFrom("Beat makers")).toBe("beat-makers");
    expect(idFrom("  3D Artists! ")).toBe("d-artists");
    expect(idFrom("Café crew")).toBe("cafe-crew");
  });

  it("groups the kernel's permissions by what they're for, then each module's", () => {
    expect(permissionGroups(PERMISSIONS).map((group) => [group.label, group.items.length])).toEqual([
      ["People and access", 2],
      ["Site and system", 1],
      ["Moderation", 1],
      ["Beat store", 1],
    ]);
  });
});
