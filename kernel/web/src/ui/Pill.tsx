/**
 * Pills and chips (VM Website `admin_kit.py`, `pill`; the filter chips of
 * shell-slots.md). A `Pill` says how a thing stands (Live, Processing, Can't
 * play): words in its tone over its tint, with a dot. Its words carry the
 * meaning, never its colour alone.
 *
 * A `Chip` is a filter that's on or off (`aria-pressed`): outlined, and in
 * the accent with a check when pressed, so its state isn't shown by colour
 * alone (WCAG 1.4.1).
 */
import type { ComponentPropsWithRef, ReactNode } from "react";

import { Icon } from "./Icon";

/** A state's tone. Each has its words' colour and a tint behind them, from the theme. */
export type Tone = "neutral" | "success" | "warning" | "danger";

export function Pill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`mf-pill mf-pill--${tone}`}>
      <span className="mf-pill-dot" aria-hidden="true" />
      {children}
    </span>
  );
}

export type ChipProps = Omit<ComponentPropsWithRef<"button">, "onChange" | "type"> & {
  pressed: boolean;
  onPressedChange: (pressed: boolean) => void;
};

export function Chip({ pressed, onPressedChange, onClick, className, children, ...rest }: ChipProps) {
  return (
    <button
      {...rest}
      type="button"
      className={className ? `mf-chip ${className}` : "mf-chip"}
      aria-pressed={pressed}
      onClick={(event) => {
        onClick?.(event);
        onPressedChange(!pressed);
      }}
    >
      {pressed ? <Icon name="check" /> : null}
      {children}
    </button>
  );
}
