/**
 * Reading the slots (K4 contract §2): `useSlot` gives only the entries of
 * modules that are on and that the person may see; `SlotOutlet` shows a
 * slot, each part that loads in its own error boundary.
 */
import { Suspense, useCallback, useState } from "react";
import { NavLink } from "react-router";

import { ErrorBoundary } from "../ui/ErrorBoundary";
import { useKernelSetup } from "../app/context";
import { lazyPart } from "../app/lazy";
import { useSession } from "../session/session";
import { SITE, useModulesOn } from "../site/site";
import { LINK_SLOTS, type Lazy, type LinkSlotName, type SlotEntryOf, type SlotName } from "./types";

/**
 * An entry with the module it came from, and its `key`: the module, the slot
 * and its place in that module's own list, fixed before anything is filtered
 * out, so a part keeps its own error boundary and state whatever is hidden
 * around it (cubic and CodeRabbit on #79).
 */
export type Placed<Name extends SlotName> = SlotEntryOf<Name> & { module: string; key: string };

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
    if (definition.id !== SITE && !on.has(definition.id)) continue; // the site's are always on
    const entries = (definition.slots?.[name] ?? []) as SlotEntryOf<Name>[];
    entries.forEach((entry, at) => {
      const permission = "permission" in entry ? entry.permission : undefined;
      if (may(permission)) found.push({ ...entry, module: definition.id, key: `${definition.id}:${name}:${String(at)}` });
    });
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
  // Bumped by Try again, so the parts are made again here: one whose code
  // didn't arrive gets a fresh load (lazyPart forgot the failed one).
  const [, setTries] = useState(0);
  const again = useCallback(() => {
    setTries((tries) => tries + 1);
  }, []);
  if (entries.length === 0) return null;
  if (isLinkSlot(name)) {
    return (
      <ul className="mf-slot-links" aria-label={label}>
        {(entries as Placed<LinkSlotName>[]).map((entry) => (
          <li key={entry.key}>
            <NavLink to={entry.to}>{entry.label}</NavLink>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <>
      {(entries as (Placed<SlotName> & { lazy: Lazy })[]).map((entry) => {
        const Part = lazyPart(entry.lazy);
        return (
          <ErrorBoundary key={entry.key} where={`${entry.module}'s part of ${name}`} onRetry={again}>
            <Suspense fallback={null}>
              <Part />
            </Suspense>
          </ErrorBoundary>
        );
      })}
    </>
  );
}
