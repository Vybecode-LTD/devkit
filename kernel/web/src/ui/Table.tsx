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
import type { FocusEvent, Key, ReactNode } from "react";

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

export function Table<Row>({ caption, captionHidden = false, columns, rows, rowKey, empty }: TableProps<Row>) {
  if (rows.length === 0) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;
  return (
    <div className="mf-table-scroll" onFocus={keepFocusInView}>
      <table className="mf-table">
        <caption className={captionHidden ? "mf-visually-hidden" : "mf-table-caption"}>{caption}</caption>
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
