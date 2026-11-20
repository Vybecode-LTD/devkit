/**
 * The site's own pages (K5 contract change 5, decision 0048): `defineSite` and
 * `mountApp({ site })`. They're always on, with no switch on Features, and win
 * a tie with a module's route; a more fixed module route still wins.
 */
import { act, screen } from "@testing-library/react";
import type { Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { renderApp, renderWithKernel, testUser } from "../../testing";
import { mountApp } from "../app/mount";
import { defineModule, defineSite, type SiteDefinition } from "../modules";
import { SlotOutlet } from "../slots/slots";
import { problem, routedFetch } from "../test-fetch";
import { SITE } from "./site";

function pageSaying(words: string) {
  return () => Promise.resolve({ default: () => <h1>{words}</h1> });
}

function site(changes: Partial<SiteDefinition> = {}): SiteDefinition {
  return {
    routes: {
      public: [
        { path: "/", lazy: pageSaying("Our own home") },
        { path: "/:page", lazy: pageSaying("One of our pages") },
      ],
      member: [{ path: "/library", lazy: pageSaying("Your library") }],
    },
    slots: { "nav.public": [{ label: "About us", to: "/about" }] },
    ...changes,
  };
}

const landing = defineModule({
  id: "landing",
  routes: { public: [{ path: "/", lazy: pageSaying("The landing page") }], member: [], admin: [] },
});

const shop = defineModule({
  id: "shop",
  routes: {
    public: [
      { path: "/shop", lazy: pageSaying("The shop") },
      { path: "/:product", lazy: pageSaying("A product") },
    ],
    member: [],
    admin: [],
  },
});

describe("defineSite", () => {
  it("gives back the site it's given", () => {
    const given = site();
    expect(defineSite(given)).toBe(given);
    expect(SITE).toBe("site");
  });

  it("refuses a route that takes a kernel page", () => {
    const routes = { public: [{ path: "/account/:tab", lazy: pageSaying("Mine") }], member: [] };
    expect(() => defineSite(site({ routes }))).toThrow(/site's route \/account\/:tab takes the kernel's page/);
  });

  it("refuses a route under /admin", () => {
    const routes = { public: [], member: [{ path: "/admin/mine", lazy: pageSaying("Mine") }] };
    expect(() => defineSite(site({ routes }))).toThrow(/under \/admin/);
  });

  it("refuses a path given twice", () => {
    const routes = { public: [{ path: "/about", lazy: pageSaying("A") }], member: [{ path: "/about", lazy: pageSaying("B") }] };
    expect(() => defineSite(site({ routes }))).toThrow(/gives the path \/about twice/);
  });

  it("refuses a link that leaves the site", () => {
    expect(() => defineSite(site({ slots: { "nav.public": [{ label: "Out", to: "https://elsewhere.test" }] } }))).toThrow(
      /must go to a path on this site/,
    );
  });

  it("refuses the site's id as a module's", () => {
    expect(() => defineModule({ ...landing, id: SITE })).toThrow(/the kernel's own/);
  });
});

describe("the site's pages", () => {
  it("answer / before a module's page there and the kernel's home", async () => {
    renderApp({ modules: [landing], sitePages: site() });
    expect(await screen.findByRole("heading", { name: "Our own home" })).toBeInTheDocument();
  });

  it("answer whatever modules are on", async () => {
    renderApp({ modules: [shop], on: [], sitePages: site(), path: "/shop" });
    expect(await screen.findByRole("heading", { name: "One of our pages" })).toBeInTheDocument();
  });

  it("answer while it isn't known which modules are on", async () => {
    renderApp({ modules: [landing], on: "loading", sitePages: site() });
    expect(await screen.findByRole("heading", { name: "Our own home" })).toBeInTheDocument();
  });

  it("win a tie with a module's route", async () => {
    renderApp({ modules: [shop], sitePages: site(), path: "/about" });
    expect(await screen.findByRole("heading", { name: "One of our pages" })).toBeInTheDocument();
  });

  it("win a tie with a module's route of another kind: the site's member page over a module's public one (Codex on #92)", async () => {
    const shelf = defineModule({
      id: "shelf",
      routes: { public: [{ path: "/library", lazy: pageSaying("The shelf") }], member: [], admin: [] },
    });
    renderApp({ modules: [shelf], sitePages: site(), path: "/library", session: testUser() });
    expect(await screen.findByRole("heading", { name: "Your library" })).toBeInTheDocument();
  });

  it("lose to a more fixed module route", async () => {
    renderApp({ modules: [shop], sitePages: site(), path: "/shop" });
    expect(await screen.findByRole("heading", { name: "The shop" })).toBeInTheDocument();
  });

  it("keep a member page behind sign-in", async () => {
    const { router } = renderApp({ sitePages: site(), path: "/library" });
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname + router.state.location.search).toBe("/sign-in?next=%2Flibrary");
  });
});

describe("the site's member home page (CodeRabbit on #92)", () => {
  const members = site({
    routes: { public: [], member: [{ path: "/", lazy: pageSaying("Members' home") }] },
  });

  it("is the site's, over a module's public home, for someone signed in", async () => {
    renderApp({ modules: [landing], sitePages: members, session: testUser() });
    expect(await screen.findByRole("heading", { name: "Members' home" })).toBeInTheDocument();
  });

  it("asks someone signed out to sign in", async () => {
    const { router } = renderApp({ modules: [landing], sitePages: members });
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    // Home is where signing in lands anyway, so no `next` (guards/next.ts).
    expect(router.state.location.pathname + router.state.location.search).toBe("/sign-in");
  });
});

describe("the site's slots", () => {
  it("show its links whatever modules are on", async () => {
    renderWithKernel(<SlotOutlet name="nav.public" label="Menu" />, { modules: [landing], on: [], sitePages: site() });
    expect(await screen.findByRole("link", { name: "About us" })).toHaveAttribute("href", "/about");
  });

  it("show its links while it isn't known which modules are on, and no module's (CodeRabbit on #92)", async () => {
    const linked = defineModule({ ...landing, id: "linked", slots: { "nav.public": [{ label: "Shop", to: "/shop" }] } });
    renderWithKernel(<SlotOutlet name="nav.public" label="Menu" />, { modules: [linked], on: "loading", sitePages: site() });
    expect(await screen.findByRole("link", { name: "About us" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Shop" })).toBeNull();
  });
});

describe("mountApp with the site's pages", () => {
  const mounted: Root[] = [];

  afterEach(() => {
    for (const root of mounted.splice(0))
      act(() => {
        root.unmount();
      });
    document.body.innerHTML = "";
  });

  it("draws the site's home page", async () => {
    routedFetch({
      "GET /api/kernel/site": {
        status: 200,
        body: { name: "Mounted", description: "", kind: "Organization", logo: "", card_image: "", same_as: [] },
      },
      "GET /api/kernel/modules": { status: 200, body: { on: [] } },
      "GET /api/auth/session": problem(401, "kernel.not_signed_in"),
    });
    document.body.innerHTML = '<div id="root"></div>';
    mounted.push(await mountApp({ modules: [landing], site: site() }));
    expect(await screen.findByRole("heading", { name: "Our own home" })).toBeInTheDocument();
  });

  it("refuses a site whose routes it can't take", () => {
    document.body.innerHTML = '<div id="root"></div>';
    const routes = { public: [{ path: "/sign-in", lazy: pageSaying("Ours") }], member: [] };
    expect(() => mountApp({ modules: [], site: site({ routes }) })).toThrow(/takes the kernel's page/);
  });
});
