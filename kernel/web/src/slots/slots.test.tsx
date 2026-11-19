import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithKernel, testUser } from "../../testing";
import { defineModule } from "../modules";
import { SESSION_KEY } from "../session/session";
import { adminSidebar } from "./sidebar";
import { SlotOutlet, useSlot, type Placed } from "./slots";

const part = (words: string) => () => Promise.resolve({ default: () => <span>{words}</span> });

const blog = defineModule({
  id: "blog",
  routes: { public: [], member: [], admin: [] },
  slots: {
    "nav.public": [
      { label: "Blog", to: "/blog" },
      { label: "Drafts", to: "/blog/drafts", permission: "blog.post.write" },
    ],
    "site.footer": [{ lazy: part("Blog footer") }],
  },
});

const shop = defineModule({
  id: "shop",
  routes: { public: [], member: [], admin: [] },
  slots: {
    "nav.public": [{ label: "Shop", to: "/shop" }],
    "site.footer": [
      {
        lazy: () =>
          Promise.resolve({
            default: () => {
              throw new Error("the shop's footer broke");
            },
          }),
      },
      { lazy: part("Shop footer") },
    ],
  },
});

function Labels() {
  return <output>{useSlot("nav.public").map((entry) => `${entry.module}:${entry.label}`).join(",")}</output>;
}

describe("useSlot", () => {
  it("gives the entries of the modules on, in their order", () => {
    renderWithKernel(<Labels />, { modules: [blog, shop] });
    expect(screen.getByRole("status")).toHaveTextContent("blog:Blog,shop:Shop");
  });

  it("leaves out a module that's off", () => {
    renderWithKernel(<Labels />, { modules: [blog, shop], on: ["shop"] });
    expect(screen.getByRole("status")).toHaveTextContent(/^shop:Shop$/);
  });

  it("shows an entry with a permission to those who hold it", () => {
    renderWithKernel(<Labels />, {
      modules: [blog],
      session: testUser({ roles: ["member", "editor"], permissions: ["blog.post.write"] }),
    });
    expect(screen.getByRole("status")).toHaveTextContent("blog:Blog,blog:Drafts");
  });

  it("is empty until the modules on are known", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    renderWithKernel(<Labels />, { modules: [blog], on: "loading" });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("names each entry by its module and place in that module's list, whatever is filtered out", () => {
    function Keys() {
      return <output>{useSlot("nav.public").map((entry) => entry.key).join(",")}</output>;
    }
    renderWithKernel(<Keys />, { modules: [blog, shop] });
    expect(screen.getByRole("status")).toHaveTextContent("blog:nav.public:0,shop:nav.public:0");
  });
});

describe("SlotOutlet", () => {
  it("shows a menu's links", () => {
    renderWithKernel(<SlotOutlet name="nav.public" label="Site" />, { modules: [blog, shop] });
    expect(screen.getByRole("list", { name: "Site" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Shop" })).toHaveAttribute("href", "/shop");
  });

  it("shows nothing for an empty slot", () => {
    const { container } = renderWithKernel(<SlotOutlet name="nav.member" />, { modules: [blog] });
    expect(container).toBeEmptyDOMElement();
  });

  it("shows each part, one failing in its own boundary while the rest stay", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderWithKernel(<SlotOutlet name="site.footer" />, { modules: [blog, shop] });
    expect(await screen.findByText("Blog footer")).toBeInTheDocument();
    expect(await screen.findByText("Shop footer")).toBeInTheDocument();
    expect(await screen.findByText(/This part didn't load/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/This part didn't load/)).toBeInTheDocument(); // it fails again, still alone
    expect(screen.getByText("Shop footer")).toBeInTheDocument();
  });

  it("loads a part again on Try again when its code didn't arrive the first time (cubic, CodeRabbit on #79)", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let tries = 0;
    const flaky = defineModule({
      id: "flaky",
      routes: { public: [], member: [], admin: [] },
      slots: {
        "site.footer": [
          {
            lazy: () => {
              tries += 1;
              return tries === 1
                ? Promise.reject(new TypeError("Failed to fetch dynamically imported module"))
                : Promise.resolve({ default: () => <span>Flaky footer</span> });
            },
          },
        ],
      },
    });
    renderWithKernel(<SlotOutlet name="site.footer" />, { modules: [flaky] });
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Flaky footer")).toBeInTheDocument();
    expect(tries).toBe(2);
  });

  it("keeps each part's own boundary when an entry before it is hidden (cubic, CodeRabbit on #79)", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const guarded = defineModule({
      id: "guarded",
      routes: { public: [], member: [], admin: [] },
      slots: {
        "admin.dashboard.widget": [
          {
            permission: "x.see",
            lazy: () =>
              Promise.resolve({
                default: () => {
                  throw new Error("the first widget broke");
                },
              }),
          },
          { lazy: part("Second widget") },
        ],
      },
    });
    const editor = testUser({ roles: ["member", "editor"], permissions: ["x.see"] });
    const { queryClient } = renderWithKernel(<SlotOutlet name="admin.dashboard.widget" />, {
      modules: [guarded],
      session: editor,
    });
    expect(await screen.findByText("Second widget")).toBeInTheDocument();
    expect(await screen.findByText(/This part didn't load/)).toBeInTheDocument();
    act(() => {
      queryClient.setQueryData(SESSION_KEY, { ...editor, permissions: [] });
    });
    await waitFor(() => {
      expect(screen.queryByText(/This part didn't load/)).toBeNull();
    });
    expect(screen.getByText("Second widget")).toBeInTheDocument();
  });
});

describe("the admin sidebar's order", () => {
  const entry = (label: string, section?: string): Placed<"nav.admin"> =>
    section === undefined
      ? { label, to: `/admin/${label}`, module: "m", key: label }
      : { label, to: `/admin/${label}`, section, module: "m", key: label };

  it("is Dashboard, the sections in the site's order then the rest as they come, People and access, Settings", () => {
    const groups = adminSidebar(
      [entry("posts", "Content"), entry("orders", "Shop"), entry("loose"), entry("pages", "Content"), entry("odd", "Other")],
      [
        { label: "Shop", icon: "shop" },
        { label: "Content", icon: "document" },
        { label: "Unused", icon: "close" },
      ],
      () => true,
    );
    expect(groups.map((group) => [group.label, group.icon, group.items.map((item) => item.label)])).toEqual([
      [undefined, undefined, ["Dashboard", "loose"]],
      ["Shop", "shop", ["orders"]],
      ["Content", "document", ["posts", "pages"]],
      ["Other", undefined, ["odd"]],
      ["People and access", "lock", ["People", "Roles", "Activity"]],
      ["Settings", "settings", ["Site", "Features", "System"]],
    ]);
  });

  it("drops the kernel's links the person can't open, and an empty group", () => {
    const groups = adminSidebar([], [], (permission) => permission === "kernel.module.manage");
    expect(groups.map((group) => group.items.map((item) => item.label))).toEqual([["Dashboard"], ["Features"]]);
  });

  it("names a section once, however often the site lists it (cubic on #79)", () => {
    const groups = adminSidebar(
      [entry("posts", "Content")],
      [
        { label: "Content", icon: "document" },
        { label: "Content", icon: "people" },
      ],
      () => false,
    );
    expect(groups.map((group) => [group.label, group.icon, group.items.length])).toEqual([
      [undefined, undefined, 1],
      ["Content", "document", 1],
    ]);
  });

  it("keeps an entry's icon", () => {
    const [top] = adminSidebar([{ label: "x", to: "/admin/x", icon: "bell", module: "m", key: "m:0" }], [], () => false);
    expect(top?.items[1]).toEqual({ label: "x", to: "/admin/x", icon: "bell" });
  });
});
