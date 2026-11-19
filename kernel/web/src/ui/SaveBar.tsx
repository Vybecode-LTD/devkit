/**
 * The bar that holds a form's Save while it has changes (VM Website
 * `admin_kit.py`, `savebar`): stuck to the bottom of the window, with how
 * many changes aren't saved, Discard and Save.
 *
 * While it shows, the page's `scroll-padding-bottom` is its height and the
 * gap below it, so a control the keyboard reaches is never scrolled under it
 * (WCAG 2.4.11, focus not obscured): `--mf-save-bar-room` on the root, which
 * the kit's stylesheet reads.
 */
import { useLayoutEffect, useRef } from "react";

import { Button } from "./Button";

export type SaveBarProps = {
  /** How many fields have changed; the bar shows only while it's more than none. */
  changes: number;
  onSave: () => void;
  onDiscard: () => void;
  saving?: boolean;
  /** The save's words: "Save" by default, "Save and go live" where saving publishes. */
  saveLabel?: string;
};

/** The room the bar takes below what scrolls: its height, its 16px gap, and the 8px a focus ring needs. */
export const SAVE_BAR_ROOM = "--mf-save-bar-room";

export function SaveBar({ changes, onSave, onDiscard, saving = false, saveLabel = "Save" }: SaveBarProps) {
  const bar = useRef<HTMLDivElement>(null);
  const shown = changes > 0;

  useLayoutEffect(() => {
    const element = bar.current;
    if (!shown || !element) return;
    const root = document.documentElement;
    const measure = () => {
      root.style.setProperty(SAVE_BAR_ROOM, `${String(Math.ceil(element.getBoundingClientRect().height) + 24)}px`);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    return () => {
      observer?.disconnect();
      root.style.removeProperty(SAVE_BAR_ROOM);
    };
  }, [shown]);

  if (!shown) return null;
  return (
    <div ref={bar} className="mf-save-bar" role="region" aria-label="Changes not saved">
      <span className="mf-save-bar-dot" aria-hidden="true" />
      <span className="mf-save-bar-words">
        {changes === 1 ? "1 change not saved" : `${String(changes)} changes not saved`}
      </span>
      <span className="mf-save-bar-actions">
        <Button onClick={onDiscard} disabled={saving}>
          Discard
        </Button>
        <Button variant="primary" onClick={onSave} disabled={saving}>
          {saving ? "Saving…" : saveLabel}
        </Button>
      </span>
    </div>
  );
}
