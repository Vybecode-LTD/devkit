/**
 * After a move to another page, puts the keyboard's focus on its heading, so
 * a screen reader reads the new page and Tab starts from its top. The first
 * page is left as the browser opened it.
 *
 * A page whose code is still loading draws nothing at first, so the focus
 * waits for its heading to appear (Codex on #79). A page that shows none
 * within `FOCUS_WAIT_MS` has its main area focused instead. On back and
 * forward the focus moves without scrolling, so the place ScrollRestoration
 * gives back stays (cubic on #79). The page is compared with the last one
 * focused for, so StrictMode's second run of the effect does nothing.
 */
import { useEffect, useRef } from "react";
import { NavigationType, useLocation, useNavigationType } from "react-router";

/** How long a page may take to show its heading before the focus goes to its main area. */
export const FOCUS_WAIT_MS = 3000;

function focus(target: HTMLElement, keepScroll: boolean): void {
  if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: keepScroll });
}

function heading(): HTMLElement | null {
  return document.querySelector<HTMLElement>("main h1");
}

export function RouteFocus() {
  const { pathname } = useLocation();
  const keepScroll = useNavigationType() === NavigationType.Pop;
  const last = useRef(pathname);
  useEffect(() => {
    if (last.current === pathname) return;
    last.current = pathname;
    let done = false;
    const land = (target: HTMLElement) => {
      done = true;
      observer.disconnect();
      focus(target, keepScroll);
    };
    const observer = new MutationObserver(() => {
      const found = heading();
      if (found) land(found);
    });
    // After the new page has drawn: its heading may come a frame later, or
    // once its code has arrived.
    const frame = requestAnimationFrame(() => {
      const found = heading();
      if (found) land(found);
      else observer.observe(document.body, { childList: true, subtree: true });
    });
    const timer = setTimeout(() => {
      const main = document.querySelector<HTMLElement>("main");
      if (!done && main) land(main);
      observer.disconnect();
    }, FOCUS_WAIT_MS);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [pathname, keepScroll]);
  return null;
}
