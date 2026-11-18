/**
 * The router's routes (K4 contract §2): a data router, which the
 * unsaved-changes guard needs.
 *
 * - The site frame holds `/` (a module's page if one on owns it, else the
 *   kernel's home), the kernel's public pages, the modules' public pages,
 *   and, behind `RequireAuth`, the kernel's and the modules' member pages.
 * - The admin frame, behind `RequireAdmin`, holds the kernel's admin pages
 *   and the modules', each behind its permission.
 * - Anything else is the 404 page, in its frame.
 *
 * Every module page loads lazily, and a module that's off is the 404 page.
 */
import { Suspense, type ComponentType } from "react";
import type { RouteObject } from "react-router";

import { RequireAdmin, RequireAuth, RequirePermission } from "../guards/guards";
import type { ModuleDefinition, ModuleRoute } from "../modules";
import { useModuleEnabled, useModulesOn } from "../site/site";
import { AdminFrame, Root, SiteFrame } from "./frames";
import { lazyPart } from "./lazy";
import { KERNEL_PAGES, type KernelPage } from "./pages";
import { Home, NotFound, Pending } from "./pages/KernelPages";
import { RouteError } from "./RouteError";

type Owned = { module: string; page: ComponentType };

/** A module's page: nothing while it's unknown whether the module is on, the 404 page if it's off. */
export function ModulePage({ module, page: Page }: Owned) {
  const on = useModuleEnabled(module);
  if (on === undefined) return null;
  if (!on) return <NotFound />;
  return (
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  );
}

/** `/`: the page of the first module on that declares it, else the kernel's home. */
function HomeRoute({ owners }: { owners: readonly Owned[] }) {
  const on = useModulesOn();
  if (owners.length === 0) return <Home />;
  if (on === undefined) return null;
  const owner = owners.find((each) => on.has(each.module));
  return owner ? <ModulePage module={owner.module} page={owner.page} /> : <Home />;
}

function kernelRoute(page: KernelPage): RouteObject {
  const shown = <Pending page={page} />;
  return {
    path: page.path,
    element: page.permission ? <RequirePermission permission={page.permission}>{shown}</RequirePermission> : shown,
  };
}

function moduleRoute(module: ModuleDefinition, route: ModuleRoute, permission?: string): RouteObject {
  const page = <ModulePage module={module.id} page={lazyPart(route.lazy)} />;
  return {
    path: route.path,
    element: permission ? <RequirePermission permission={permission}>{page}</RequirePermission> : page,
  };
}

/**
 * The router's routes, from the modules `on` (every module given while it's
 * unknown). A module that's off has no routes at all, so its pattern never
 * keeps an address from a module on whose pattern also takes it, as the
 * server's `Routes.resolve(path, on)` has it (Codex on #79). A module switched
 * off while the app is open is still the 404 page (`ModulePage`).
 */
export function buildRoutes(given: readonly ModuleDefinition[], on?: ReadonlySet<string>): RouteObject[] {
  const modules = on === undefined ? given : given.filter((module) => on.has(module.id));
  const kernel = (access: KernelPage["access"]) => KERNEL_PAGES.filter((page) => page.access === access);
  const dashboard = KERNEL_PAGES.find((page) => page.path === "/admin");
  const owners = modules.flatMap((module) =>
    module.routes.public
      .filter((route) => route.path === "/")
      .map((route): Owned => ({ module: module.id, page: lazyPart(route.lazy) })),
  );
  return [
    {
      element: <Root />,
      errorElement: <RouteError />,
      children: [
        {
          element: <SiteFrame />,
          children: [
            { index: true, element: <HomeRoute owners={owners} /> },
            ...kernel("public").map(kernelRoute),
            ...modules.flatMap((module) =>
              module.routes.public.filter((route) => route.path !== "/").map((route) => moduleRoute(module, route)),
            ),
            {
              element: <RequireAuth />,
              children: [
                ...kernel("member").map(kernelRoute),
                ...modules.flatMap((module) => module.routes.member.map((route) => moduleRoute(module, route))),
              ],
            },
            { path: "*", element: <NotFound /> },
          ],
        },
        {
          path: "/admin",
          element: (
            <RequireAdmin
              notFound={
                <SiteFrame>
                  <NotFound />
                </SiteFrame>
              }
            >
              <AdminFrame />
            </RequireAdmin>
          ),
          children: [
            ...(dashboard ? [{ index: true, element: <Pending page={dashboard} /> }] : []),
            ...kernel("admin")
              .filter((page) => page !== dashboard)
              .map(kernelRoute),
            ...modules.flatMap((module) =>
              module.routes.admin.map((route) => moduleRoute(module, route, route.permission)),
            ),
            { path: "*", element: <NotFound /> },
          ],
        },
      ],
    },
  ];
}
