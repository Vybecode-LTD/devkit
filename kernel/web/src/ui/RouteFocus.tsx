/**
 * After a move to another page, puts the keyboard's focus on its heading, so
 * a screen reader reads the new page and Tab starts from its top. The first
 * page is left as the browser opened it.
 *
 * A page whose code is still loading draws nothing at first, so the focus
 * waits for its heading to appear (Codex on #79). A page that shows none
 * within `FOCUS_WAIT_MS` has its main area focused meanwhile, and its heading
 * still gets the focus when it comes; the watch ends after `FOCUS_GIVE_UP_MS`.
 * The moment the person moves the focus themselves, or goes to another
 * page, all of it stops: theirs is never taken back (CodeRabbit on #79). The
 * focus never scrolls: `ScrollMemory` places the page, at its top, at the
 * place Back gives back (cubic on #79), or at the place its address names,
 * which then takes the focus itself (`landOn`), so a page reached with a
 * `#place` is left to it, its heading focused only if nothing took the
 * focus within `FOCUS_WAIT_MS`. The page is compared with the last one focused for,
 * so StrictMode's second run of the effect does nothing.
 */
import { useEffect, useRef } from "react";
import { useLocation } from "react-router";

import { placeNamed } from "./ScrollMemory";

/** How long a page may take to show its heading before the focus goes to its main area. */
export const FOCUS_WAIT_MS = 3000;
/** How long a page's heading is watched for at all. */
export const FOCUS_GIVE_UP_MS = 30_000;

function focus(target: HTMLElement): void {
  if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
}

function heading(): HTMLElement | null {
  return document.querySelector<HTMLElement>("main h1");
}

export function RouteFocus() {
  const { pathname, hash } = useLocation();
  const last = useRef(pathname);
  useEffect(() => {
    if (last.current === pathname) return;
    last.current = pathname;
    // Set while this effect moves the focus itself, so only the person's own
    // moves stop it.
    let ours = false;
    const move = (target: HTMLElement) => {
      ours = true;
      try {
        focus(target);
      } finally {
        ours = false;
      }
    };
    // Whether the page's place holds the focus: it took it, as `landOn` does.
    const placeHasIt = (): boolean => {
      if (!hash) return false;
      const place = document.getElementById(placeNamed(hash));
      const at = document.activeElement;
      return Boolean(place && at && (place === at || place.contains(at)));
    };
    const observer = new MutationObserver(() => {
      if (placeHasIt()) {
        stop();
        return;
      }
      const found = heading();
      if (found) {
        stop();
        move(found);
      }
    });
    const theirs = () => {
      if (!ours) stop();
    };
    // After the new page has drawn: its heading may come a frame later, or
    // once its code has arrived. A page reached at a `#place` leaves it to
    // the landing (`landOn`), which focuses the place; if nothing takes the
    // focus meanwhile, its heading still gets it below (cubic on #82).
    const frame = requestAnimationFrame(() => {
      if (hash) return;
      const found = heading();
      if (found) {
        stop();
        move(found);
      } else observer.observe(document.body, { childList: true, subtree: true });
    });
    const wait = setTimeout(() => {
      // Not if the place has it: it may have taken it before this effect
      // began to listen. Anything else holding it is what had it before the
      // move (a link in the frame), so the fallback goes ahead; the person
      // moving it themselves since has stopped all this (CodeRabbit on #82).
      if (placeHasIt()) {
        stop();
        return;
      }
      const found = heading();
      if (hash && found) {
        stop();
        move(found);
        return;
      }
      const main = document.querySelector<HTMLElement>("main");
      if (!found && main) move(main);
      // And keep watching for the heading: at a #place too, whose watch the
      // frame above never began (CodeRabbit on #82).
      if (!found && hash) observer.observe(document.body, { childList: true, subtree: true });
    }, FOCUS_WAIT_MS);
    const giveUp = setTimeout(() => {
      stop();
    }, FOCUS_GIVE_UP_MS);
    function stop(): void {
      cancelAnimationFrame(frame);
      clearTimeout(wait);
      clearTimeout(giveUp);
      observer.disconnect();
      document.removeEventListener("focusin", theirs, true);
    }
    document.addEventListener("focusin", theirs, true);
    return stop;
  }, [pathname, hash]);
  return null;
}
