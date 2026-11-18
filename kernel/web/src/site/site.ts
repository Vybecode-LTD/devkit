/**
 * What the site is and which modules are on (K4 contract §2): `useSite` and
 * `useModuleEnabled`, from `GET /api/kernel/site` and `GET /api/kernel/modules`.
 */
import { useApiQuery } from "../api/client";
import type { components } from "../api/schema";

export type Site = components["schemas"]["Site"];

/** Both change only when staff change them: read again after five minutes. */
const SETTLED = 5 * 60_000;

/** The site's name and identity; `undefined` until it's read. */
export function useSite(): Site | undefined {
  return useApiQuery("get", "/api/kernel/site", undefined, { staleTime: SETTLED }).data;
}

/** The modules on; `undefined` until it's read. */
export function useModulesOn(): ReadonlySet<string> | undefined {
  const { data } = useApiQuery("get", "/api/kernel/modules", undefined, {
    staleTime: SETTLED,
    select: (answer) => new Set(answer.on),
  });
  return data;
}

/** Whether the module `id` is on; `undefined` until it's known. */
export function useModuleEnabled(id: string): boolean | undefined {
  return useModulesOn()?.has(id);
}
