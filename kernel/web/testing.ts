/**
 * Test helpers for the kernel's and every module's component tests (K4
 * contract §2). Imported from tests only ("@/kernel/testing"), never from a
 * page, so none of it reaches a visitor's bundle.
 *
 * `renderWithKernel(ui, options)` draws `ui` at `path` inside everything a
 * page has: the query cache, the session, the modules on and the site, all
 * given, so nothing is fetched unless the test means it. `renderApp` draws
 * the whole router at `path`.
 */
import { QueryClient } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { StrictMode, createElement, type ReactElement } from "react";
import { RouterProvider, createMemoryRouter } from "react-router";

import type { AdminSection } from "./src/app/context";
import { KernelProviders, drawNow } from "./src/app/mount";
import { buildRoutes } from "./src/app/routes";
import type { ModuleDefinition } from "./src/modules";
import { SESSION_KEY, type SessionUser } from "./src/session/session";
import type { Site } from "./src/site/site";

export type KernelRenderOptions = {
  /** The address the page is drawn at; `/` by default. */
  path?: string;
  /** Who's signed in: `null` (the default) for no one, `"loading"` for not read yet. */
  session?: SessionUser | null | "loading";
  /** The modules' bindings. */
  modules?: ModuleDefinition[];
  /** The modules on; every module given by default; `"loading"` for not read yet. */
  on?: string[] | "loading";
  /** The site's identity, over `TEST_SITE`; `"loading"` for not read yet. */
  site?: Partial<Site> | "loading";
  adminSections?: AdminSection[];
  /** Draw inside React's StrictMode, as `mountApp` does. */
  strict?: boolean;
};

export type KernelRender = RenderResult & {
  queryClient: QueryClient;
  router: ReturnType<typeof createMemoryRouter>;
};

export const TEST_SITE: Site = {
  name: "Test Site",
  description: "",
  kind: "Organization",
  logo: "",
  card_image: "",
  same_as: [],
};

/** A signed-in person: a member with nothing extra, unless `overrides` says otherwise. */
export function testUser(overrides: Partial<SessionUser> = {}): SessionUser {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    email: "member@mechframe.test",
    roles: ["member"],
    permissions: [],
    verified: true,
    second_factor: false,
    ...overrides,
  };
}

/**
 * A query cache that never retries and never reads again on its own: not on
 * focus, on reconnect or on a remount, whatever a query's own `staleTime`
 * (cubic on #79). What's given is in it; what's `"loading"` is read when asked.
 */
export function testQueryClient(options: KernelRenderOptions = {}): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
        gcTime: Infinity,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        refetchOnMount: false,
      },
    },
  });
  if (options.session !== "loading") queryClient.setQueryData(SESSION_KEY, options.session ?? null);
  if (options.site !== "loading") queryClient.setQueryData(["get", "/api/kernel/site"], { ...TEST_SITE, ...options.site });
  if (options.on !== "loading") {
    const on = options.on ?? (options.modules ?? []).map((module) => module.id);
    queryClient.setQueryData(["get", "/api/kernel/modules"], { on });
  }
  return queryClient;
}

function drawn(router: ReturnType<typeof createMemoryRouter>, options: KernelRenderOptions): KernelRender {
  const queryClient = testQueryClient(options);
  const setup = { modules: options.modules ?? [], adminSections: options.adminSections ?? [] };
  const app = createElement(KernelProviders, { queryClient, setup, children: createElement(RouterProvider, { router, flushSync: drawNow }) });
  const result = render(options.strict ? createElement(StrictMode, null, app) : app);
  return { ...result, queryClient, router };
}

/** `ui` at `options.path`, with the kernel around it. */
export function renderWithKernel(ui: ReactElement, options: KernelRenderOptions = {}): KernelRender {
  const router = createMemoryRouter([{ path: "*", element: ui }], { initialEntries: [options.path ?? "/"] });
  return drawn(router, options);
}

/** The whole app, the kernel's routes and the modules', at `options.path`. */
export function renderApp(options: KernelRenderOptions = {}): KernelRender {
  const modules = options.modules ?? [];
  // As mountApp: the modules on's routes, or every module's while it's not read.
  const on = options.on === "loading" ? undefined : new Set(options.on ?? modules.map((module) => module.id));
  const router = createMemoryRouter(buildRoutes(modules, on), { initialEntries: [options.path ?? "/"] });
  return drawn(router, options);
}
