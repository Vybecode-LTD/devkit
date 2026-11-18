/**
 * The kernel's own pages (K4 contract §2), as the router serves them.
 *
 * The same list is `kernel/kernel.json`'s `pages` and the backend's
 * `kernel.server_copy.KERNEL_PAGES`; a site never receives the manifest, so
 * each side keeps it in code and a test holds it to the manifest (change 8).
 * `permission` is the router's own: an admin page shows the no-access page to
 * staff without it.
 */
export type KernelPage = {
  path: string;
  title: string;
  access: "public" | "member" | "admin";
  permission?: string;
};

export const KERNEL_PAGES: readonly KernelPage[] = [
  { path: "/sign-in", title: "Sign in", access: "public" },
  { path: "/sign-up", title: "Sign up", access: "public" },
  { path: "/forgot-password", title: "Forgot password", access: "public" },
  { path: "/auth/verify", title: "Verify your email", access: "public" },
  { path: "/auth/link", title: "Sign in with a link", access: "public" },
  { path: "/auth/reset", title: "Choose a new password", access: "public" },
  { path: "/auth/email", title: "Confirm your new email", access: "public" },
  { path: "/auth/email/undo", title: "Undo the email change", access: "public" },
  { path: "/auth/second-factor/undo", title: "Remove the new sign-in step", access: "public" },
  { path: "/notifications/unsubscribe", title: "Unsubscribe", access: "public" },
  { path: "/account", title: "Your account", access: "member" },
  { path: "/account/notifications", title: "Notifications", access: "member" },
  { path: "/account/activity", title: "Your activity", access: "member" },
  { path: "/admin", title: "Dashboard", access: "admin" },
  { path: "/admin/people", title: "People", access: "admin", permission: "auth.user.manage" },
  { path: "/admin/roles", title: "Roles", access: "admin", permission: "auth.user.manage" },
  { path: "/admin/activity", title: "Activity", access: "admin", permission: "auth.audit.read" },
  { path: "/admin/settings", title: "Settings", access: "admin", permission: "kernel.settings.manage" },
  { path: "/admin/settings/features", title: "Features", access: "admin", permission: "kernel.module.manage" },
  { path: "/admin/settings/system", title: "System", access: "admin", permission: "kernel.settings.manage" },
];

/** A path's segments, as the router reads them: no empty ones, so a trailing slash counts for nothing. */
function segments(path: string): string[] {
  return path.split("/").filter(Boolean);
}

function isName(segment: string): boolean {
  return segment.startsWith(":") || segment === "*";
}

/** Every path an optional segment (`:tab?`, `edit?`) makes: with it and without it. */
function variants(parts: readonly string[]): string[][] {
  const [head, ...rest] = parts;
  if (head === undefined) return [[]];
  const after = variants(rest);
  if (!head.endsWith("?")) return after.map((tail) => [head, ...tail]);
  const kept = head.slice(0, -1);
  return [...after.map((tail) => [kept, ...tail]), ...after];
}

function meets(mine: readonly string[], theirs: readonly string[]): boolean {
  const star = mine.indexOf("*");
  if (star >= 0) {
    const fixed = mine.slice(0, star);
    return fixed.length <= theirs.length && fixed.every((part, at) => isName(part) || part === theirs[at]);
  }
  return mine.length === theirs.length && mine.every((part, at) => isName(part) || part === theirs[at]);
}

/**
 * The kernel page a module's route would take, if any: one it matches under
 * the kernel's own first segment (`/sign-in`, `/account/:tab`,
 * `/admin/people`). A route that starts with a `:name` (`/:slug`) may meet
 * them and never gets them: the router ranks the kernel's fixed paths first,
 * as the server does (change 9). Each path an optional segment makes is
 * checked, and a trailing slash is read as the router reads it, as nothing
 * (CodeRabbit and cubic on #79).
 */
export function kernelPageTaken(path: string): KernelPage | undefined {
  for (const mine of variants(segments(path))) {
    const first = mine[0];
    if (first === undefined || isName(first)) continue;
    const taken = KERNEL_PAGES.find((page) => meets(mine, segments(page.path)));
    if (taken) return taken;
  }
  return undefined;
}
