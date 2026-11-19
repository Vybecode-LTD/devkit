/**
 * `mountApp` (K4 contract §2): the site's web app, mounted with `createRoot`
 * (never `hydrateRoot`: the server's words are a crawler's copy, not React's
 * markup). React's first render replaces them; `server-copy.css` hides them
 * until then for a browser that runs scripts.
 */
import "./server-copy.css";
import "./frames.css";
import "../ui/kit.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { flushSync } from "react-dom";
import { RouterProvider, createBrowserRouter } from "react-router";

import { apiQueryOptions, retryUnlessRefused } from "../api/client";
import { defineModule, type ModuleDefinition } from "../modules";
import { StepUpProvider } from "../auth/StepUp";
import { SessionHandlers } from "../session/session";
import { ToastProvider } from "../ui/Toast";
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

/** What every page shares: the query cache, the setup the slots read, the session's handlers, the step-up dialog, the toasts. */
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
        <SessionHandlers>
          <StepUpProvider>
            <ToastProvider>{children}</ToastProvider>
          </StepUpProvider>
        </SessionHandlers>
      </KernelContext.Provider>
    </QueryClientProvider>
  );
}

/**
 * React Router's `flushSync` prop: ReactDOM's, as `react-router/dom`'s provider
 * passes it, so a move that asks (`navigate(to, {flushSync: true})`) is drawn at
 * once rather than in a transition. Given here, the app and the tests use one
 * build of React Router, not its DOM entry's second copy under Node.
 */
export function drawNow(update: () => unknown): undefined {
  flushSync(update);
  return undefined;
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

/**
 * Which modules are on, read once before the router is built so its routes
 * are the modules on's (`buildRoutes`); `undefined` if it can't be read, and
 * then every module's routes stand, each page waiting on its own switch. Read
 * without the cache's retries: the server's words stay up meanwhile, and a
 * slow answer shouldn't keep the app away.
 */
async function modulesOn(queryClient: QueryClient): Promise<ReadonlySet<string> | undefined> {
  try {
    const { on } = await queryClient.query({ ...apiQueryOptions("get", "/api/kernel/modules"), retry: false });
    return new Set(on);
  } catch {
    return undefined;
  }
}

/**
 * Mounts the app. The page and the modules are checked at once (a mistake
 * throws here); the app draws once it knows which modules are on. Gives the
 * React root, for a host page or a test to unmount (cubic on #79).
 */
export function mountApp(options: AppOptions): Promise<Root> {
  const root = options.root ?? document.getElementById("root");
  if (!root) throw new Error("The page has no #root to mount the app in.");
  checkModules(options.modules);
  const setup: KernelSetup = { modules: options.modules, adminSections: options.adminSections ?? [] };
  const queryClient = kernelQueryClient();
  return modulesOn(queryClient).then((on) => {
    const router = createBrowserRouter(buildRoutes(setup.modules, on));
    const app = createRoot(root);
    app.render(
      <StrictMode>
        <KernelProviders queryClient={queryClient} setup={setup}>
          {/* flushSync: a move that asks for it is drawn at once, not in a transition (the frame's Sign out). */}
          <RouterProvider router={router} flushSync={drawNow} />
        </KernelProviders>
      </StrictMode>,
    );
    return app;
  });
}
