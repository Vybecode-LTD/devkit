/**
 * Roles as the admin shows them (K4.7): the roles read
 * (`GET /api/auth/admin/roles`, `auth.user.manage`), each role's name, the
 * permissions in groups, and whether the signed-in person may change a role.
 *
 * What the person may do is the server's to decide (SPEC 14.8); these only
 * say ahead what it will answer, so a switch the server would refuse is drawn
 * off with its reason (decision 0013: a role is granted, removed or edited only
 * by someone holding every permission it carries; only an owner grants
 * `owner`; `member` is no rank).
 */
import { useApiQuery } from "../api/client";
import type { components } from "../api/schema";
import { useSession } from "../session/session";

export type RoleView = components["schemas"]["RoleView"];
export type PermissionView = components["schemas"]["PermissionView"];

export const OWNER = "owner";
export const MEMBER = "member";

/** The roles read, for those who may make it; for others it never asks, and the ids stand in for names. */
export function useRoles() {
  const session = useSession();
  const allowed = session.status === "signed-in" && session.can("auth.user.manage");
  return useApiQuery("get", "/api/auth/admin/roles", undefined, { enabled: allowed });
}

/** A role's name: from the roles read when there is one, else its id in words ("owner" is "Owner"). */
export function roleName(id: string, roles?: readonly RoleView[]): string {
  const found = roles?.find((role) => role.id === id);
  if (found) return found.name;
  const spaced = id.replace(/-/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** The roles as words, a member's role left out beside any other: "Owner", "Admin, Editor". */
export function roleWords(ids: readonly string[], roles?: readonly RoleView[]): string {
  const shown = ids.filter((id) => id !== MEMBER);
  return (shown.length > 0 ? shown : [MEMBER]).map((id) => roleName(id, roles)).join(", ");
}

/** What the signed-in person holds, and whether they're an owner. */
export function useHeld(): { held: ReadonlySet<string>; owner: boolean } {
  const session = useSession();
  if (session.status !== "signed-in") return { held: new Set(), owner: false };
  return { held: new Set(session.user.permissions), owner: session.user.roles.includes(OWNER) };
}

/** Why the person can't grant or remove `role`, or null when they can. */
export function whyNotGrant(role: RoleView, held: ReadonlySet<string>, owner: boolean): string | null {
  if (owner || role.id === MEMBER) return null;
  if (role.id === OWNER) return "Only an owner grants or removes it.";
  return role.permissions.every((key) => held.has(key)) ? null : "It carries permissions you don't hold.";
}

export type PermissionGroup = { label: string; items: PermissionView[] };

function groupOf(permission: PermissionView): string {
  if (permission.owner !== "kernel") {
    const spaced = permission.owner.replace(/-/g, " ");
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
  }
  if (permission.key.startsWith("auth.")) return "People and access";
  if (permission.key.startsWith("kernel.moderation.")) return "Moderation";
  return "Site and system";
}

/** The permissions in groups, in the order they first appear: the kernel's, then each module's. */
export function permissionGroups(permissions: readonly PermissionView[]): PermissionGroup[] {
  const groups = new Map<string, PermissionView[]>();
  for (const permission of permissions) {
    const label = groupOf(permission);
    groups.set(label, [...(groups.get(label) ?? []), permission]);
  }
  return [...groups].map(([label, items]) => ({ label, items }));
}
