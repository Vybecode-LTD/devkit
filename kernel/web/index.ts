/**
 * The kernel's web half: its public surface (SPEC.md section 6).
 *
 * Modules import from "@/kernel" only. Everything else under kernel/web is
 * private and may change in any release. Built so far: defineModule and the
 * typed API client; K4 adds the app shell, useSession, the guards and the UI kit.
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
export type { ModuleDefinition, ModuleRoute, SlotEntry } from "./src/modules";
