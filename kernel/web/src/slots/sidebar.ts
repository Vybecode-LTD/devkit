/**
 * The admin sidebar's order (K4 contract §2): Dashboard, then the modules'
 * entries grouped by `section` in `adminSections` order (sections it doesn't
 * list after, as they appear), then People and access, then Settings. An
 * entry with no section sits under Dashboard. A group with nothing the person
 * may open isn't shown.
 */
import type { AdminSection } from "../app/context";
import type { Placed } from "./slots";
import type { IconName } from "./types";

export type SidebarItem = { label: string; to: string; icon?: IconName };
export type SidebarGroup = { label?: string; icon?: IconName; items: SidebarItem[] };

type KernelItem = SidebarItem & { permission?: string };

const PEOPLE: KernelItem[] = [
  { label: "People", to: "/admin/people", permission: "auth.user.manage" },
  { label: "Roles", to: "/admin/roles", permission: "auth.user.manage" },
  { label: "Activity", to: "/admin/activity", permission: "auth.audit.read" },
];

const SETTINGS: KernelItem[] = [
  { label: "Site", to: "/admin/settings", permission: "kernel.settings.manage" },
  { label: "Features", to: "/admin/settings/features", permission: "kernel.module.manage" },
  { label: "System", to: "/admin/settings/system", permission: "kernel.settings.manage" },
];

function item(entry: Placed<"nav.admin">): SidebarItem {
  return entry.icon === undefined ? { label: entry.label, to: entry.to } : { label: entry.label, to: entry.to, icon: entry.icon };
}

/** The sidebar's groups, from the entries the person may see (`useSlot("nav.admin")`). */
export function adminSidebar(
  entries: readonly Placed<"nav.admin">[],
  sections: readonly AdminSection[],
  can: (permission: string) => boolean,
): SidebarGroup[] {
  const kernel = (items: KernelItem[]) =>
    items.filter((each) => each.permission === undefined || can(each.permission)).map(({ label, to }) => ({ label, to }));
  const top: SidebarGroup = {
    items: [{ label: "Dashboard", to: "/admin" }, ...entries.filter((entry) => entry.section === undefined).map(item)],
  };
  const named = new Map<string, SidebarItem[]>();
  for (const entry of entries) {
    if (entry.section === undefined) continue;
    named.set(entry.section, [...(named.get(entry.section) ?? []), item(entry)]);
  }
  // Each section once, at its first place and with its first icon (cubic on #79).
  const listed = [...new Set(sections.map((section) => section.label))];
  const order = [...listed.filter((label) => named.has(label)), ...[...named.keys()].filter((label) => !listed.includes(label))];
  const modules = order.map((label): SidebarGroup => {
    const icon = sections.find((section) => section.label === label)?.icon;
    const items = named.get(label) ?? [];
    return icon === undefined ? { label, items } : { label, icon, items };
  });
  const groups = [
    top,
    ...modules,
    { label: "People and access", items: kernel(PEOPLE) },
    { label: "Settings", items: kernel(SETTINGS) },
  ];
  return groups.filter((group) => group.items.length > 0);
}
