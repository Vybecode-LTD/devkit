/**
 * An editor's unsaved changes, kept from a move away (ported from VybeSite's
 * `lib/unsavedGuard.ts`).
 *
 * - A move to another page (a link, Back, the app's own) waits while `dirty`:
 *   React Router's blocker, which the kernel's data router allows. A move
 *   within the page (a query, a `#place`) isn't a leave.
 * - A reload or a closed tab gets the browser's own question, while `dirty`
 *   and only then: a page that asks needlessly teaches people to ignore it.
 *
 * `useLeaveGuard` is the blocker alone, for an editor that asks its own way;
 * `useUnsavedGuard` adds the question `UnsavedDialog` asks.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useBlocker, type Blocker, type BlockerFunction } from "react-router";

export function useLeaveGuard(dirty: boolean): { blocker: Blocker; release: () => void } {
  // Read at the moment of a move, not at the last render: `release` must hold
  // for a move made in the same breath as the save it follows.
  const armed = useRef(dirty);
  useLayoutEffect(() => {
    armed.current = dirty;
  });
  const blocker = useBlocker(
    useCallback<BlockerFunction>(
      ({ currentLocation, nextLocation }) => armed.current && currentLocation.pathname !== nextLocation.pathname,
      [],
    ),
  );

  useEffect(() => {
    if (!dirty) return;
    const ask = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", ask);
    return () => {
      window.removeEventListener("beforeunload", ask);
    };
  }, [dirty]);

  /** Lets the next move through: the editor's own, after a save, before the form has caught up. */
  const release = useCallback(() => {
    armed.current = false;
  }, []);
  return { blocker, release };
}

export type UnsavedGuard = {
  /** A move away is waiting on the person. */
  asking: boolean;
  saving: boolean;
  /** Why the last Save and leave didn't save, in words; blank if it didn't say. */
  error: string;
  saveAndLeave: () => void;
  leave: () => void;
  stay: () => void;
  /** Lets the editor's own next move through (see `useLeaveGuard`). */
  release: () => void;
};

/**
 * `useLeaveGuard` with the question an explicit-save editor asks. `save`
 * saves what's on the screen for a leave: it answers null once it's saved, or
 * why it isn't (blank when the person called it off), and makes no move of
 * its own, so the leave goes where it was going.
 */
export function useUnsavedGuard(dirty: boolean, save: () => Promise<string | null>): UnsavedGuard {
  const { blocker, release } = useLeaveGuard(dirty);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);
  // The leave a Save and leave is for: Stay moves it on, so a save that
  // answers after the person chose to stay changes nothing but its own fields.
  const turn = useRef(0);
  const saveNow = useRef(save);
  useLayoutEffect(() => {
    saveNow.current = save;
  });

  const leave = useCallback(() => {
    setError("");
    release();
    blocker.proceed?.();
  }, [blocker, release]);

  const saveAndLeave = useCallback(() => {
    if (busy.current) return;
    busy.current = true;
    const mine = turn.current;
    setSaving(true);
    setError("");
    // Through a promise, so a save that throws at once fails as any other (cubic on #82).
    void Promise.resolve()
      .then(() => saveNow.current())
      .catch((caught: unknown) => (caught instanceof Error ? caught.message : "It couldn't be saved."))
      .then((why) => {
        busy.current = false;
        setSaving(false);
        if (mine !== turn.current) return;
        if (why === null) leave();
        else setError(why);
      });
  }, [leave]);

  const stay = useCallback(() => {
    turn.current += 1;
    setError("");
    blocker.reset?.();
  }, [blocker]);

  return { asking: blocker.state === "blocked", saving, error, saveAndLeave, leave, stay, release };
}
