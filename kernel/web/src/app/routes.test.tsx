import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderApp, testUser } from "../../testing";
import { defineModule, type ModuleDefinition } from "../modules";
import { routedFetch } from "../test-fetch";
import { isMissingCode } from "./RouteError";
import { FOCUS_WAIT_MS } from "./RouteFocus";

function pageSaying(words: string) {
  return () => Promise.resolve({ default: () => <h1>{words}</h1> });
}

const blog: ModuleDefinition = defineModule({
  id: "blog",
  routes: {
    public: [{ path: "/blog", lazy: pageSaying("The blog") }],
    member: [{ path: "/blog/drafts", lazy: pageSaying("Your drafts") }],
    admin: [{ path: "/admin/blog", lazy: pageSaying("Posts"), permission: "blog.post.write" }],
  },
  slots: { "nav.admin": [{ label: "Posts", to: "/admin/blog", section: "Content" }] },
});

const landing: ModuleDefinition = defineModule({
  id: "landing",
  routes: { public: [{ path: "/", lazy: pageSaying("The landing page") }], member: [], admin: [] },
});

const staff = testUser({ roles: ["member", "admin"], second_factor: true, permissions: ["auth.user.manage"] });

function at(router: ReturnType<typeof renderApp>["router"]) {
  return router.state.location.pathname + router.state.location.search;
}

describe("the public pages", () => {
  it("are the kernel's home, saying what the server's copy says", async () => {
    renderApp({ site: { name: "Vibrant", description: "Music and more." } });
    expect(await screen.findByRole("heading", { level: 1, name: "Vibrant" })).toBeInTheDocument();
    expect(screen.getByText("Music and more.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  });

  it("leave out the description's paragraph when there's none", async () => {
    renderApp({ site: { name: "Vibrant", description: "" } });
    await screen.findByRole("heading", { level: 1, name: "Vibrant" });
    expect(screen.getByRole("main").querySelector("p")).toBeNull();
  });

  it("are a module's page at / while it's on, else the kernel's home", async () => {
    const { unmount } = renderApp({ modules: [landing] });
    expect(await screen.findByRole("heading", { name: "The landing page" })).toBeInTheDocument();
    unmount();
    renderApp({ modules: [landing], on: [], site: { name: "Kernel home" } });
    expect(await screen.findByRole("heading", { name: "Kernel home" })).toBeInTheDocument();
  });

  it("are a module's page, loaded when asked for", async () => {
    renderApp({ path: "/blog", modules: [blog] });
    expect(await screen.findByRole("heading", { name: "The blog" })).toBeInTheDocument();
  });

  it("leave an address to a module on when the one with the more fixed route is off, as the server does (Codex on #79)", async () => {
    const posts = defineModule({
      id: "posts",
      routes: { public: [{ path: "/blog/:slug", lazy: pageSaying("A post") }], member: [], admin: [] },
    });
    const pages = defineModule({
      id: "pages",
      routes: { public: [{ path: "/:section/:slug", lazy: pageSaying("A page") }], member: [], admin: [] },
    });
    const { unmount } = renderApp({ path: "/blog/hello", modules: [posts, pages] });
    expect(await screen.findByRole("heading", { name: "A post" })).toBeInTheDocument();
    unmount();
    renderApp({ path: "/blog/hello", modules: [posts, pages], on: ["pages"] });
    expect(await screen.findByRole("heading", { name: "A page" })).toBeInTheDocument();
  });

  it("are the 404 page for a module that's off, and for an address no one has", async () => {
    const { unmount } = renderApp({ path: "/blog", modules: [blog], on: [] });
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    unmount();
    renderApp({ path: "/nowhere" });
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(document.title).toBe("Page not found · Test Site");
  });

  it("are each kernel page's heading until its screen is built", async () => {
    renderApp({ path: "/sign-in" });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(document.title).toBe("Sign in · Test Site");
  });

  it("match with case, as the server does (cubic on #79)", async () => {
    renderApp({ path: "/Sign-In" });
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("say the site can't be reached, with a way to try again, when the modules on can't be read (cubic, CodeRabbit on #79)", async () => {
    routedFetch({});
    renderApp({ path: "/blog", modules: [blog], on: "loading" });
    expect(await screen.findByRole("heading", { name: "The site can't be reached" })).toBeInTheDocument();
    routedFetch({ "GET /api/kernel/modules": { status: 200, body: { on: ["blog"] } } });
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "The blog" })).toBeInTheDocument();
  });

  it("say so on the home page when the site's identity can't be read (CodeRabbit on #79)", async () => {
    routedFetch({});
    renderApp({ site: "loading" });
    expect(await screen.findByRole("heading", { name: "The site can't be reached" })).toBeInTheDocument();
  });

  it("are the 404 page for a module switched off while the app is open, before any sign-in or permission (cubic, CodeRabbit on #79)", async () => {
    const off = { on: [] };
    const member = renderApp({ modules: [blog] });
    await screen.findByRole("heading", { name: "Test Site" });
    act(() => {
      member.queryClient.setQueryData(["get", "/api/kernel/modules"], off);
    });
    await act(() => member.router.navigate("/blog/drafts"));
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(at(member.router)).toBe("/blog/drafts");
    member.unmount();
    const admin = renderApp({ modules: [blog], session: staff });
    await screen.findByRole("heading", { name: "Test Site" });
    act(() => {
      admin.queryClient.setQueryData(["get", "/api/kernel/modules"], off);
    });
    await act(() => admin.router.navigate("/admin/blog"));
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

describe("the member pages", () => {
  it("send a signed-out person to sign in, and back here after", async () => {
    const { router } = renderApp({ path: "/blog/drafts?sort=new", modules: [blog] });
    await waitFor(() => {
      expect(at(router)).toBe("/sign-in?next=%2Fblog%2Fdrafts%3Fsort%3Dnew");
    });
  });

  it("show a signed-in person the page", async () => {
    renderApp({ path: "/account", session: testUser() });
    expect(await screen.findByRole("heading", { name: "Your account" })).toBeInTheDocument();
  });

  it("wait quietly while the session is read", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    renderApp({ path: "/account", session: "loading" });
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("say so, with a way to try again, when the site can't be reached", async () => {
    routedFetch({});
    renderApp({ path: "/account", session: "loading" });
    expect(await screen.findByRole("heading", { name: "The site can't be reached" })).toBeInTheDocument();
    expect(screen.getByText("Check your connection, then try again.")).toBeInTheDocument();
    routedFetch({ "GET /api/auth/session": { status: 200, body: { user: testUser() } } });
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Your account" })).toBeInTheDocument();
  });
});

describe("the admin", () => {
  it("is the 404 page to a member, in the site's frame", async () => {
    renderApp({ path: "/admin", session: testUser() });
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Site" })).toBeInTheDocument();
  });

  it("sends staff without a second factor to add one", async () => {
    const { router } = renderApp({ path: "/admin", session: { ...staff, second_factor: false } });
    await waitFor(() => {
      expect(at(router)).toBe("/account?needs=second-factor");
    });
  });

  it("sends a signed-out person to sign in", async () => {
    const { router } = renderApp({ path: "/admin/people" });
    await waitFor(() => {
      expect(at(router)).toBe("/sign-in?next=%2Fadmin%2Fpeople");
    });
  });

  it("shows staff the dashboard and the sidebar in its order", async () => {
    renderApp({ path: "/admin", session: { ...staff, permissions: ["auth.user.manage", "blog.post.write"] }, modules: [blog] });
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Admin" });
    const links = [...nav.querySelectorAll("a")].map((link) => link.textContent);
    expect(links).toEqual(["Dashboard", "Posts", "People", "Roles", "View site"]);
  });

  it("shows the no-access page, at the same address, without the permission", async () => {
    const { router } = renderApp({ path: "/admin/blog", session: staff, modules: [blog] });
    expect(await screen.findByRole("heading", { name: "You can't open this page" })).toBeInTheDocument();
    expect(at(router)).toBe("/admin/blog");
  });

  it("shows a module's admin page with the permission", async () => {
    renderApp({ path: "/admin/blog", session: { ...staff, permissions: ["blog.post.write"] }, modules: [blog] });
    expect(await screen.findByRole("heading", { name: "Posts" })).toBeInTheDocument();
  });

  it("is the 404 page in its own frame for an admin address no one has", async () => {
    renderApp({ path: "/admin/nowhere", session: staff });
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Admin" })).toBeInTheDocument();
  });
});

describe("moving between pages", () => {
  it("puts the focus on the new page's heading", async () => {
    const { router } = renderApp({ modules: [blog] });
    await screen.findByRole("heading", { name: "Test Site" });
    await act(() => router.navigate("/blog"));
    const heading = await screen.findByRole("heading", { name: "The blog" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
  });

  it("waits for a page whose code comes later than a frame, then focuses its heading (Codex on #79)", async () => {
    const slow = defineModule({
      id: "slow",
      routes: {
        public: [
          {
            path: "/slow",
            lazy: () =>
              new Promise((resolve) => {
                setTimeout(() => {
                  resolve({ default: () => <h1>Late heading</h1> });
                }, 120);
              }),
          },
        ],
        member: [],
        admin: [],
      },
    });
    const { router } = renderApp({ modules: [slow] });
    await screen.findByRole("heading", { name: "Test Site" });
    await act(() => router.navigate("/slow"));
    const heading = await screen.findByRole("heading", { name: "Late heading" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
  });

  it("keeps the restored scroll on back and forward, focusing without scrolling (cubic on #79)", async () => {
    const focused = vi.spyOn(HTMLElement.prototype, "focus");
    const { router } = renderApp({ modules: [blog] });
    await screen.findByRole("heading", { name: "Test Site" });
    await act(() => router.navigate("/blog"));
    await screen.findByRole("heading", { name: "The blog" });
    await waitFor(() => {
      expect(focused).toHaveBeenLastCalledWith({ preventScroll: false });
    });
    await act(() => router.navigate(-1));
    const home = await screen.findByRole("heading", { name: "Test Site" });
    await waitFor(() => {
      expect(home).toHaveFocus();
    });
    expect(focused).toHaveBeenLastCalledWith({ preventScroll: true });
  });

  it("leaves the first page's focus alone under StrictMode, which runs effects twice (cubic on #79)", async () => {
    renderApp({ strict: true, site: { name: "Strict" } });
    const heading = await screen.findByRole("heading", { name: "Strict" });
    await new Promise((settle) => setTimeout(settle, 50));
    expect(heading).not.toHaveFocus();
  });

  it("focuses the page's main area when it has no heading after a while", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const bare = defineModule({
        id: "bare",
        routes: { public: [{ path: "/bare", lazy: () => Promise.resolve({ default: () => <span>No heading</span> }) }], member: [], admin: [] },
      });
      const { router } = renderApp({ modules: [bare] });
      await screen.findByRole("heading", { name: "Test Site" });
      await act(() => router.navigate("/bare"));
      await screen.findByText("No heading");
      await act(() => vi.advanceTimersByTimeAsync(FOCUS_WAIT_MS + 50));
      expect(screen.getByRole("main")).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it("signs out from the frame and goes home", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))),
    );
    const { router } = renderApp({ path: "/account", session: testUser() });
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => {
      expect(at(router)).toBe("/");
    });
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("a page that fails", () => {
  it("offers a reload when its code didn't arrive", async () => {
    const broken = defineModule({
      id: "broken",
      routes: {
        public: [{ path: "/broken", lazy: () => Promise.reject(new TypeError("Failed to fetch dynamically imported module: /assets/x.js")) }],
        member: [],
        admin: [],
      },
    });
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderApp({ path: "/broken", modules: [broken] });
    expect(await screen.findByRole("heading", { name: "This page has changed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("says so for anything else", async () => {
    const broken = defineModule({
      id: "broken",
      routes: {
        public: [
          {
            path: "/broken",
            lazy: () =>
              Promise.resolve({
                default: () => {
                  throw new Error("boom");
                },
              }),
          },
        ],
        member: [],
        admin: [],
      },
    });
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderApp({ path: "/broken", modules: [broken] });
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
  });

  it("tells missing code from other failures", () => {
    expect(isMissingCode(new TypeError("Failed to fetch dynamically imported module: /a.js"))).toBe(true);
    expect(isMissingCode(new Error("Importing a module script failed."))).toBe(true);
    expect(isMissingCode(new Error("boom"))).toBe(false);
    expect(isMissingCode("text")).toBe(false);
  });
});
