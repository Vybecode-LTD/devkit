/**
 * How a module's web binding registers itself (SPEC.md section 8).
 *
 * A binding calls `defineModule` once, in `module.web.ts`, with its routes by
 * access level and the kernel slots it fills. The kernel's shell (K4) reads
 * these to build the router and the slots. A binding holds no business logic:
 * anything a desktop or mobile app would also need lives in the backend.
 */
import type { ComponentType } from "react";

export type ModuleRoute = {
  /** The path, in React Router's syntax, such as "/blog/:slug". */
  path: string;
  /** Loads the page, so each module's pages are their own chunk. */
  lazy: () => Promise<{ default: ComponentType }>;
  /** For admin routes: the permission a user needs, such as "blog.post.write". */
  permission?: string;
};

export type SlotEntry = {
  label: string;
  to: string;
  /** Hidden unless the user holds this permission. */
  permission?: string;
};

export type ModuleDefinition = {
  /** The module's id, as in its module.json. */
  id: string;
  routes: {
    public: ModuleRoute[];
    member: ModuleRoute[];
    admin: ModuleRoute[];
  };
  /** Kernel slots this module fills, by slot name, such as "nav.admin". */
  slots?: Record<string, SlotEntry[]>;
};

const MODULE_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

/**
 * Registers a module's web binding. Checks what the type can't: the id's
 * shape, admin routes under /admin and each with a permission, and no path
 * given twice.
 */
export function defineModule(definition: ModuleDefinition): ModuleDefinition {
  if (!MODULE_ID.test(definition.id)) {
    throw new Error(`"${definition.id}" isn't a module id: lowercase letters, digits and hyphens.`);
  }
  const seen = new Set<string>();
  for (const [level, routes] of Object.entries(definition.routes)) {
    for (const route of routes) {
      if (seen.has(route.path)) {
        throw new Error(`${definition.id} gives the path ${route.path} twice.`);
      }
      seen.add(route.path);
      if (level === "admin" && !route.path.startsWith("/admin/")) {
        throw new Error(`${definition.id}'s admin route ${route.path} must start with /admin/.`);
      }
      if (level === "admin" && !route.permission) {
        throw new Error(`${definition.id}'s admin route ${route.path} must name a permission.`);
      }
    }
  }
  return definition;
}
