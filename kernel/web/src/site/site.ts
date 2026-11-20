/**
 * What the site is and which modules are on (K4 contract §2): `useSite` and
 * `useModuleEnabled`, from `GET /api/kernel/site` and `GET /api/kernel/modules`.
 *
 * `useSiteRead` and `useModulesRead` also tell a read that failed from one
 * still on its way, with a way to try again, so a page can say the site
 * can't be reached instead of staying blank (cubic and CodeRabbit on #79).
 */
import type { ApiProblem } from "../api/problem";
import { useApiQuery } from "../api/client";
import type { components } from "../api/schema";

/** The id of the site's own pages and slots, which are always on (decision 0048). */
export { SITE } from "../modules";

export type Site = components["schemas"]["Site"];

/** A read: on its way, failed with nothing to show, or read. */
export type Read<T> =
  | { status: "loading" }
  | { status: "failed"; problem: ApiProblem; retry: () => void }
  | { status: "read"; value: T };

/** Both change only when staff change them: read again after five minutes. */
const SETTLED = 5 * 60_000;

function read<T>(query: { data: T | undefined; error: ApiProblem | null; refetch: () => unknown }): Read<T> {
  if (query.data !== undefined) return { status: "read", value: query.data };
  if (query.error) {
    const { error, refetch } = query;
    return {
      status: "failed",
      problem: error,
      retry: () => {
        void refetch();
      },
    };
  }
  return { status: "loading" };
}

export function useSiteRead(): Read<Site> {
  return read(useApiQuery("get", "/api/kernel/site", undefined, { staleTime: SETTLED }));
}

export function useModulesRead(): Read<ReadonlySet<string>> {
  return read(
    useApiQuery("get", "/api/kernel/modules", undefined, {
      staleTime: SETTLED,
      select: (answer) => new Set(answer.on) as ReadonlySet<string>,
    }),
  );
}

/** The site's name and identity; `undefined` until it's read. */
export function useSite(): Site | undefined {
  const found = useSiteRead();
  return found.status === "read" ? found.value : undefined;
}

/** The modules on; `undefined` until it's read. */
export function useModulesOn(): ReadonlySet<string> | undefined {
  const found = useModulesRead();
  return found.status === "read" ? found.value : undefined;
}

/** Whether the module `id` is on; `undefined` until it's known. */
export function useModuleEnabled(id: string): boolean | undefined {
  return useModulesOn()?.has(id);
}
