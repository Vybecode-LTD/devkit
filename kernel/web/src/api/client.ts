/**
 * The typed API client (SPEC.md section 6; K4 contract, `dev plans/contracts/k4-web-kernel.md`).
 *
 * `openapi-fetch` over the types `openapi-typescript` makes from the committed
 * `openapi.json` (`npm run api:types`), with TanStack Query hooks from
 * `openapi-react-query`. Same origin, the session cookie only: nothing else
 * authenticates a call. What every client made here does for every call:
 *
 * - An answer that isn't a success throws an `ApiProblem` (a failed network,
 *   status 0 and `kernel.unreachable`), so a screen reads `problem.code`.
 * - A 401 `kernel.not_signed_in` tells the session (`setApiHandlers`), which
 *   then shows the person signed out.
 * - A write refused with 403 `auth.step_up_required` asks the person to
 *   confirm it's them (the step-up dialog) and, if they do, sends the same
 *   request again, once. A read never asks.
 *
 * The kernel's own paths are `api`, `useApiQuery` and `useApiMutation`; a
 * module's `api.ts` makes its own with `createApiClient<paths>()` from its
 * own `openapi.json`.
 */
import createClient, { type Client, type ClientOptions, type Middleware } from "openapi-fetch";
import createQueryClient from "openapi-react-query";

import { ApiProblem } from "./problem";
import type { paths } from "./schema";

export { ApiProblem } from "./problem";
export type { ProblemBody } from "./problem";

type Handlers = {
  /** The session ended or was never there: show the person signed out. */
  signedOut: () => void;
  /** Ask the person to confirm it's them; true once they have. */
  stepUp: () => Promise<boolean>;
};

const handlers: Handlers = {
  signedOut: () => undefined,
  stepUp: () => Promise.resolve(false),
};

/** For the app shell (the session, the step-up dialog) and tests; not for modules. */
export function setApiHandlers(given: Partial<Handlers>): void {
  Object.assign(handlers, given);
}

const READS = new Set(["GET", "HEAD", "OPTIONS"]);

type Fetch = (input: Request) => Promise<Response>;

function problems(send: Fetch): Middleware {
  // A copy of each write, made before it's sent (sending uses its body up),
  // so a write refused for a step-up can be sent again.
  const copies = new WeakMap<Request, Request>();
  return {
    onRequest({ request }) {
      if (!READS.has(request.method)) copies.set(request, request.clone());
      return undefined;
    },
    async onResponse({ request, response }) {
      if (response.ok) return undefined;
      let answer = response;
      const copy = copies.get(request);
      if (response.status === 403 && copy) {
        const refused = await ApiProblem.from(response.clone());
        if (refused.code === "auth.step_up_required" && (await handlers.stepUp())) {
          // Sent from here, outside openapi-fetch's own sending, so its onError
          // never sees a failure: make one a problem here (Codex on #78).
          try {
            answer = await send(copy);
          } catch {
            throw ApiProblem.unreachable();
          }
          if (answer.ok) return answer;
        }
      }
      const problem = await ApiProblem.from(answer);
      if (problem.status === 401 && problem.code === "kernel.not_signed_in") handlers.signedOut();
      throw problem;
    },
    onError({ error }) {
      return error instanceof ApiProblem ? error : ApiProblem.unreachable();
    },
  };
}

export type ApiClientOptions = {
  /** For tests: the fetch to send with. */
  fetch?: Fetch;
  /** For tests: the site's origin. The page's own by default. */
  baseUrl?: string;
};

/** A typed client for one `openapi.json`'s paths, with its hooks. */
export function createApiClient<Paths extends object>(options: ApiClientOptions = {}) {
  const send: Fetch = options.fetch ?? ((request) => globalThis.fetch(request));
  const settings: ClientOptions = {
    baseUrl: options.baseUrl ?? (typeof location === "undefined" ? "" : location.origin),
    credentials: "same-origin",
    fetch: send,
  };
  const api: Client<Paths> = createClient<Paths>(settings);
  api.use(problems(send));
  const hooks = createQueryClient(api);
  return {
    api,
    /** `useApiQuery("get", "/api/...", init?, options?)`: TanStack Query's `useQuery`, typed. */
    useApiQuery: hooks.useQuery,
    /** `useApiMutation("post", "/api/...", options?)`: TanStack Query's `useMutation`, typed. */
    useApiMutation: hooks.useMutation,
    /** The same query as options, for `queryClient.fetchQuery` or `prefetchQuery`. */
    apiQueryOptions: hooks.queryOptions,
  };
}

/** The kernel's own paths: `/api/auth` and `/api/kernel`. */
export type KernelPaths = paths;

const kernel = createApiClient<paths>();

export const api = kernel.api;
export const useApiQuery = kernel.useApiQuery;
export const useApiMutation = kernel.useApiMutation;
export const apiQueryOptions = kernel.apiQueryOptions;
