/**
 * `mountApp` (K4 contract §2): the site's web app, mounted with `createRoot`
 * (never `hydrateRoot`: the server's words are a crawler's copy, not React's
 * markup). React's first render replaces them; `server-copy.css` hides them
 * until then for a browser that runs scripts.
 */
import "./server-copy.css";
import "./frames.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router";

import { retryUnlessRefused } from "../api/client";
import { defineModule, type ModuleDefinition } from "../modules";
import { SessionHandlers } from "../session/session";
import { KernelContext, type AdminSection, type KernelSetup } from "./context";
import { buildRoutes } from "./routes";

export type AppOptions = {
  /** Every module's binding (`module.web.ts`'s default export). */
  modules: ModuleDefinition[];
  /** The admin sidebar's order and icons for module sections. */
  adminSections?: AdminSection[];
  /** Where to mount; the page's `#root` by default. */
  root?: HTMLElement;
};

/** What every page shares: the query cache, the setup the slots read, the session's handlers. */
export function KernelProviders({
  queryClient,
  setup,
  children,
}: {
  queryClient: QueryClient;
  setup: KernelSetup;
  children: ReactNode;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <KernelContext.Provider value={setup}>
        <SessionHandlers>{children}</SessionHandlers>
      </KernelContext.Provider>
    </QueryClientProvider>
  );
}

/** The modules, checked again (a binding may skip defineModule), each once. */
export function checkModules(modules: readonly ModuleDefinition[]): void {
  const seen = new Set<string>();
  for (const module of modules) {
    defineModule(module);
    if (seen.has(module.id)) throw new Error(`The module ${module.id} is given twice.`);
    seen.add(module.id);
  }
}

/** The app's query cache: a refusal (any 4xx) is never asked again; a dropped call or a 5xx up to three times. */
export function kernelQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: retryUnlessRefused } } });
}

export function mountApp(options: AppOptions): void {
  const root = options.root ?? document.getElementById("root");
  if (!root) throw new Error("The page has no #root to mount the app in.");
  checkModules(options.modules);
  const setup: KernelSetup = { modules: options.modules, adminSections: options.adminSections ?? [] };
  const router = createBrowserRouter(buildRoutes(setup.modules));
  createRoot(root).render(
    <StrictMode>
      <KernelProviders queryClient={kernelQueryClient()} setup={setup}>
        <RouterProvider router={router} />
      </KernelProviders>
    </StrictMode>,
  );
}
