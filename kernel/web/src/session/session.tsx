/**
 * Who is signed in (K4 contract §2): `useSession` and `useSignOut`.
 *
 * The session is `GET /api/auth/session`, read once and kept in the query
 * cache under its own key. A 401 there shows the person signed out. A 401 on
 * any other call (the client's `setApiHandlers`) reads the session again and
 * forgets what was the person's only if it's gone: the call may have been
 * sent before a sign-in (cubic on #79). A sign-in's answer sets it directly
 * (`setSessionUser`), after stopping any read already on its way, whose older
 * answer would otherwise land on top (CodeRabbit on #79). `staff` is any role
 * but `member`.
 */
import { useQuery, useQueryClient, type Query, type QueryClient } from "@tanstack/react-query";
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

/** How the session is read and kept. */
const SESSION = { queryKey: SESSION_KEY, queryFn: readSession, staleTime: 60_000 };

/** An answer that was the signed-in person's own: everything but who's signed in and what the site is. */
function personal(query: Query): boolean {
  return !KEPT.has(query.queryKey.slice(0, 2).map(String).join(":"));
}

/**
 * Shows `user` signed in (a sign-in's answer), or signed out with `null`.
 * Another account than the one shown first forgets the last one's answers,
 * those on their way too, so the new one never sees them (CodeRabbit on #83).
 */
export async function setSessionUser(queryClient: QueryClient, user: SessionUser | null): Promise<void> {
  await queryClient.cancelQueries({ queryKey: SESSION_KEY });
  const before = queryClient.getQueryData<SessionUser | null>(SESSION_KEY);
  if ((before?.id ?? null) !== (user?.id ?? null)) {
    await queryClient.cancelQueries({ predicate: personal });
    queryClient.removeQueries({ predicate: personal });
  }
  queryClient.setQueryData(SESSION_KEY, user);
}

/** Forgets every answer that was the person's own, then shows them signed out. */
function forget(queryClient: QueryClient): void {
  queryClient.removeQueries({ predicate: personal });
  queryClient.setQueryData(SESSION_KEY, null);
}

/**
 * A call found no session, or one that answered success ended it (a reset,
 * an undo from mail): read it again, joining a read already on its way (so
 * the session read's own 401 asks nothing more), and forget only if it's
 * gone. If it can't be read, nothing changes. Says whether it was read.
 */
export async function recheckSession(queryClient: QueryClient): Promise<boolean> {
  let user: SessionUser | null;
  try {
    user = await queryClient.query({ ...SESSION, staleTime: 0, retry: false });
  } catch {
    return false;
  }
  if (user === null) forget(queryClient);
  return true;
}

/**
 * Reads the session fresh after a success that changed the account (a
 * confirmed address, an undo from mail): a read already on its way began
 * before it and would bring back what was, so it's stopped, not joined
 * (CodeRabbit on #83). Gone, what was the person's is forgotten; a read that
 * fails leaves the session marked to be read again. Says whether it was read.
 */
export async function refreshSession(queryClient: QueryClient): Promise<boolean> {
  await queryClient.cancelQueries({ queryKey: SESSION_KEY });
  return recheckSession(queryClient);
}

/** Tells the client what to do when a call finds the session gone. */
export function SessionHandlers({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  useEffect(() => {
    setApiHandlers({
      signedOut: () => {
        void recheckSession(queryClient);
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
  const query = useQuery<SessionUser | null, ApiProblem>(SESSION);
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
    await queryClient.cancelQueries({ queryKey: SESSION_KEY });
    forget(queryClient);
  }, [queryClient]);
}
