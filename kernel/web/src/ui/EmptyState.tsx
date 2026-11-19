/**
 * What a list or a page shows when there's nothing in it yet: what would be
 * here, and how to make the first one. Only for a load that succeeded and
 * found nothing: a load that failed is a `LoadError`, never this.
 */
import type { ReactNode } from "react";

export type EmptyStateProps = {
  /** "No roles of your own yet". */
  title: ReactNode;
  /** A line on what goes here, or why it's empty. */
  children?: ReactNode;
  /** The way to make the first one: a button or a link. */
  action?: ReactNode;
};

export function EmptyState({ title, children, action }: EmptyStateProps) {
  return (
    <div className="mf-empty">
      <p className="mf-empty-title">{title}</p>
      {children ? <p className="mf-empty-line">{children}</p> : null}
      {action ? <div className="mf-empty-action">{action}</div> : null}
    </div>
  );
}
