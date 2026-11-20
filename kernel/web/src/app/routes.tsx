/**
 * The router's routes (K4 contract §2): a data router, which the
 * unsaved-changes guard needs.
 *
 * - The sign-in frame holds the kernel's public pages: signing in and up,
 *   and the landings from mail (VM Website `Auth.dc.html`).
 * - The site frame holds `/` (a module's page if one on owns it, else the
 *   kernel's home), the modules' public pages, and, behind `RequireAuth`,
 *   the kernel's and the modules' member pages.
 * - The admin frame, behind `RequireAdmin`, holds the kernel's admin pages
 *   and the modules', each behind its permission.
 * - Anything else is the 404 page, in its frame.
 *
 * Every module page loads lazily, and a module that's off is the 404 page.
 * The site's own pages (`mountApp({ site })`, decision 0048) come first among
 * the modules', so they win a tie, and are always on.
 */
import { Suspense, type ComponentType, type ReactNode } from "react";
import type { RouteObject } from "react-router";

import { RequireAdmin, RequireAuth, RequirePermission } from "../guards/guards";
import { SITE, type ModuleDefinition, type ModuleRoute } from "../modules";
import { useModulesRead } from "../site/site";
import { AdminFrame } from "../admin/AdminFrame";
import { AuthFrame } from "../auth/AuthFrame";
import { Root, SiteFrame } from "./frames";
import { lazyPart } from "./lazy";
import { KERNEL_PAGES, type KernelPage } from "./pages";
import { Home, NotFound, Pending, Unreachable } from "./pages/KernelPages";
import { RouteError } from "./RouteError";
import { SCREENS } from "./screens";

/** A page at `/`: its module's, and whether it's a member page, behind sign-in. */
type Owned = { module: string; page: ComponentType; member: boolean };

/**
 * A module's page waits for its switch, says so if the switch can't be read,
 * and is the 404 page while it's off: before any sign-in or permission is
 * asked for, so a module that's off is never more than a missing page
 * (cubic and CodeRabbit on #79).
 */
export function ModuleGate({ module, children }: { module: string; children: ReactNode }) {
  const found = useModulesRead();
  if (found.status === "loading") return null;
  if (found.status === "failed") return <Unreachable problem={found.problem} retry={found.retry} />;
  if (!found.value.has(module)) return <NotFound />;
  return children;
}

function Loaded({ page: Page }: { page: ComponentType }) {
  return (
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  );
}

function Owner({ owner }: { owner: Owned }) {
  const page = <Loaded page={owner.page} />;
  return owner.member ? <RequireAuth>{page}</RequireAuth> : page;
}

/**
 * `/`: the site's own page if it has one, public or member, else the first
 * module on's that declares it, else the kernel's home. A member page at `/`
 * is chosen here too, behind sign-in: the index route takes `/` before any
 * other route could (CodeRabbit on #92).
 */
function HomeRoute({ owners }: { owners: readonly Owned[] }) {
  const found = useModulesRead();
  const [first] = owners;
  if (first === undefined) return <Home />;
  if (first.module === SITE) return <Owner owner={first} />;
  if (found.status === "loading") return null;
  if (found.status === "failed") return <Unreachable problem={found.problem} retry={found.retry} />;
  const owner = owners.find((each) => found.value.has(each.module));
  return owner ? <Owner owner={owner} /> : <Home />;
}

function kernelRoute(page: KernelPage): RouteObject {
  const screen = SCREENS[page.path];
  const shown = screen ? <Loaded page={lazyPart(screen)} /> : <Pending page={page} />;
  return {
    path: page.path,
    caseSensitive: true,
    element: page.permission ? <RequirePermission permission={page.permission}>{shown}</RequirePermission> : shown,
  };
}

type Access = "public" | "member" | "admin";

/** A module's route: its switch first, then who may see it, then the page. */
function moduleRoute(module: ModuleDefinition, route: ModuleRoute, access: Access): RouteObject {
  const page = <Loaded page={lazyPart(route.lazy)} />;
  const guarded =
    access === "member" ? (
      <RequireAuth>{page}</RequireAuth>
    ) : access === "admin" && route.permission ? (
      <RequirePermission permission={route.permission}>{page}</RequirePermission>
    ) : (
      page
    );
  return {
    path: route.path,
    caseSensitive: true, // as the server matches (cubic on #79)
    // The site's own pages have no switch: they never wait for one.
    element: module.id === SITE ? guarded : <ModuleGate module={module.id}>{guarded}</ModuleGate>,
  };
}

/** The public and then the member pages of `modules`, in the site frame; `/` is `HomeRoute`'s. */
function pageRoutes(modules: readonly ModuleDefinition[]): RouteObject[] {
  return [
    ...modules.flatMap((module) =>
      module.routes.public.filter((route) => route.path !== "/").map((route) => moduleRoute(module, route, "public")),
    ),
    ...modules.flatMap((module) =>
      module.routes.member.filter((route) => route.path !== "/").map((route) => moduleRoute(module, route, "member")),
    ),
  ];
}

/**
 * The router's routes, from the modules `on` (every module given while it's
 * unknown). A module that's off has no routes at all, so its pattern never
 * keeps an address from a module on whose pattern also takes it, as the
 * server's `Routes.resolve(path, on)` has it (Codex on #79). A module switched
 * off while the app is open is still the 404 page (`ModuleGate`).
 */
export function buildRoutes(given: readonly ModuleDefinition[], on?: ReadonlySet<string>): RouteObject[] {
  const modules = on === undefined ? given : given.filter((module) => module.id === SITE || on.has(module.id));
  const kernel = (access: KernelPage["access"]) => KERNEL_PAGES.filter((page) => page.access === access);
  const dashboard = KERNEL_PAGES.find((page) => page.path === "/admin");
  const owners = modules.flatMap((module) =>
    (["public", "member"] as const).flatMap((access) =>
      module.routes[access]
        .filter((route) => route.path === "/")
        .map((route): Owned => ({ module: module.id, page: lazyPart(route.lazy), member: access === "member" })),
    ),
  );
  return [
    {
      element: <Root />,
      errorElement: <RouteError />,
      children: [
        { element: <AuthFrame />, children: kernel("public").map(kernelRoute) },
        {
          element: <SiteFrame />,
          children: [
            { index: true, element: <HomeRoute owners={owners} /> },
            // The site's own pages of either kind first, so they win any tie, as the server's (Codex on #92).
            ...pageRoutes(modules.filter((module) => module.id === SITE)),
            ...pageRoutes(modules.filter((module) => module.id !== SITE)),
            { element: <RequireAuth />, children: kernel("member").map(kernelRoute) },
            { path: "*", element: <NotFound /> },
          ],
        },
        {
          path: "/admin",
          caseSensitive: true,
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
            ...(dashboard ? [{ index: true, element: kernelRoute(dashboard).element }] : []),
            ...kernel("admin")
              .filter((page) => page !== dashboard)
              .map(kernelRoute),
            ...modules.flatMap((module) => module.routes.admin.map((route) => moduleRoute(module, route, "admin"))),
            { path: "*", element: <NotFound /> },
          ],
        },
      ],
    },
  ];
}
