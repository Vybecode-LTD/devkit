/**
 * Who is signed in (K4 contract §2): `useSession` and `useSignOut`.
 *
 * The session is `GET /api/auth/session`, read once and kept in the query
 * cache under its own key. A 401 there, or on any call (the client's
 * `setApiHandlers`), shows the person signed out; a sign-in's answer sets it
 * directly (`setSessionUser`). `staff` is any role but `member`.
 */
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, type ReactNode } from "react";

import { ApiProblem, api, setApiHandlers } from "../api/client";
import type { components } from "../api/schema";

export type SessionUser = components["schemas"]["UserView"];

export type Session =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "unreachable"; problem: ApiProblem; retry: () => void }
  | { status: "signed-in"; user: SessionUser; staff: boolean; can: (permission: string) => boolean };

/** The session's place in the query cache: its own, since it holds `null` for signed out. */
export const SESSION_KEY = ["kernel", "session"] as const;

/** The queries a sign-out keeps: who's signed in, and what the site is. */
const KEPT = new Set(["kernel:session", "get:/api/kernel/site", "get:/api/kernel/modules"]);

async function readSession(): Promise<SessionUser | null> {
  try {
    const { data } = await api.GET("/api/auth/session");
    if (!data) throw ApiProblem.unreachable();
    return data.user;
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 401) return null;
    throw error;
  }
}

/** Shows `user` signed in (a sign-in's answer), or signed out with `null`. */
export function setSessionUser(queryClient: QueryClient, user: SessionUser | null): void {
  queryClient.setQueryData(SESSION_KEY, user);
}

/** Forgets every answer that was the person's own, then shows them signed out. */
function forget(queryClient: QueryClient): void {
  queryClient.removeQueries({
    predicate: (query) => !KEPT.has(query.queryKey.slice(0, 2).map(String).join(":")),
  });
  setSessionUser(queryClient, null);
}

/** Tells the client what to do when a call finds the session gone. */
export function SessionHandlers({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  useEffect(() => {
    setApiHandlers({
      signedOut: () => {
        forget(queryClient);
      },
    });
    return () => {
      setApiHandlers({ signedOut: () => undefined });
    };
  }, [queryClient]);
  return children;
}

function signedIn(user: SessionUser): Session {
  const held = new Set(user.permissions);
  return {
    status: "signed-in",
    user,
    staff: user.roles.some((role) => role !== "member"),
    can: (permission) => held.has(permission),
  };
}

/** Who is signed in, if anyone. */
export function useSession(): Session {
  const query = useQuery<SessionUser | null, ApiProblem>({
    queryKey: SESSION_KEY,
    queryFn: readSession,
    staleTime: 60_000,
  });
  const { refetch } = query;
  const retry = useCallback(() => void refetch(), [refetch]);
  if (query.data !== undefined) return query.data === null ? { status: "signed-out" } : signedIn(query.data);
  if (query.error) return { status: "unreachable", problem: query.error, retry };
  return { status: "loading" };
}

/** Signs the person out on this device, then forgets what was theirs. */
export function useSignOut(): () => Promise<void> {
  const queryClient = useQueryClient();
  return useCallback(async () => {
    try {
      await api.POST("/api/auth/sign-out");
    } catch (error) {
      // Already signed out is signed out; anything else is still signed in.
      if (!(error instanceof ApiProblem && error.status === 401)) throw error;
    }
    forget(queryClient);
  }, [queryClient]);
}
