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

function segments(path: string): string[] {
  return path === "/" ? [] : path.slice(1).split("/");
}

function isName(segment: string): boolean {
  return segment.startsWith(":") || segment === "*";
}

/**
 * The kernel page a module's route would take, if any: one it matches under
 * the kernel's own first segment (`/sign-in`, `/account/:tab`,
 * `/admin/people`). A route that starts with a `:name` (`/:slug`) may meet
 * them and never gets them: the router ranks the kernel's fixed paths first,
 * as the server does (change 9).
 */
export function kernelPageTaken(path: string): KernelPage | undefined {
  const mine = segments(path);
  const first = mine[0];
  if (first === undefined || isName(first)) return undefined;
  return KERNEL_PAGES.find((page) => {
    const theirs = segments(page.path);
    if (mine.includes("*")) {
      const fixed = mine.slice(0, mine.indexOf("*"));
      return fixed.length <= theirs.length && fixed.every((part, at) => isName(part) || part === theirs[at]);
    }
    return mine.length === theirs.length && mine.every((part, at) => isName(part) || part === theirs[at]);
  });
}
