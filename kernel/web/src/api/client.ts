/**
 * The typed API client (SPEC.md section 6; K4 contract, `dev plans/contracts/k4-web-kernel.md`).
 *
 * `openapi-fetch` over the types `openapi-typescript` makes from the committed
 * `openapi.json` (`npm run api:types`), with TanStack Query hooks from
 * `openapi-react-query`. Same origin, the session cookie only: nothing else
 * authenticates a call. What every client made here does for every call:
 *
 * - An answer that isn't a success throws an `ApiProblem` (a failed network,
 *   status 0 and `kernel.unreachable`), so a screen reads `problem.code`. The
 *   hooks' types say so: their error is an `ApiProblem`.
 * - An HTTP 401 `kernel.not_signed_in` tells the session (`setApiHandlers`),
 *   which then shows the person signed out.
 * - A write refused with 403 `auth.step_up_required` asks the person to
 *   confirm it's them (the step-up dialog) and, if they do, sends the same
 *   request again, once. A read never asks, and `useApiQuery` takes reads only.
 *
 * The kernel's own paths are `api`, `useApiQuery` and `useApiMutation`; a
 * module's `api.ts` makes its own with `createApiClient<paths>()` from its
 * own `openapi.json`.
 */
import type {
  QueryClient,
  SkipToken,
  UseMutationOptions,
  UseMutationResult,
  UseQueryOptions,
  UseQueryResult,
} from "@tanstack/react-query";
import createClient, {
  type Client,
  type ClientOptions,
  type FetchResponse,
  type MaybeOptionalInit,
  type Middleware,
} from "openapi-fetch";
import createQueryClient, { type QueryKey } from "openapi-react-query";
import type {
  HttpMethod,
  MediaType,
  PathsWithMethod,
  RequiredKeysOf,
} from "openapi-typescript-helpers";

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

function problems(): Middleware {
  // A copy of each write, made before it's sent (sending uses its body up),
  // so a write refused for a step-up can be sent again. Kept by the call's id,
  // not its Request, which a later middleware may replace (CodeRabbit on #78),
  // and dropped once the call is answered.
  const copies = new Map<string, Request>();
  return {
    onRequest({ request, id }) {
      if (!READS.has(request.method)) copies.set(id, request.clone());
      return undefined;
    },
    async onResponse({ response, options, id }) {
      const copy = copies.get(id);
      copies.delete(id);
      if (response.ok) return undefined;
      let answer = response;
      if (response.status === 403 && copy) {
        const refused = await ApiProblem.from(response.clone());
        if (refused.code === "auth.step_up_required" && (await handlers.stepUp())) {
          // Sent from here, outside openapi-fetch's own sending, so its onError
          // never sees a failure: make one a problem here (Codex on #78). The
          // fetch is the request's own, a per-call one if it was given one.
          try {
            answer = await options.fetch(copy);
          } catch {
            throw ApiProblem.unreachable();
          }
          if (answer.ok) return answer;
        }
      }
      const problem = await ApiProblem.from(answer);
      // The HTTP status, not the body's: a body can say anything (CodeRabbit on #78).
      if (answer.status === 401 && problem.code === "kernel.not_signed_in") handlers.signedOut();
      throw problem;
    },
    onError({ error, id }) {
      copies.delete(id);
      return error instanceof ApiProblem ? error : ApiProblem.unreachable();
    },
  };
}

// --- the hooks' types: openapi-react-query's, with ApiProblem as the error ---------------

// `any`, not `Record<HttpMethod, {}>`: the generated `paths` is an interface, and only an
// index signature of `any` takes an interface without one of its own.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyPaths = Record<string, any>;
/** The one method a query may use: a read never asks for a step-up (the contract). */
type Read = "get";
type Selected<Data, Select> = Select extends (data: Data) => infer Chosen ? Chosen : Data;
type Answer<Paths extends AnyPaths, Method extends HttpMethod, Path extends keyof Paths, Init> =
  Required<FetchResponse<Paths[Path][Method], Init, MediaType>>["data"];
type Arguments<Init, Rest extends unknown[]> =
  RequiredKeysOf<Init> extends never ? [(Init & Record<string, unknown>)?, ...Rest] : [Init & Record<string, unknown>, ...Rest];

/** A query's options; `Select` is the options' own `select`, as the library has it, so
 * the data keeps its type when there's none. */
type QueryOptionsOf<
  Paths extends AnyPaths,
  Path extends PathsWithMethod<Paths, Read>,
  Init,
  Select,
> = Omit<
  UseQueryOptions<
    Answer<Paths, Read, Path, Init>,
    ApiProblem,
    Selected<Answer<Paths, Read, Path, Init>, Select>,
    QueryKey<Paths, Read, Path>
  >,
  "queryKey" | "queryFn"
>;

export type UseApiQuery<Paths extends AnyPaths> = <
  Path extends PathsWithMethod<Paths, Read>,
  Init extends MaybeOptionalInit<Paths[Path], Read>,
  Options extends QueryOptionsOf<Paths, Path, Init, Options["select"]>,
>(
  method: Read,
  path: Path,
  ...rest: Arguments<Init, [Options?, QueryClient?]>
) => UseQueryResult<Selected<Answer<Paths, Read, Path, Init>, Options["select"]>, ApiProblem>;

export type ApiQueryOptions<Paths extends AnyPaths> = <
  Path extends PathsWithMethod<Paths, Read>,
  Init extends MaybeOptionalInit<Paths[Path], Read>,
  Options extends QueryOptionsOf<Paths, Path, Init, Options["select"]>,
>(
  method: Read,
  path: Path,
  ...rest: Arguments<Init, [Options?]>
) => Omit<
  UseQueryOptions<
    Answer<Paths, Read, Path, Init>,
    ApiProblem,
    Selected<Answer<Paths, Read, Path, Init>, Options["select"]>,
    QueryKey<Paths, Read, Path>
  >,
  "queryFn"
> & {
  queryFn: Exclude<
    UseQueryOptions<Answer<Paths, Read, Path, Init>, ApiProblem, unknown, QueryKey<Paths, Read, Path>>["queryFn"],
    SkipToken | undefined
  >;
};

export type UseApiMutation<Paths extends AnyPaths> = <
  Method extends HttpMethod,
  Path extends PathsWithMethod<Paths, Method>,
  Init extends MaybeOptionalInit<Paths[Path], Method>,
  OnMutate = unknown,
>(
  method: Method,
  path: Path,
  options?: Omit<
    UseMutationOptions<Answer<Paths, Method, Path, Init>, ApiProblem, Init, OnMutate>,
    "mutationKey" | "mutationFn"
  >,
  queryClient?: QueryClient,
) => UseMutationResult<Answer<Paths, Method, Path, Init>, ApiProblem, Init, OnMutate>;

/**
 * A query's retries: what may pass on a second try (a network failure, a 5xx),
 * up to TanStack's three, never a refusal (any 4xx). So an ended session is
 * read once and told to the session once (cubic on #78).
 */
export function retryUnlessRefused(failures: number, error: unknown): boolean {
  if (error instanceof ApiProblem && error.status >= 400 && error.status < 500) return false;
  return failures < 3;
}

function onlyReads(method: string): void {
  if (method !== "get") {
    throw new Error(`A query only reads: ${method} goes through useApiMutation or api.`);
  }
}

export type ApiClientOptions = {
  /** For tests: the fetch to send with. */
  fetch?: Fetch;
  /** For tests: the site's origin. The page's own by default. */
  baseUrl?: string;
};

/** A typed client for one `openapi.json`'s paths, with its hooks. */
export function createApiClient<Paths extends AnyPaths>(options: ApiClientOptions = {}) {
  const send: Fetch = options.fetch ?? ((request) => globalThis.fetch(request));
  const settings: ClientOptions = {
    baseUrl: options.baseUrl ?? (typeof location === "undefined" ? "" : location.origin),
    credentials: "same-origin",
    fetch: send,
  };
  const api: Client<Paths> = createClient<Paths>(settings);
  api.use(problems());
  const hooks = createQueryClient(api);
  // The library's own hooks, with their types restated: ApiProblem as the
  // error, and reads only for a query (CodeRabbit on #78).
  const useQuery = hooks.useQuery as (...args: unknown[]) => unknown;
  const queryOptions = hooks.queryOptions as (...args: unknown[]) => unknown;
  const useApiQuery = ((
    method: string,
    path: unknown,
    init?: unknown,
    given?: object,
    client?: unknown,
  ) => {
    onlyReads(method);
    return useQuery(method, path, init, { retry: retryUnlessRefused, ...given }, client);
  }) as UseApiQuery<Paths>;
  const apiQueryOptions = ((method: string, path: unknown, init?: unknown, given?: object) => {
    onlyReads(method);
    return queryOptions(method, path, init, { retry: retryUnlessRefused, ...given });
  }) as ApiQueryOptions<Paths>;
  return {
    api,
    /** `useApiQuery("get", "/api/...", init?, options?)`: TanStack Query's `useQuery`, typed. */
    useApiQuery,
    /** `useApiMutation("post", "/api/...", options?)`: TanStack Query's `useMutation`, typed. */
    useApiMutation: hooks.useMutation as UseApiMutation<Paths>,
    /** The same query as options, for `queryClient.fetchQuery` or `prefetchQuery`. */
    apiQueryOptions,
  };
}

/** The kernel's own paths: `/api/auth` and `/api/kernel`. */
export type KernelPaths = paths;

const kernel = createApiClient<paths>();

export const api = kernel.api;
export const useApiQuery = kernel.useApiQuery;
export const useApiMutation = kernel.useApiMutation;
export const apiQueryOptions = kernel.apiQueryOptions;
