import { describe, expect, it } from "vitest";

import { defineModule, type ModuleDefinition, type Slots } from "../index";
import kernelManifest from "../../kernel.json";
import { KERNEL_WEB_VERSION } from "./version";

const page = () => Promise.resolve({ default: () => null });

function blog(overrides: Partial<ModuleDefinition> = {}): ModuleDefinition {
  return {
    id: "blog",
    routes: {
      public: [{ path: "/blog", lazy: page }],
      member: [],
      admin: [{ path: "/admin/blog", lazy: page, permission: "blog.post.write" }],
    },
    slots: { "nav.admin": [{ label: "Posts", to: "/admin/blog" }] },
    ...overrides,
  };
}

describe("defineModule", () => {
  it("returns a good definition as it was", () => {
    const definition = blog();
    expect(defineModule(definition)).toBe(definition);
  });

  it("refuses an id that isn't one", () => {
    expect(() => defineModule(blog({ id: "Blog_Posts" }))).toThrow(/isn't a module id/);
  });

  it("refuses an admin route outside /admin/", () => {
    const routes = { ...blog().routes, admin: [{ path: "/blog/edit", lazy: page, permission: "blog.post.write" }] };
    expect(() => defineModule(blog({ routes }))).toThrow(/must start with \/admin\//);
  });

  it("refuses an admin route with no permission", () => {
    const routes = { ...blog().routes, admin: [{ path: "/admin/blog", lazy: page }] };
    expect(() => defineModule(blog({ routes }))).toThrow(/must name a permission/);
  });

  it("refuses a path given twice", () => {
    const routes = { ...blog().routes, member: [{ path: "/blog", lazy: page }] };
    expect(() => defineModule(blog({ routes }))).toThrow(/twice/);
  });

  it.each([
    ["public", "/sign-in"],
    ["member", "/account/:tab"],
    ["admin", "/admin/people"],
  ] as const)("refuses a %s route that takes a kernel page: %s", (level, path) => {
    const routes = { ...blog().routes, [level]: [{ path, lazy: page, permission: "blog.post.write" }] };
    expect(() => defineModule(blog({ routes }))).toThrow(/takes the kernel's page/);
  });

  it.each(["public", "member"] as const)("refuses a %s route under /admin", (level) => {
    const routes = { ...blog().routes, [level]: [{ path: "/admin/mine", lazy: page }] };
    expect(() => defineModule(blog({ routes }))).toThrow(/list it as an admin route/);
  });

  it.each(["auth", "kernel", "site"])("refuses the id %s, which the kernel keeps (cubic on #79)", (id) => {
    expect(() => defineModule(blog({ id }))).toThrow(/the kernel's own/);
  });

  it("refuses an admin link that leaves /admin once its dots are read", () => {
    expect(() => defineModule(blog({ slots: { "nav.admin": [{ label: "Out", to: "/admin/../sign-in" }] } }))).toThrow(
      /must go under \/admin/,
    );
  });

  it("takes an admin link with a query", () => {
    const definition = blog({ slots: { "nav.admin": [{ label: "People", to: "/admin?tab=people" }] } });
    expect(defineModule(definition)).toBe(definition);
  });

  it("refuses a slot the kernel doesn't have", () => {
    const slots = { "nav.footer": [{ label: "Posts", to: "/blog" }] } as unknown as Slots;
    expect(() => defineModule(blog({ slots }))).toThrow(/doesn't have/);
  });

  it.each(["https://evil.test/", "//evil.test", "blog", "/a\\b"])("refuses a link off the site: %s", (to) => {
    expect(() => defineModule(blog({ slots: { "nav.public": [{ label: "Out", to }] } }))).toThrow(/path on this site/);
  });

  it("refuses an admin link outside /admin", () => {
    expect(() => defineModule(blog({ slots: { "nav.admin": [{ label: "Posts", to: "/blog" }] } }))).toThrow(
      /must go under \/admin/,
    );
  });

  it("refuses a part that doesn't load", () => {
    const slots = { "site.footer": [{ lazy: "nope" }] } as unknown as Slots;
    expect(() => defineModule(blog({ slots }))).toThrow(/must load its part/);
  });

  it("takes every slot it knows, parts and links", () => {
    const definition = blog({
      slots: {
        "nav.public": [{ label: "Blog", to: "/blog" }],
        "nav.member": [{ label: "Drafts", to: "/blog/drafts" }],
        "nav.admin": [{ label: "Posts", to: "/admin/blog", section: "Content", icon: "document" }],
        "admin.dashboard.widget": [{ lazy: page }],
        "admin.settings.section": [{ id: "blog", title: "Blog", lazy: page }],
        "account.section": [{ id: "blog", title: "Your posts", lazy: page }],
        "site.footer": [{ lazy: page }],
      },
    });
    expect(defineModule(definition)).toBe(definition);
  });
});

describe("the kernel's version", () => {
  it("matches kernel.json", () => {
    expect(KERNEL_WEB_VERSION).toBe(kernelManifest.version);
  });
});
