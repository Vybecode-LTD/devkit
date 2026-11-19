// The admin's frame and its Dashboard (K4.6): the sidebar's sections, the
// breadcrumb, Ctrl K, the notices, the phone's Menu, the signed-in person,
// and "Needs you" with the modules' cards.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { renderApp, testUser } from "../../testing";
import { defineModule } from "../modules";
import { problem, routedFetch } from "../test-fetch";
import { StatCard } from "../ui/StatCard";
import { initials, roleWords, whereIs } from "./AdminFrame";
import { greeting } from "./Dashboard";
import { matching, pagesOf } from "./JumpTo";
import { adminSidebar } from "../slots/sidebar";

beforeAll(async () => {
  await Promise.all([import("./Dashboard"), import("./Activity")]);
});

afterEach(() => {
  vi.useRealTimers();
});

const admin = testUser({
  email: "ann.example@mechframe.test",
  roles: ["member", "admin"],
  second_factor: true,
  permissions: ["auth.user.manage", "auth.audit.read", "kernel.settings.manage", "kernel.module.manage"],
});

const NOTHING = {
  "GET /api/kernel/admin/attention": { status: 200, body: { items: [] } },
  "GET /api/kernel/notifications": { status: 200, body: { items: [], next_cursor: null, unread: 0 } },
};

const at = (router: { state: { location: { pathname: string } } }) => router.state.location.pathname;

/** Leaves every GET of `path` waiting, as a slow first read does; the rest go on as told. */
function holdReads(path: string): void {
  const base = globalThis.fetch;
  vi.stubGlobal("fetch", (request: Request) =>
    request.method === "GET" && new URL(request.url).pathname === path ? new Promise<Response>(() => undefined) : base(request),
  );
}

describe("the sidebar", () => {
  it("names each section, and shows its pages under it while one of them is open", async () => {
    routedFetch({
      ...NOTHING,
      "GET /api/kernel/admin/audit": { status: 200, body: { items: [], next_cursor: null, people: {}, kept_days: 365 } },
    });
    renderApp({ path: "/admin/activity", session: admin });
    await screen.findByRole("heading", { level: 1, name: "Activity log" });
    const nav = screen.getByRole("navigation", { name: "Admin" });
    const pages = within(nav).getByRole("list", { name: "People and access" });
    expect(within(pages).getAllByRole("link").map((link) => link.textContent)).toEqual(["People", "Roles", "Activity"]);
    expect(within(pages).getByRole("link", { name: "Activity" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/admin/settings");
    expect(within(nav).queryByRole("list", { name: "Settings" })).toBeNull();
  });

  it("finds the page by the longest address it's under, and Site only at its own", () => {
    const groups = adminSidebar([], [], () => true);
    expect(whereIs(groups, "/admin/settings/features").item?.label).toBe("Features");
    expect(whereIs(groups, "/admin/settings").item?.label).toBe("Site");
    expect(whereIs(groups, "/admin/people/123").item?.label).toBe("People");
    expect(whereIs(groups, "/admin").item?.label).toBe("Dashboard");
    expect(whereIs(groups, "/admin/nowhere").item).toBeUndefined();
  });

  it("marks only Site as current on Site, not on Features", async () => {
    routedFetch(NOTHING);
    renderApp({ path: "/admin/settings/features", session: admin });
    await screen.findByRole("heading", { level: 1, name: "Features" });
    const pages = within(screen.getByRole("navigation", { name: "Admin" })).getByRole("list", { name: "Settings" });
    expect(within(pages).getByRole("link", { name: "Site" })).not.toHaveAttribute("aria-current");
    expect(within(pages).getByRole("link", { name: "Features" })).toHaveAttribute("aria-current", "page");
  });

  it("shows who is signed in: initials, email and roles, and View site", async () => {
    routedFetch(NOTHING);
    renderApp({ path: "/admin", session: admin });
    const rail = await screen.findByRole("complementary", { name: "Admin sections" });
    expect(within(rail).getByText("ann.example@mechframe.test")).toBeInTheDocument();
    expect(within(rail).getByText("Admin", { selector: ".mf-admin-person-role" })).toBeInTheDocument();
    expect(within(rail).getByText("AE")).toBeInTheDocument();
    expect(within(rail).getByRole("link", { name: "View site" })).toHaveAttribute("href", "/");
    expect(initials("bo@site.test")).toBe("B");
    expect(initials("cy_place+tag@site.test")).toBe("CP");
    expect(roleWords(["member"])).toBe("Member");
    expect(roleWords(["member", "owner", "editor"])).toBe("Owner, Editor");
  });
});

describe("the top bar", () => {
  it("says where the page sits, ending in the page's own name for itself", async () => {
    routedFetch({
      ...NOTHING,
      "GET /api/kernel/admin/audit": { status: 200, body: { items: [], next_cursor: null, people: {}, kept_days: 365 } },
    });
    const { router } = renderApp({ path: "/admin", session: admin });
    await screen.findByRole("heading", { level: 1, name: greeting(new Date()) });
    const crumbs = () => within(screen.getByRole("navigation", { name: "Breadcrumb" })).getAllByRole("listitem").map((item) => item.textContent);
    expect(crumbs()).toEqual(["Admin", "Dashboard"]);
    await act(() => router.navigate("/admin/activity"));
    await screen.findByRole("heading", { level: 1, name: "Activity log" });
    expect(crumbs()).toEqual(["Admin", "People and access", "Activity log"]);
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("Activity log")).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "People and access" })).toHaveAttribute("href", "/admin/people");
  });

  it("opens Jump to on Ctrl K, narrows the pages as one types, and opens the one chosen", async () => {
    routedFetch(NOTHING);
    const { router } = renderApp({ path: "/admin", session: admin });
    await screen.findByRole("heading", { level: 1, name: greeting(new Date()) });
    await userEvent.keyboard("{Control>}k{/Control}");
    const dialog = await screen.findByRole("dialog", { name: "Jump to a page" });
    const box = within(dialog).getByRole("combobox", { name: "Page name" });
    await waitFor(() => {
      expect(box).toHaveFocus();
    });
    const options = () => within(dialog).getAllByRole("option").map((option) => option.textContent);
    expect(options()).toEqual([
      "Dashboard",
      "People People and access",
      "Roles People and access",
      "Activity People and access",
      "Site Settings",
      "Features Settings",
      "System Settings",
    ]);
    await userEvent.type(box, "set");
    expect(options()).toEqual(["Site Settings", "Features Settings", "System Settings"]);
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");
    expect(within(dialog).getByRole("option", { name: "Site Settings" })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowUp}{Enter}");
    await waitFor(() => {
      expect(at(router)).toBe("/admin/settings/system");
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens Jump to from its button too, says when nothing matches, and closes on Escape", async () => {
    routedFetch(NOTHING);
    renderApp({ path: "/admin", session: admin });
    const jump = await screen.findByRole("button", { name: /Search or jump to/ });
    expect(jump).toHaveAttribute("aria-keyshortcuts", "Control+K Meta+K");
    await userEvent.click(jump);
    const dialog = await screen.findByRole("dialog", { name: "Jump to a page" });
    await userEvent.type(within(dialog).getByRole("combobox"), "zebra");
    expect(within(dialog).getByRole("status")).toHaveTextContent("No page's name has those words.");
    await userEvent.keyboard("{Enter}{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(jump).toHaveFocus();
  });

  it("matches every word typed against a page's name and its section", () => {
    const pages = pagesOf(adminSidebar([], [], () => true));
    expect(matching(pages, "  ").length).toBe(pages.length);
    expect(matching(pages, "people ROLES").map((page) => page.to)).toEqual(["/admin/roles"]);
    expect(matching(pages, "dash").map((page) => page.to)).toEqual(["/admin"]);
  });

  it("shows the notices: the unread count, each notice, Mark all read, and a notice opened as read", async () => {
    const { sent } = routedFetch({
      ...NOTHING,
      "GET /api/kernel/notifications": {
        status: 200,
        body: {
          items: [
            { id: "n1", key: "kernel.x", title: "A report came in", link: "/admin/activity", created_at: "2026-11-19T12:00:00Z", read_at: null },
            { id: "n2", key: "kernel.y", title: "Elsewhere", link: "https://elsewhere.test/", created_at: "2026-11-18T12:00:00Z", read_at: "2026-11-18T13:00:00Z" },
          ],
          next_cursor: null,
          unread: 1,
        },
      },
      "POST /api/kernel/notifications/read": { status: 204 },
      "GET /api/kernel/admin/audit": { status: 200, body: { items: [], next_cursor: null, people: {}, kept_days: 365 } },
    });
    const { router } = renderApp({ path: "/admin", session: admin });
    const bell = await screen.findByRole("button", { name: "Notices, 1 unread" });
    expect(bell).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(bell);
    const panel = screen.getByRole("region", { name: "Notices" });
    expect(bell).toHaveAttribute("aria-expanded", "true");
    // Another site's address isn't a link out of the admin.
    expect(within(panel).queryByRole("link", { name: /Elsewhere/ })).toBeNull();
    expect(within(panel).getByText("Elsewhere")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Mark all read" }));
    await waitFor(() => {
      expect(sent.some((request) => request.method === "POST")).toBe(true);
    });
    expect(await sent.find((request) => request.method === "POST")?.clone().json()).toEqual({ all: true });
    await userEvent.click(within(panel).getByRole("link", { name: /A report came in/ }));
    await waitFor(() => {
      expect(at(router)).toBe("/admin/activity");
    });
    expect(screen.queryByRole("region", { name: "Notices" })).toBeNull();
    const posts = sent.filter((request) => request.method === "POST");
    expect(await posts.at(-1)?.clone().json()).toEqual({ ids: ["n1"] });
  });

  it("closes the notices on Escape, putting the focus back on the bell, and on a click elsewhere", async () => {
    routedFetch(NOTHING);
    renderApp({ path: "/admin", session: admin });
    const bell = await screen.findByRole("button", { name: "Notices" });
    await userEvent.click(bell);
    expect(await screen.findByText("Nothing yet. What the site tells you shows here.")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Notices" })).toBeNull();
    expect(bell).toHaveFocus();
    await userEvent.click(bell);
    await userEvent.click(screen.getByRole("heading", { level: 1 }));
    expect(screen.queryByRole("region", { name: "Notices" })).toBeNull();
  });

  it("says when the notices can't be read, with Try again", async () => {
    routedFetch({ ...NOTHING, "GET /api/kernel/notifications": problem(500, "kernel.internal_error") });
    renderApp({ path: "/admin", session: admin });
    await userEvent.click(await screen.findByRole("button", { name: "Notices" }));
    expect(await screen.findByText("Your notices couldn't be loaded.")).toBeInTheDocument();
  });

  it("opens and closes the phone's Menu, and closes it on the next page", async () => {
    routedFetch({
      ...NOTHING,
      "GET /api/kernel/admin/audit": { status: 200, body: { items: [], next_cursor: null, people: {}, kept_days: 365 } },
    });
    const { router } = renderApp({ path: "/admin", session: admin });
    const menu = await screen.findByRole("button", { name: "Menu" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(document.getElementById(menu.getAttribute("aria-controls") ?? "")).toHaveClass("mf-admin-rail");
    await userEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(menu);
    await act(() => router.navigate("/admin/activity"));
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });

  it("stays shut on coming back to the page it was opened on (CodeRabbit on #84)", async () => {
    routedFetch({
      ...NOTHING,
      "GET /api/kernel/admin/audit": { status: 200, body: { items: [], next_cursor: null, people: {}, kept_days: 365 } },
    });
    const { router } = renderApp({ path: "/admin", session: admin });
    await userEvent.click(await screen.findByRole("button", { name: "Menu" }));
    await act(() => router.navigate("/admin/activity"));
    await screen.findByRole("heading", { level: 1, name: "Activity log" });
    await act(() => router.navigate("/admin"));
    await screen.findByRole("heading", { level: 1, name: greeting(new Date()) });
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    await act(() => router.navigate(-2));
    await screen.findByRole("heading", { level: 1, name: greeting(new Date()) });
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });

  it("says the notices are on their way while the first read is (CodeRabbit on #84)", async () => {
    routedFetch(NOTHING);
    holdReads("/api/kernel/notifications");
    renderApp({ path: "/admin", session: admin });
    await userEvent.click(await screen.findByRole("button", { name: "Notices" }));
    const panel = screen.getByRole("region", { name: "Notices" });
    expect(within(panel).getByRole("status")).toHaveTextContent("Loading your notices");
    expect(within(panel).queryByText(/Nothing yet/)).toBeNull();
  });

  it("says when Mark all read didn't go through, and tries again (CodeRabbit on #84)", async () => {
    let tries = 0;
    const { sent } = routedFetch({
      ...NOTHING,
      "GET /api/kernel/notifications": {
        status: 200,
        body: {
          items: [{ id: "n1", key: "kernel.x", title: "A report came in", link: null, created_at: "2026-11-19T12:00:00Z", read_at: null }],
          next_cursor: null,
          unread: 1,
        },
      },
      "POST /api/kernel/notifications/read": () => {
        tries += 1;
        return tries === 1 ? problem(500, "kernel.internal_error") : { status: 204 };
      },
    });
    renderApp({ path: "/admin", session: admin });
    await userEvent.click(await screen.findByRole("button", { name: "Notices, 1 unread" }));
    const panel = screen.getByRole("region", { name: "Notices" });
    await userEvent.click(within(panel).getByRole("button", { name: "Mark all read" }));
    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent("Your notices couldn't be marked read.");
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    await waitFor(() => {
      expect(within(panel).queryByRole("alert")).toBeNull();
    });
    const posts = sent.filter((request) => request.method === "POST");
    expect(posts).toHaveLength(2);
    expect(await posts[1]?.clone().json()).toEqual({ all: true });
  });
});

describe("the Dashboard", () => {
  it("greets by the reader's clock", () => {
    const day = (hour: number) => new Date(2026, 10, 19, hour);
    expect([4, 5, 11, 12, 17, 18, 23].map((hour) => greeting(day(hour)))).toEqual([
      "Good evening",
      "Good morning",
      "Good morning",
      "Good afternoon",
      "Good afternoon",
      "Good evening",
      "Good evening",
    ]);
  });

  it("lists what needs the person, worst first as the server sends it, each with its fix", async () => {
    routedFetch({
      ...NOTHING,
      "GET /api/kernel/admin/attention": {
        status: 200,
        body: {
          items: [
            { key: "kernel.jobs.dead", tone: "danger", what: "2 background jobs failed", why: "They ran out of tries.", action: { label: "See failed jobs", to: "/admin/settings/system" } },
            { key: "kernel.site.card_missing", tone: "info", what: "Shared links show no picture", why: "No image.", action: { label: "Choose a picture", to: "/admin/settings" } },
          ],
        },
      },
    });
    renderApp({ path: "/admin", session: admin });
    const section = await screen.findByRole("region", { name: "Needs you 2" });
    const items = await within(section).findAllByRole("listitem");
    expect(items.map((item) => item.querySelector(".mf-attention-what")?.textContent)).toEqual(["2 background jobs failed", "Shared links show no picture"]);
    const [first, second] = items;
    expect(first?.querySelector("[role=img]")).toHaveAccessibleName("Problem");
    expect(second?.querySelector("[role=img]")).toHaveAccessibleName("Note");
    expect(within(section).getByRole("link", { name: "See failed jobs" })).toHaveAttribute("href", "/admin/settings/system");
  });

  it("says what needs the person is on its way while it's read (CodeRabbit on #84)", async () => {
    routedFetch(NOTHING);
    holdReads("/api/kernel/admin/attention");
    renderApp({ path: "/admin", session: admin });
    const section = await screen.findByRole("region", { name: "Needs you" });
    expect(within(section).getByRole("status")).toHaveTextContent("Checking what needs you");
    expect(within(section).queryByText("Nothing needs you right now.")).toBeNull();
  });

  it("says so when nothing needs the person, and when the list can't be read", async () => {
    routedFetch(NOTHING);
    const { unmount } = renderApp({ path: "/admin", session: admin });
    expect(await screen.findByText("Nothing needs you right now.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Needs you 0" })).toBeInTheDocument();
    unmount();
    routedFetch({ ...NOTHING, "GET /api/kernel/admin/attention": problem(500, "kernel.internal_error") });
    renderApp({ path: "/admin", session: admin });
    expect(await screen.findByText("What needs you couldn't be loaded.")).toBeInTheDocument();
  });

  it("lays out the modules' cards, each one's own", async () => {
    routedFetch(NOTHING);
    const music = defineModule({
      id: "music",
      routes: { public: [], member: [], admin: [] },
      slots: {
        "admin.dashboard.widget": [
          { lazy: () => Promise.resolve({ default: () => <StatCard label="Plays this week" value="1,284" /> }) },
          { lazy: () => Promise.resolve({ default: () => <StatCard label="Sales today" value="$0" /> }), permission: "shop.order.read" },
        ],
      },
    });
    const { container } = renderApp({ path: "/admin", session: admin, modules: [music] });
    expect(await screen.findByRole("region", { name: "Plays this week" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sales today" })).toBeNull();
    expect(container.querySelector(".mf-dashboard-cards")).toContainElement(screen.getByRole("region", { name: "Plays this week" }));
  });

  it("draws no grid without cards, and names the day in its lead", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 10, 15, 19, 30) });
    routedFetch(NOTHING);
    const { container } = renderApp({ path: "/admin", session: admin });
    expect(await screen.findByRole("heading", { level: 1, name: "Good evening" })).toBeInTheDocument();
    expect(screen.getByText(/^Sunday, November 15\. Here's what needs you and how the site is doing\.$/)).toBeInTheDocument();
    expect(container.querySelector(".mf-dashboard-cards")).toBeNull();
  });
});
