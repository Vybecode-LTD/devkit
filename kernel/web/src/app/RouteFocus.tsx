/**
 * After a move to another page, puts the keyboard's focus on its heading, so
 * a screen reader reads the new page and Tab starts from its top. The first
 * page is left as the browser opened it.
 */
import { useEffect, useRef } from "react";
import { useLocation } from "react-router";

export function RouteFocus() {
  const { pathname } = useLocation();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    // After the new page has drawn: its heading may come a frame later.
    const frame = requestAnimationFrame(() => {
      const heading = document.querySelector<HTMLElement>("main h1") ?? document.querySelector<HTMLElement>("main");
      if (!heading) return;
      if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: false });
    });
    return () => {
      cancelAnimationFrame(frame);
    };
  }, [pathname]);
  return null;
}
