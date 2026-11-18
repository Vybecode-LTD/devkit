import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { defineModule, type ModuleDefinition } from "../modules";
import { problem, routedFetch } from "../test-fetch";
import { checkModules, kernelQueryClient, mountApp } from "./mount";

const site = { name: "Mounted", description: "Words from the API.", kind: "Organization", logo: "", card_image: "", same_as: [] };

afterEach(() => {
  document.body.innerHTML = "";
});

describe("mountApp", () => {
  it("mounts into #root with createRoot, replacing the server's words", async () => {
    routedFetch({
      "GET /api/kernel/site": { status: 200, body: site },
      "GET /api/kernel/modules": { status: 200, body: { on: [] } },
      "GET /api/auth/session": problem(401, "kernel.not_signed_in"),
    });
    document.body.innerHTML = '<div id="root"><div data-server-copy><h1>The server\'s words</h1></div></div>';
    await mountApp({ modules: [] });
    expect(await screen.findByRole("heading", { name: "Mounted" })).toBeInTheDocument();
    expect(document.querySelector("[data-server-copy]")).toBeNull();
    expect(screen.getByText("Words from the API.")).toBeInTheDocument();
  });

  it("builds its routes from the modules on, so one that's off never keeps an address (Codex on #79)", async () => {
    routedFetch({
      "GET /api/kernel/site": { status: 200, body: site },
      "GET /api/kernel/modules": { status: 200, body: { on: ["pages"] } },
      "GET /api/auth/session": problem(401, "kernel.not_signed_in"),
    });
    const posts = defineModule({
      id: "posts",
      routes: { public: [{ path: "/blog/:slug", lazy: () => Promise.resolve({ default: () => <h1>A post</h1> }) }], member: [], admin: [] },
    });
    const pages = defineModule({
      id: "pages",
      routes: { public: [{ path: "/:section/:slug", lazy: () => Promise.resolve({ default: () => <h1>A page</h1> }) }], member: [], admin: [] },
    });
    history.pushState(null, "", "/blog/hello");
    document.body.innerHTML = '<div id="root"></div>';
    try {
      await mountApp({ modules: [posts, pages] });
      expect(await screen.findByRole("heading", { name: "A page" })).toBeInTheDocument();
    } finally {
      history.pushState(null, "", "/");
    }
  });

  it("builds its routes from every module when it can't read which are on", async () => {
    routedFetch({ "GET /api/kernel/site": { status: 200, body: site } });
    const posts = defineModule({
      id: "posts",
      routes: { public: [{ path: "/blog/:slug", lazy: () => Promise.resolve({ default: () => <h1>A post</h1> }) }], member: [], admin: [] },
    });
    history.pushState(null, "", "/blog/hello");
    document.body.innerHTML = '<div id="root"></div>';
    try {
      await mountApp({ modules: [posts] });
      // Its page waits for the switch it can't read: nothing, rather than a 404 that may be wrong.
      expect(await screen.findByRole("navigation", { name: "Site" })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Page not found" })).toBeNull();
    } finally {
      history.pushState(null, "", "/");
    }
  });

  it("mounts where it's told", async () => {
    routedFetch({ "GET /api/kernel/site": { status: 200, body: site } });
    const root = document.body.appendChild(document.createElement("section"));
    await mountApp({ modules: [], root });
    expect(await screen.findByRole("heading", { name: "Mounted" })).toBeInTheDocument();
    expect(root).not.toBeEmptyDOMElement();
  });

  it("refuses a page without #root", () => {
    expect(() => {
      void mountApp({ modules: [] });
    }).toThrow(/no #root/);
  });
});

describe("the modules given", () => {
  const blog = defineModule({ id: "blog", routes: { public: [], member: [], admin: [] } });

  it("are each given once", () => {
    expect(() => {
      checkModules([blog, blog]);
    }).toThrow(/given twice/);
  });

  it("are checked again, for a binding that skipped defineModule", () => {
    const unchecked = { id: "Bad Id", routes: { public: [], member: [], admin: [] } } as ModuleDefinition;
    expect(() => {
      checkModules([unchecked]);
    }).toThrow(/isn't a module id/);
  });
});

describe("the app's query cache", () => {
  it("never asks a refusal again", () => {
    const retry = kernelQueryClient().getDefaultOptions().queries?.retry;
    expect(typeof retry).toBe("function");
  });
});
