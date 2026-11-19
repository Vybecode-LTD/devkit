/**
 * A table of records (VM Website `admin_kit.py`; shell-slots.md's Table),
 * in a scroller that slides sideways on a narrow screen.
 *
 * Keyboard focus inside it (the owner, 2026-11-18): the scroller keeps
 * `scroll-padding-inline: 10px`, so a control focus scrolls to sits clear of
 * its edge with its ring showing, and a `focusin` handler scrolls the focused
 * control into view itself, since Chrome leaves one cut off when 20px of it
 * already shows. When Chrome makes the scroller a tab stop of its own (it
 * scrolls and holds nothing focusable), its ring is drawn inside it.
 *
 * Each column says how to draw its cell; `empty` is what shows when there are
 * no rows, an `EmptyState` by default.
 */
import { useId, useLayoutEffect, useState, type FocusEvent, type Key, type ReactNode } from "react";

import { EmptyState } from "./EmptyState";

export type Column<Row> = {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  /** `end` for numbers and actions. */
  align?: "start" | "end";
};

export type TableProps<Row> = {
  /** What the table holds: its caption, which names it. */
  caption: ReactNode;
  /** Keep the caption for screen readers only, when a heading above already says it. */
  captionHidden?: boolean;
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => Key;
  empty?: ReactNode;
};

/** Scrolls the control that took the focus into view inside the scroller: Chrome won't if part of it shows. */
export function keepFocusInView(event: FocusEvent<HTMLDivElement>): void {
  if (event.target === event.currentTarget) return;
  event.target.scrollIntoView({ block: "nearest", inline: "nearest" });
}

/**
 * Whether the scroller slides sideways: then it's a tab stop of its own, so
 * a keyboard can move along a table of words alone in a browser that doesn't
 * make a scroller focusable itself (cubic on #82).
 */
function useOverflows(): [(element: HTMLDivElement | null) => void, boolean] {
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const [overflows, setOverflows] = useState(false);
  useLayoutEffect(() => {
    if (!element) return;
    const measure = () => {
      setOverflows(element.scrollWidth > element.clientWidth);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    // The table too: rows growing wider leave the scroller's own size as it was (CodeRabbit on #82).
    const table = element.querySelector("table");
    if (table) observer?.observe(table);
    return () => {
      observer?.disconnect();
    };
  }, [element]);
  return [setElement, overflows];
}

export function Table<Row>({ caption, captionHidden = false, columns, rows, rowKey, empty }: TableProps<Row>) {
  const id = useId();
  const [scroller, overflows] = useOverflows();
  const captionClass = captionHidden ? "mf-visually-hidden" : "mf-table-caption";
  // Empty, it keeps its caption, so two empty tables are told apart (cubic on #82).
  if (rows.length === 0) {
    return (
      <div role="group" aria-labelledby={`${id}-caption`} className="mf-table-empty">
        <p id={`${id}-caption`} className={captionClass}>
          {caption}
        </p>
        {empty ?? <EmptyState title="Nothing here yet" />}
      </div>
    );
  }
  return (
    <div
      ref={scroller}
      className="mf-table-scroll"
      onFocus={keepFocusInView}
      {...(overflows ? { tabIndex: 0, role: "region", "aria-labelledby": `${id}-caption` } : {})}
    >
      <table className="mf-table">
        <caption id={`${id}-caption`} className={captionClass}>
          {caption}
        </caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.align === "end" ? "mf-cell-end" : undefined}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td key={column.key} className={column.align === "end" ? "mf-cell-end" : undefined}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
