/**
 * The kernel's web half: its public surface (SPEC.md section 6).
 *
 * Modules import from "@/kernel" only. Everything else under kernel/web is
 * private and may change in any release. K4 fills this in: the app shell,
 * useSession, the typed API client, the guards and the UI kit.
 */
export { KERNEL_WEB_VERSION } from "./src/version";
export { defineModule } from "./src/modules";
export type { ModuleDefinition, ModuleRoute, SlotEntry } from "./src/modules";
