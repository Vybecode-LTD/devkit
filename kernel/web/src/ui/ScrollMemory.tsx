/**
 * Where the page is scrolled as the reader moves around the app (ported from
 * VybeSite's `components/ScrollMemory.tsx`), in place of React Router's
 * `<ScrollRestoration>`, which restores once and gives up when the page is
 * still too short.
 *
 * - Back, Forward and a reload return to where the reader was on that entry,
 *   held while the page grows to fit (`holdScroll`); the place the address
 *   names still opens the shut sections around it.
 * - A new page starts at the top, or lands on the place its address names
 *   (`#id`), waiting for a part that loads its data first (`landOn`); so
 *   does a move to a new place on the same page.
 *
 * The browser's own restoration is turned off (it runs before the app has
 * drawn the page), each entry's position is recorded as the reader scrolls,
 * and kept in sessionStorage through a reload.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavigationType, useLocation, useNavigationType } from "react-router";

import { entryKey, holdScroll, landOn, readPositions, savePositions } from "./place";

type Shown = { pathname: string; hash: string };

/** The id an address's `#…` names; a malformed escape is taken as written. */
export function placeNamed(hash: string): string {
  const raw = hash.slice(1);
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export function ScrollMemory() {
  const location = useLocation();
  const action = useNavigationType();
  const key = entryKey(location);
  const { pathname, hash } = location;
  const [positions] = useState(readPositions);
  const current = useRef(key);
  const holding = useRef(false);
  const restoring = useRef(false);

  useEffect(() => {
    const record = () => {
      if (holding.current) return;
      positions.delete(current.current);
      positions.set(current.current, window.scrollY);
    };
    const keep = () => {
      savePositions(positions);
    };
    const before = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    window.addEventListener("scroll", record, { passive: true });
    window.addEventListener("pagehide", keep);
    return () => {
      window.removeEventListener("scroll", record);
      window.removeEventListener("pagehide", keep);
      window.history.scrollRestoration = before;
    };
  }, [positions]);

  // Back, Forward and a reload: where the reader was on this entry.
  useLayoutEffect(() => {
    current.current = key;
    const saved = action === NavigationType.Pop ? positions.get(key) : undefined;
    restoring.current = saved !== undefined;
    if (saved === undefined) return undefined;
    holding.current = true;
    const stop = holdScroll(saved, {
      onDone: () => {
        holding.current = false;
      },
    });
    return () => {
      stop();
      holding.current = false;
    };
  }, [key, hash, action, positions]);

  // A new page: the top, or the place its address names. Instantly, so the
  // reader never sees it scroll. Within the page, only a new place moves it:
  // the router's own move to `#passkeys` doesn't scroll as a plain link would
  // (Codex on #82), and a new query or a place dropped leaves it where it is.
  // The address before this one changes only when the address does, so
  // StrictMode's second run of the effect decides as the first did.
  const seen = useRef<{ before: Shown | null; now: Shown | null }>({ before: null, now: null });
  useLayoutEffect(() => {
    if (seen.current.now?.pathname !== pathname || seen.current.now.hash !== hash) {
      seen.current = { before: seen.current.now, now: { pathname, hash } };
    }
    const id = placeNamed(hash);
    if (seen.current.before?.pathname === pathname) return id ? landOn(id, { scroll: !restoring.current }) : undefined;
    if (restoring.current) return id ? landOn(id, { scroll: false }) : undefined;
    if (!id || !document.getElementById(id)) window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    return id ? landOn(id) : undefined;
  }, [pathname, hash]);

  return null;
}
