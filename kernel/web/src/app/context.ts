/**
 * What `mountApp` was given, for the slots and the router to read.
 */
import { createContext, useContext } from "react";

import type { ModuleDefinition } from "../modules";
import type { IconName } from "../slots/types";

/** The sidebar's order and icons for module sections. */
export type AdminSection = { label: string; icon: IconName };

export type KernelSetup = {
  modules: readonly ModuleDefinition[];
  adminSections: readonly AdminSection[];
};

export const KernelContext = createContext<KernelSetup>({ modules: [], adminSections: [] });

export function useKernelSetup(): KernelSetup {
  return useContext(KernelContext);
}
