import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithKernel, testUser } from "../../testing";
import { defineModule } from "../modules";
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
    renderWithKernel(<Labels />, { modules: [blog] }).queryClient.removeQueries({ queryKey: ["get", "/api/kernel/modules"] });
    expect(screen.getByRole("status")).toBeInTheDocument();
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
});

describe("the admin sidebar's order", () => {
  const entry = (label: string, section?: string): Placed<"nav.admin"> =>
    section === undefined ? { label, to: `/admin/${label}`, module: "m" } : { label, to: `/admin/${label}`, section, module: "m" };

  it("is Dashboard, the sections in the site's order then the rest as they come, People and access, Settings", () => {
    const groups = adminSidebar(
      [entry("posts", "Content"), entry("orders", "Shop"), entry("loose"), entry("pages", "Content"), entry("odd", "Other")],
      [
        { label: "Shop", icon: "cart" },
        { label: "Content", icon: "pen" },
        { label: "Unused", icon: "x" },
      ],
      () => true,
    );
    expect(groups.map((group) => [group.label, group.icon, group.items.map((item) => item.label)])).toEqual([
      [undefined, undefined, ["Dashboard", "loose"]],
      ["Shop", "cart", ["orders"]],
      ["Content", "pen", ["posts", "pages"]],
      ["Other", undefined, ["odd"]],
      ["People and access", undefined, ["People", "Roles", "Activity"]],
      ["Settings", undefined, ["Site", "Features", "System"]],
    ]);
  });

  it("drops the kernel's links the person can't open, and an empty group", () => {
    const groups = adminSidebar([], [], (permission) => permission === "kernel.module.manage");
    expect(groups.map((group) => group.items.map((item) => item.label))).toEqual([["Dashboard"], ["Features"]]);
  });

  it("keeps an entry's icon", () => {
    const [top] = adminSidebar([{ label: "x", to: "/admin/x", icon: "star", module: "m" }], [], () => false);
    expect(top?.items[1]).toEqual({ label: "x", to: "/admin/x", icon: "star" });
  });
});
