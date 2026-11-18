/**
 * The kernel's web half: its public surface (SPEC.md section 6).
 *
 * Modules import from "@/kernel" only (and their tests from
 * "@/kernel/testing"). Everything else under kernel/web is private and may
 * change in any release. Built so far: the typed API client, `defineModule`
 * and the app shell (`mountApp`, the session, the guards, the slots, the
 * site, `<Seo>`); K4 goes on with the themes, the UI kit and the screens.
 */
export { KERNEL_WEB_VERSION } from "./src/version";
export {
  ApiProblem,
  api,
  apiQueryOptions,
  createApiClient,
  useApiMutation,
  useApiQuery,
} from "./src/api/client";
export type { ApiClientOptions, KernelPaths, ProblemBody } from "./src/api/client";
export { defineModule } from "./src/modules";
export type { ModuleDefinition, ModuleRoute } from "./src/modules";
export type { AdminLinkEntry, IconName, Lazy, LinkEntry, SlotName, Slots } from "./src/slots/types";

export { mountApp } from "./src/app/mount";
export type { AppOptions } from "./src/app/mount";
export type { AdminSection } from "./src/app/context";
export { ErrorBoundary } from "./src/app/ErrorBoundary";
export { RouteFocus } from "./src/app/RouteFocus";

export { useSession, useSignOut } from "./src/session/session";
export type { Session, SessionUser } from "./src/session/session";
export { RequireAuth, RequirePermission } from "./src/guards/guards";
export { useSlot, SlotOutlet } from "./src/slots/slots";
export { useModuleEnabled, useSite } from "./src/site/site";
export type { Site } from "./src/site/site";
export { Seo } from "./src/seo/Seo";
export type { SeoProps } from "./src/seo/Seo";
