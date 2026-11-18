import { describe, expect, it } from "vitest";

import kernelManifest from "../../../kernel.json";
import { KERNEL_PAGES, kernelPageTaken } from "./pages";

describe("the kernel's pages", () => {
  it("are kernel.json's, in its order (change 8)", () => {
    expect(KERNEL_PAGES.map(({ path, title, access }) => ({ path, title, access }))).toEqual(kernelManifest.pages);
  });

  it("are each named once, the admin's under /admin", () => {
    expect(new Set(KERNEL_PAGES.map((page) => page.path)).size).toBe(KERNEL_PAGES.length);
    for (const page of KERNEL_PAGES) expect(page.path.startsWith("/admin")).toBe(page.access === "admin");
  });
});

describe("a route that takes a kernel page", () => {
  it.each([
    ["/sign-in", "/sign-in"],
    ["/account/:tab", "/account/notifications"],
    ["/auth/:step", "/auth/verify"],
    ["/auth/email/:what", "/auth/email/undo"],
    ["/admin/people", "/admin/people"],
    ["/admin/:section", "/admin/people"],
    ["/account/*", "/account"],
  ])("%s takes %s", (route, page) => {
    expect(kernelPageTaken(route)?.path).toBe(page);
  });

  it.each(["/", "/:slug", "/:a/:b", "/blog", "/account/orders", "/admin/blog", "/admin/blog/:id", "/notifications"])(
    "%s takes none",
    (route) => {
      expect(kernelPageTaken(route)).toBeUndefined();
    },
  );
});
