import { describe, expect, it } from "vitest";

import { defineModule, type ModuleDefinition } from "../index";
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
});

describe("the kernel's version", () => {
  it("matches kernel.json", () => {
    expect(KERNEL_WEB_VERSION).toBe(kernelManifest.version);
  });
});
