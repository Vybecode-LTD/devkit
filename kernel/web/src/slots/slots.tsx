/**
 * Reading the slots (K4 contract §2): `useSlot` gives only the entries of
 * modules that are on and that the person may see; `SlotOutlet` shows a
 * slot, each part that loads in its own error boundary.
 */
import { Suspense } from "react";
import { NavLink } from "react-router";

import { ErrorBoundary } from "../app/ErrorBoundary";
import { useKernelSetup } from "../app/context";
import { lazyPart } from "../app/lazy";
import { useSession } from "../session/session";
import { useModulesOn } from "../site/site";
import { LINK_SLOTS, type Lazy, type LinkSlotName, type SlotEntryOf, type SlotName } from "./types";

/** An entry with the module it came from. */
export type Placed<Name extends SlotName> = SlotEntryOf<Name> & { module: string };

/** The entries of `name` the person may see, in the modules' order. */
export function useSlot<Name extends SlotName>(name: Name): Placed<Name>[] {
  const { modules } = useKernelSetup();
  const on = useModulesOn();
  const session = useSession();
  if (on === undefined) return [];
  const may = (permission: string | undefined) =>
    permission === undefined || (session.status === "signed-in" && session.can(permission));
  const found: Placed<Name>[] = [];
  for (const definition of modules) {
    if (!on.has(definition.id)) continue;
    const entries = (definition.slots?.[name] ?? []) as SlotEntryOf<Name>[];
    for (const entry of entries) {
      const permission = "permission" in entry ? entry.permission : undefined;
      if (may(permission)) found.push({ ...entry, module: definition.id });
    }
  }
  return found;
}

function isLinkSlot(name: SlotName): name is LinkSlotName {
  return (LINK_SLOTS as readonly string[]).includes(name);
}

/**
 * Shows the slot `name`: a list of links for a menu, else each part in turn,
 * each in an error boundary of its own so one part failing leaves the rest.
 */
export function SlotOutlet({ name, label }: { name: SlotName; label?: string }) {
  const entries = useSlot(name);
  if (entries.length === 0) return null;
  if (isLinkSlot(name)) {
    return (
      <ul className="mf-slot-links" aria-label={label}>
        {(entries as Placed<LinkSlotName>[]).map((entry) => (
          <li key={`${entry.module}:${entry.to}`}>
            <NavLink to={entry.to}>{entry.label}</NavLink>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <>
      {(entries as (Placed<SlotName> & { lazy: Lazy })[]).map((entry, at) => {
        const Part = lazyPart(entry.lazy);
        return (
          <ErrorBoundary key={`${entry.module}:${String(at)}`} where={`${entry.module}'s part of ${name}`}>
            <Suspense fallback={null}>
              <Part />
            </Suspense>
          </ErrorBoundary>
        );
      })}
    </>
  );
}
