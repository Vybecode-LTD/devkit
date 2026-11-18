/**
 * The kernel's slots, typed (K4 contract §2): what a module's binding may put
 * in each, by name. `defineModule` takes them; `useSlot` and `SlotOutlet`
 * read them.
 */
import type { ComponentType } from "react";

/**
 * An icon's name. Any string until the UI kit (K4.4) brings its icon set and
 * narrows this to the set's names.
 */
export type IconName = string;

/** Loads a part, so each module's parts are their own chunk. */
export type Lazy = () => Promise<{ default: ComponentType }>;

/** A link in a menu. `to` is a path on this site. */
export type LinkEntry = {
  label: string;
  to: string;
  /** Hidden unless the person holds this permission. */
  permission?: string;
};

export type AdminLinkEntry = LinkEntry & {
  /** The sidebar group it sits in; `adminSections` orders the groups. */
  section?: string;
  icon?: IconName;
};

export type Slots = {
  "nav.public"?: LinkEntry[];
  "nav.member"?: LinkEntry[];
  "nav.admin"?: AdminLinkEntry[];
  "admin.dashboard.widget"?: { lazy: Lazy; permission?: string }[];
  "admin.settings.section"?: { id: string; title: string; lazy: Lazy; permission?: string }[];
  "account.section"?: { id: string; title: string; lazy: Lazy }[];
  "site.footer"?: { lazy: Lazy }[];
};

export type SlotName = keyof Slots;

/** One entry of a slot, as the slot holds it. */
export type SlotEntryOf<Name extends SlotName> = NonNullable<Slots[Name]>[number];

/** The slots that hold links; the rest hold parts that load. */
export const LINK_SLOTS = ["nav.public", "nav.member", "nav.admin"] as const satisfies readonly SlotName[];

export const SLOT_NAMES = [
  ...LINK_SLOTS,
  "admin.dashboard.widget",
  "admin.settings.section",
  "account.section",
  "site.footer",
] as const satisfies readonly SlotName[];

export type LinkSlotName = (typeof LINK_SLOTS)[number];
export type PartSlotName = Exclude<SlotName, LinkSlotName>;
