// The activity log (K4.6): who did what and when, by kind, fifty at a time,
// and everything an entry holds one click deeper.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import type { components } from "../api/schema";
import { problem, routedFetch, type Answer } from "../test-fetch";
import { KINDS, kindOf, whatHappened } from "./actions";

type Entry = components["schemas"]["AuditEntry"];

beforeAll(async () => {
  await import("./Activity");
});

const staff = testUser({ roles: ["member", "admin"], second_factor: true, permissions: ["auth.audit.read"] });

const ANN = "00000000-0000-4000-8000-0000000000a1";
const BO = "00000000-0000-4000-8000-0000000000b2";
const GONE = "00000000-0000-4000-8000-0000000000c3";

const PEOPLE = {
  [ANN]: { name: "Ann Example", email: "ann@site.test", roles: [{ id: "admin", name: "Admin" }, { id: "member", name: "Member" }] },
  [BO]: { name: null, email: "bo@site.test", roles: [{ id: "member", name: "Member" }] },
};

function entry(id: number, fields: Partial<Entry>): Entry {
  return {
    id,
    at: "2026-11-19T15:04:00Z",
    action: "auth.sign_in",
    result: "success",
    actor_id: null,
    subject_id: null,
    target: null,
    ip: null,
    user_agent: "",
    details: {},
    ...fields,
  };
}

const ENTRIES: Entry[] = [
  entry(5, { action: "auth.user.suspended", actor_id: ANN, subject_id: BO, details: { reason: "spam", days: 7 }, ip: "203.0.113.9", user_agent: "Firefox" }),
  entry(4, { action: "auth.passkey_added", actor_id: BO, subject_id: BO, details: { name: "Phone", at: { x: 1 } } }),
  entry(3, { action: "auth.user.removed_unverified", details: { count: 3, changed: ["a", "b"] } }),
  entry(2, { action: "auth.sign_in", result: "failure", ip: "198.51.100.4", user_agent: "Chrome" }),
  entry(1, { action: "blog.post_published", actor_id: GONE, target: { type: "blog.post", id: "42" } }),
];

function page(items: Entry[], next: string | null = null): Answer {
  return { status: 200, body: { items, next_cursor: next, people: PEOPLE, kept_days: 365 } };
}

const BASE = {
  "GET /api/kernel/notifications": { status: 200, body: { items: [], next_cursor: null, unread: 0 } },
};

async function opened() {
  renderApp({ path: "/admin/activity", session: staff });
  await screen.findByRole("heading", { level: 1, name: "Activity log" });
  return within(await screen.findByRole("table", { name: "Entries, newest first" }));
}

describe("the activity log", () => {
  it("says who did what, when, in a few details, and its kind; and how long entries are kept", async () => {
    routedFetch({ ...BASE, "GET /api/kernel/admin/audit": page(ENTRIES) });
    const table = await opened();
    const rows = table.getAllByRole("row").slice(1);
    const cells = rows.map((row) => within(row).getAllByRole("cell").slice(1).map((cell) => cell.textContent));
    expect(cells).toEqual([
      ["Ann ExampleAdmin", "Suspended bo@site.test", "Reason: spam, Days: 7", "Accounts and roles"],
      ["bo@site.testMember", "Added a passkey", 'Name: Phone, At: {"x":1}', "Sign-in"],
      ["MechFrameSystem", "Removed an unconfirmed account", "Count: 3, Changed: a, b", "Accounts and roles"],
      ["SomeoneNot signed in", "Signed in (didn't go through)", "", "Sign-in"],
      ["A removed account", "blog.post_published", "", "Blog"],
    ]);
    expect(rows[0]?.querySelector("td time")).toHaveAttribute("dateTime", "2026-11-19T15:04:00Z");
    expect(screen.getByText("Kept for 365 days. Older entries leave the log on their own.")).toBeInTheDocument();
  });

  it("shows everything the newest entry holds beneath the table, and another's once it's picked", async () => {
    routedFetch({ ...BASE, "GET /api/kernel/admin/audit": page(ENTRIES) });
    const table = await opened();
    const panel = () => document.getElementById("activity-entry");
    const fields = () => [...(panel()?.querySelectorAll("dt") ?? [])].map((term) => [term.textContent, term.nextElementSibling?.textContent]);
    expect(panel()).toHaveTextContent("Suspended bo@site.test");
    expect(fields()[0]?.[0]).toBe("When");
    expect(fields().slice(1)).toEqual([
      ["By", "Ann Example, Admin"],
      ["Result", "Went through"],
      ["Reason", "spam"],
      ["Days", "7"],
      ["From", "203.0.113.9"],
      ["Browser", "Firefox"],
      ["Entry", "5"],
    ]);
    const blog = table.getByRole("button", { name: "blog.post_published" });
    expect(blog).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(blog);
    expect(blog).toHaveAttribute("aria-pressed", "true");
    expect(fields().slice(1)).toEqual([
      ["By", "A removed account"],
      ["Result", "Went through"],
      ["About", "blog.post 42"],
      ["Entry", "1"],
    ]);
  });

  it("asks for a kind's actions and prefixes at once, and for every entry again under All", async () => {
    const asked: string[][] = [];
    routedFetch({
      ...BASE,
      "GET /api/kernel/admin/audit": (request) => {
        const actions = new URL(request.url).searchParams.getAll("action");
        asked.push(actions);
        return page(actions.length ? ENTRIES.slice(2, 3) : ENTRIES);
      },
    });
    await opened();
    const kinds = screen.getByRole("group", { name: "Kind" });
    expect(within(kinds).getAllByRole("button").map((chip) => chip.textContent)).toEqual(["All", ...KINDS.map((kind) => kind.label)]);
    expect(within(kinds).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(kinds).getByRole("button", { name: "Accounts and roles" }));
    await waitFor(() => {
      expect(screen.getByRole("table", { name: "Accounts and roles entries, newest first" })).toBeInTheDocument();
    });
    expect(asked.at(-1)).toEqual(["auth.sign_up", "auth.email_verified", "auth.verification_resent", "auth.user.", "auth.role."]);
    // Pressed again, a kind lets go: All.
    await userEvent.click(within(kinds).getByRole("button", { name: /Accounts and roles/ }));
    await screen.findByRole("table", { name: "Entries, newest first" });
    expect(within(kinds).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(kinds).getByRole("button", { name: "Moderation" }));
    await screen.findByRole("table", { name: "Moderation entries, newest first" });
    await userEvent.click(within(kinds).getByRole("button", { name: "All" }));
    const all = within(await screen.findByRole("table", { name: "Entries, newest first" }));
    expect(all.getAllByRole("row")).toHaveLength(ENTRIES.length + 1);
    expect(asked[0]).toEqual([]);
  });

  it("shows older entries on asking, the next page after the last", async () => {
    const cursors: (string | null)[] = [];
    routedFetch({
      ...BASE,
      "GET /api/kernel/admin/audit": (request) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        cursors.push(cursor);
        return cursor ? page(ENTRIES.slice(3)) : page(ENTRIES.slice(0, 3), "c1");
      },
    });
    const table = await opened();
    expect(table.getAllByRole("row")).toHaveLength(4);
    await userEvent.click(screen.getByRole("button", { name: "Show older" }));
    await waitFor(() => {
      expect(table.getAllByRole("row")).toHaveLength(6);
    });
    expect(cursors).toEqual([null, "c1"]);
    expect(screen.queryByRole("button", { name: "Show older" })).toBeNull();
  });

  it("says when the log can't be read, and when it has nothing yet", async () => {
    routedFetch({ ...BASE, "GET /api/kernel/admin/audit": problem(500, "kernel.internal_error") });
    const { unmount } = renderApp({ path: "/admin/activity", session: staff });
    expect(await screen.findByText("The activity log couldn't be loaded.")).toBeInTheDocument();
    unmount();
    routedFetch({ ...BASE, "GET /api/kernel/admin/audit": page([]) });
    renderApp({ path: "/admin/activity", session: staff });
    expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
    expect(document.getElementById("activity-entry")).toBeNull();
  });

  it("is the no-access page without auth.audit.read", async () => {
    routedFetch(BASE);
    renderApp({ path: "/admin/activity", session: { ...staff, permissions: [] } });
    expect(await screen.findByRole("heading", { name: "You can't open this page" })).toBeInTheDocument();
  });
});

describe("the kernel's actions", () => {
  // The backend's closed set (kernel/backend/kernel/audit.py, KERNEL_ACTIONS).
  const source = readFileSync(resolve(__dirname, "../../../backend/kernel/audit.py"), "utf-8");
  const block = /KERNEL_ACTIONS = frozenset\(\s*\{([\s\S]*?)\}\s*\)/.exec(source)?.[1] ?? "";
  const actions = [...block.matchAll(/"([a-z_.]+)"/g)].map((found) => found[1] ?? "");

  it("are read from the backend", () => {
    expect(actions.length).toBeGreaterThan(30);
    expect(actions).toContain("auth.sign_in");
  });

  it("each has words of its own and one of the kernel's kinds", () => {
    const labels = KINDS.map((kind) => kind.label);
    for (const action of actions) {
      expect(whatHappened(action, "Bo"), action).not.toBe(action);
      expect(labels, action).toContain(kindOf(action));
    }
  });

  it("name whom they concern where it matters", () => {
    expect(whatHappened("kernel.moderation.timed_out", "Bo")).toBe("Timed out Bo");
    expect(whatHappened("kernel.moderation.time_out_lifted", "Bo")).toBe("Lifted Bo's time-out");
    expect(whatHappened("auth.user.restored", "Bo")).toBe("Restored Bo");
  });
});
