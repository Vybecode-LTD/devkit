/**
 * A dashboard card (SPEC 8, `admin.dashboard.widget`: scannable, one line of
 * status, a link to the detail; VM Website `AdminDashboard.dc.html`'s cards):
 * what it counts, its state as a pill, the figure, a line about it, and the
 * page that holds the detail. A module's widget draws one; the dashboard lays
 * them out in its grid.
 */
import { useId, type ReactNode } from "react";
import { Link } from "react-router";

import { Icon } from "./Icon";
import { Pill, type Tone } from "./Pill";

export type StatCardProps = {
  /** What it counts: "Plays this week". */
  label: string;
  /** The figure, or the state in a few words: "1,284", "All jobs running". */
  value: ReactNode;
  /** One line about it: "Up 18% on last week". */
  line?: ReactNode;
  /** How it stands, in words over its tone: Live, Not live, Clear. */
  state?: { tone: Tone; label: string };
  /** Where the detail is. */
  link?: { label: string; to: string };
  /** Its label's heading level: 2 on the dashboard, 3 inside a titled section. */
  level?: 2 | 3;
};

export function StatCard({ label, value, line, state, link, level = 2 }: StatCardProps) {
  const id = useId();
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <section className="mf-stat" aria-labelledby={id}>
      <div className="mf-stat-head">
        <Heading id={id} className="mf-stat-label">
          {label}
        </Heading>
        {state ? <Pill tone={state.tone}>{state.label}</Pill> : null}
      </div>
      <p className="mf-stat-value">{value}</p>
      {line === undefined || line === null || line === "" ? null : <p className="mf-stat-line">{line}</p>}
      {link ? (
        <Link className="mf-stat-link" to={link.to}>
          {link.label}
          <Icon name="chevron-right" />
        </Link>
      ) : null}
    </section>
  );
}
