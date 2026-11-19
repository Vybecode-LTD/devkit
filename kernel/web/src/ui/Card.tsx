/**
 * A card (VM Website `admin_kit.py`, `card` and `h2`): a panel on the
 * surface, with an optional heading row whose actions sit at its right.
 * `flush` drops the padding, for a table that fills the card to its edges.
 * `description` is a line under the title, as each of the account board's
 * cards has.
 */
import { useId, type ReactNode } from "react";

import { shows } from "./words";

export type CardProps = {
  title?: ReactNode;
  /** A line under the title: what the card is for. */
  description?: ReactNode;
  /** The heading's level: 2 on a page, 3 inside a section that has its own. */
  level?: 2 | 3;
  /** Beside the title, at the right: a link or a button. */
  actions?: ReactNode;
  flush?: boolean;
  className?: string;
  children: ReactNode;
};

export function Card({ title, description, level = 2, actions, flush = false, className, children }: CardProps) {
  const id = useId();
  const titled = shows(title);
  const Heading = level === 3 ? "h3" : "h2";
  const classes = ["mf-card", flush ? "mf-card--flush" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <section className={classes} aria-labelledby={titled ? id : undefined}>
      {titled ? (
        <div className="mf-card-head">
          {shows(description) ? (
            <div className="mf-card-words">
              <Heading id={id} className="mf-card-title">
                {title}
              </Heading>
              <p className="mf-card-description">{description}</p>
            </div>
          ) : (
            <Heading id={id} className="mf-card-title">
              {title}
            </Heading>
          )}
          {shows(actions) ? <div className="mf-card-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
