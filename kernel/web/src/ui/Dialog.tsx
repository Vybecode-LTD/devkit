/**
 * A modal dialog (ported from VybeSite's `pages/admin/sitePages/Dialog.tsx`):
 * a `<dialog>` named by its heading and opened as it's drawn, so the page
 * behind it is inert. Escape closes it; the parent draws it while it's open
 * and takes it away in `onClose`. Focus starts on the heading, so it's read
 * first, unless something inside took it already; on closing it goes back
 * to what had it before, or to `returnTo` when that's gone (a row removed).
 */
import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";

export type DialogProps = {
  title: ReactNode;
  onClose: () => void;
  /** Where focus goes on closing when what opened the dialog has gone. */
  returnTo?: RefObject<HTMLElement | null>;
  /** The heading, for a screen that must give it focus again. */
  heading?: RefObject<HTMLHeadingElement | null>;
  /** Room for a list, not a few fields. */
  wide?: boolean;
  children: ReactNode;
};

export function Dialog({ title, onClose, returnTo, heading, wide = false, children }: DialogProps) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const own = useRef<HTMLHeadingElement>(null);
  const titleRef = heading ?? own;
  const opener = useRef<Element | null>(typeof document === "undefined" ? null : document.activeElement);
  const close = useRef(onClose);
  const fallback = useRef(returnTo);
  useEffect(() => {
    close.current = onClose;
    fallback.current = returnTo;
  });

  useEffect(() => {
    const box = dialog.current;
    if (box && !box.open) box.showModal();
    if (!box?.contains(document.activeElement) || document.activeElement === box) titleRef.current?.focus();
    const had = opener.current;
    return () => {
      if (had instanceof HTMLElement && had.isConnected) had.focus();
      else fallback.current?.current?.focus();
    };
  }, [titleRef]);

  return (
    <dialog
      ref={dialog}
      className={wide ? "mf-dialog mf-dialog--wide" : "mf-dialog"}
      aria-labelledby={`${id}-title`}
      // Escape: a browser cancels and closes it; jsdom doesn't, so it's met here too.
      onCancel={(event) => {
        event.preventDefault();
        close.current();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          close.current();
        }
      }}
    >
      <h2 id={`${id}-title`} ref={titleRef} tabIndex={-1} className="mf-dialog-title">
        {title}
      </h2>
      {children}
    </dialog>
  );
}
