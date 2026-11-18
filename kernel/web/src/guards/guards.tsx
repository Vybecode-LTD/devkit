/**
 * Who may open a page (K4 contract §2).
 *
 * - `RequireAuth`: signed out goes to `/sign-in?next=<this path>`.
 * - `RequirePermission`: without it, the kernel's no-access page, never a
 *   redirect, so the address stays what the person asked for.
 * - `RequireAdmin`, the admin itself: a member gets the 404 page (the admin
 *   isn't theirs to know of); staff without a second factor go to
 *   `/account?needs=second-factor` to add one.
 *
 * While the session is read, nothing shows; while the site can't be reached,
 * the problem shows with a way to try again.
 */
import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router";

import { NoAccess, NotFound, Unreachable } from "../app/pages/KernelPages";
import { useSession, type Session } from "../session/session";
import { signInFor } from "./next";

type Guarded = { children?: ReactNode };

function Reading() {
  return <div aria-busy="true" />;
}

function useSignedIn(): { session: Session; gate: ReactNode | null } {
  const session = useSession();
  const location = useLocation();
  if (session.status === "loading") return { session, gate: <Reading /> };
  if (session.status === "unreachable") return { session, gate: <Unreachable problem={session.problem} retry={session.retry} /> };
  if (session.status === "signed-out") {
    return { session, gate: <Navigate to={signInFor(location.pathname + location.search)} replace /> };
  }
  return { session, gate: null };
}

export function RequireAuth({ children }: Guarded) {
  const { gate } = useSignedIn();
  return gate ?? children ?? <Outlet />;
}

export function RequirePermission({ permission, children }: Guarded & { permission: string }) {
  const { session, gate } = useSignedIn();
  if (gate) return gate;
  if (session.status === "signed-in" && !session.can(permission)) return <NoAccess />;
  return children ?? <Outlet />;
}

export function RequireAdmin({ children, notFound }: Guarded & { notFound?: ReactNode }) {
  const { session, gate } = useSignedIn();
  if (gate) return gate;
  if (session.status !== "signed-in" || !session.staff) return notFound ?? <NotFound />;
  if (!session.user.second_factor) return <Navigate to="/account?needs=second-factor" replace />;
  return children ?? <Outlet />;
}
