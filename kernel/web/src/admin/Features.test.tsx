// The admin's Features tab (K4.8): each module's switch, grouped by its kind;
// switching one off that others need asks first, naming them.
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import { routedFetch, type Answer } from "../test-fetch";
import { grouped, moduleHint, type ModuleItem } from "./Features";

beforeAll(async () => {
  await import("./Features");
});

const admin = testUser({ roles: ["member", "admin"], second_factor: true, permissions: ["kernel.settings.manage", "kernel.module.manage"] });

function item(id: string, fields: Partial<ModuleItem> = {}): ModuleItem {
  return {
    id,
    name: `${(id[0] ?? "").toUpperCase()}${id.slice(1)}`,
    summary: `The ${id} module, for testing.`,
    category: "content",
    on: true,
    switched: true,
    requires: [],
    required_by: [],
    ...fields,
  };
}

const BLOG = item("blog", { required_by: ["comments"] });
const COMMENTS = item("comments", { requires: ["blog"], category: "community" });
const SHOP = item("shop", { category: "commerce" });

const list = (...items: ModuleItem[]): Answer => ({ status: 200, body: { items } });

function answers(more: Record<string, Answer | ((request: Request) => Answer)> = {}) {
  return routedFetch({
    "GET /api/kernel/notifications": { status: 200, body: { items: [], next_cursor: null, unread: 0 } },
    "GET /api/kernel/admin/modules": list(BLOG, COMMENTS, SHOP),
    ...more,
  });
}

async function opened() {
  renderApp({ path: "/admin/settings/features", session: admin });
  await screen.findByRole("heading", { level: 1, name: "Settings" });
  return screen.findByRole("switch", { name: "Blog" });
}

const sentTo = (sent: Request[], method: string, path: string) =>
  sent.filter((request) => request.method === method && new URL(request.url).pathname === path);

describe("the Features tab", () => {
  it("groups the modules by their kind, each switch as the admin left it", async () => {
    answers();
    await opened();
    const content = within(screen.getByRole("region", { name: "Content" }));
    expect(content.getByRole("switch", { name: "Blog" })).toBeChecked();
    expect(within(screen.getByRole("region", { name: "Community" })).getByRole("switch", { name: "Comments" })).toBeChecked();
    expect(within(screen.getByRole("region", { name: "Shop and payments" })).getByRole("switch", { name: "Shop" })).toBeChecked();
  });

  it("asks before switching off a module others need, naming them", async () => {
    const { sent } = answers({
      "PUT /api/kernel/admin/modules/blog": list(
        { ...BLOG, on: false, switched: false },
        { ...COMMENTS, on: false },
        SHOP,
      ),
    });
    const user = userEvent.setup();
    await user.click(await opened());
    const dialog = within(await screen.findByRole("dialog", { name: "Switch off Blog?" }));
    expect(dialog.getByText(/Comments needs Blog, so it goes off too/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Keep it on" }));
    expect(sentTo(sent, "PUT", "/api/kernel/admin/modules/blog")).toHaveLength(0);

    await user.click(screen.getByRole("switch", { name: "Blog" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Switch off 2" }));
    expect(await screen.findByText("Blog is switched off.")).toBeInTheDocument();
    const [put] = sentTo(sent, "PUT", "/api/kernel/admin/modules/blog");
    expect(await put?.json()).toEqual({ on: false });
    expect(screen.getByRole("switch", { name: "Blog" })).not.toBeChecked();
    // Comments keeps its own switch, and says why it's off.
    expect(screen.getByRole("switch", { name: "Comments" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Comments" })).toHaveAccessibleDescription(/Off while Blog is off/);
  });

  it("switches a module nothing needs at once", async () => {
    const { sent } = answers({ "PUT /api/kernel/admin/modules/shop": list(BLOG, COMMENTS, { ...SHOP, on: false, switched: false }) });
    const user = userEvent.setup();
    await opened();
    await user.click(screen.getByRole("switch", { name: "Shop" }));
    expect(await screen.findByText("Shop is switched off.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(sentTo(sent, "PUT", "/api/kernel/admin/modules/shop")).toHaveLength(1);
  });

  it("says when there's nothing to switch", async () => {
    answers({ "GET /api/kernel/admin/modules": list() });
    renderApp({ path: "/admin/settings/features", session: admin });
    expect(await screen.findByText("No modules to switch")).toBeInTheDocument();
  });
});

describe("the modules' groups and words", () => {
  it("keeps the categories' order, with an unknown one last", () => {
    const odd = item("odd", { category: "whatever" });
    expect(grouped([odd, SHOP, BLOG]).map((group) => group.title)).toEqual(["Content", "Shop and payments", "Other"]);
  });

  it("says a module is off while one it needs is", () => {
    const byId = new Map([BLOG, COMMENTS].map((found) => [found.id, found]));
    expect(moduleHint(COMMENTS, byId)).toBe(COMMENTS.summary);
    const off = new Map([
      ["blog", { ...BLOG, on: false, switched: false }],
      ["comments", { ...COMMENTS, on: false }],
    ]);
    expect(moduleHint({ ...COMMENTS, on: false }, off)).toBe(`${COMMENTS.summary} Off while Blog is off.`);
    // Switched off by the admin, it's simply off.
    expect(moduleHint({ ...COMMENTS, on: false, switched: false }, off)).toBe(COMMENTS.summary);
  });
});
