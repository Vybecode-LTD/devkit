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
 * page, all of it stops: theirs is never taken back (CodeRabbit on #79). On back and
 * forward the focus moves without scrolling, so the place ScrollRestoration
 * gives back stays (cubic on #79). The page is compared with the last one
 * focused for, so StrictMode's second run of the effect does nothing.
 */
import { useEffect, useRef } from "react";
import { NavigationType, useLocation, useNavigationType } from "react-router";

/** How long a page may take to show its heading before the focus goes to its main area. */
export const FOCUS_WAIT_MS = 3000;
/** How long a page's heading is watched for at all. */
export const FOCUS_GIVE_UP_MS = 30_000;

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
    // Set while this effect moves the focus itself, so only the person's own
    // moves stop it.
    let ours = false;
    const move = (target: HTMLElement) => {
      ours = true;
      try {
        focus(target, keepScroll);
      } finally {
        ours = false;
      }
    };
    const observer = new MutationObserver(() => {
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
    // once its code has arrived.
    const frame = requestAnimationFrame(() => {
      const found = heading();
      if (found) {
        stop();
        move(found);
      } else observer.observe(document.body, { childList: true, subtree: true });
    });
    const wait = setTimeout(() => {
      const main = document.querySelector<HTMLElement>("main");
      if (!heading() && main) move(main); // and keep watching for the heading
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
  }, [pathname, keepScroll]);
  return null;
}
