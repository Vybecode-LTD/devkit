/**
 * Short notes after an action ("Role saved"), in the top corner of the
 * window. Two live regions are on the page from the start, so a screen reader
 * hears each note as it arrives: a polite one, and an assertive one for a
 * failure (`aria-live` alone, so a page's own status lines keep their role). A note goes after `TOAST_MS`, but stays while the pointer is over
 * it or the keyboard is in it (WCAG 2.2.1), and has its own Close.
 *
 * `useToast()` gives `toast({tone, text})`; the provider is in every page's
 * tree (`KernelProviders`), and draws the notes at the end of the body. A note is for news only: anything the person must
 * act on belongs on the page.
 */
import { createContext, use, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Icon } from "./Icon";

export type ToastTone = "success" | "danger" | "neutral";
export type ToastNote = { tone?: ToastTone; text: string };
type Shown = ToastNote & { id: number };

/** How long a note shows, unless it's held. */
export const TOAST_MS = 8000;

const ToastContext = createContext<((note: ToastNote) => void) | null>(null);

/** `toast({tone, text})`; outside a provider (a module's test without the kernel's) it does nothing. */
export function useToast(): (note: ToastNote) => void {
  return use(ToastContext) ?? noToast;
}

const noToast = (): void => undefined;

function Note({ note, onClose }: { note: Shown; onClose: (id: number) => void }) {
  // The pointer and the keyboard each hold it, apart: one leaving never lets
  // it go while the other is still in it (Codex on #82).
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const held = hovered || focused;
  useEffect(() => {
    if (held) return;
    const timer = setTimeout(() => {
      onClose(note.id);
    }, TOAST_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [held, note.id, onClose]);
  return (
    <div
      className={`mf-toast mf-toast--${note.tone ?? "neutral"}`}
      onPointerEnter={() => {
        setHovered(true);
      }}
      onPointerLeave={() => {
        setHovered(false);
      }}
      onFocus={() => {
        setFocused(true);
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false);
      }}
    >
      <span className="mf-toast-text">{note.text}</span>
      <button
        type="button"
        className="mf-toast-close"
        aria-label="Close"
        onClick={() => {
          onClose(note.id);
        }}
      >
        <Icon name="close" />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [notes, setNotes] = useState<Shown[]>([]);
  const next = useRef(0);
  const toast = useCallback((note: ToastNote) => {
    next.current += 1;
    const id = next.current;
    setNotes((now) => [...now, { ...note, id }]);
  }, []);
  const close = useCallback((id: number) => {
    setNotes((now) => now.filter((note) => note.id !== id));
  }, []);
  const polite = notes.filter((note) => note.tone !== "danger");
  const urgent = notes.filter((note) => note.tone === "danger");
  return (
    <ToastContext value={toast}>
      {children}
      {createPortal(
        <div className="mf-toasts">
          <div aria-live="polite" className="mf-toast-region">
            {polite.map((note) => (
              <Note key={note.id} note={note} onClose={close} />
            ))}
          </div>
          <div aria-live="assertive" className="mf-toast-region">
            {urgent.map((note) => (
              <Note key={note.id} note={note} onClose={close} />
            ))}
          </div>
        </div>,
        document.body,
      )}
    </ToastContext>
  );
}
