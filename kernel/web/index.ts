/**
 * The kernel's web half: its public surface (SPEC.md section 6).
 *
 * Modules import from "@/kernel" only (and their tests from
 * "@/kernel/testing"). Everything else under kernel/web is private and may
 * change in any release. Built so far: the typed API client, `defineModule`
 * and the app shell (`mountApp`, the session, the guards, the slots, the
 * site, `<Seo>`), the UI kit (`src/ui/`) and the admin's `AdminPage`; K4
 * goes on with the screens.
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
export { defineModule, defineSite } from "./src/modules";
export type { ModuleDefinition, ModuleRoute, SiteDefinition } from "./src/modules";
export type { AdminLinkEntry, IconName, Lazy, LinkEntry, SlotName, Slots } from "./src/slots/types";

export { mountApp } from "./src/app/mount";
export type { AppOptions } from "./src/app/mount";
export type { AdminSection } from "./src/app/context";

export { useSession, useSignOut } from "./src/session/session";
export type { Session, SessionUser } from "./src/session/session";
export { RequireAuth, RequirePermission } from "./src/guards/guards";
export { useSlot, SlotOutlet } from "./src/slots/slots";
export { useModuleEnabled, useSite } from "./src/site/site";
export type { Site } from "./src/site/site";
// A settings section's admin form, for a module's admin.settings.section part (K4.8).
export { useSettings } from "./src/settings/useSettings";
export type { SaveOutcome, SettingsForm, SettingsValues } from "./src/settings/useSettings";
export { Seo } from "./src/seo/Seo";
export type { SeoProps } from "./src/seo/Seo";

// The admin's page header, for a module's admin pages too (K4.6, decision 0044).
export { AdminPage } from "./src/admin/AdminPage";
export type { AdminPageProps } from "./src/admin/AdminPage";

// The UI kit (K4 contract §4 item 4; src/ui/README.md).
export * from "./src/ui";
