/**
 * One collapsible section of a long admin page (ported from VybeSite's
 * `components/Accordion.tsx`; drawn as VM Website's `accordion`).
 *
 * Built on `<details>` and `<summary>`, so the keyboard, a screen reader and
 * find-in-page work with no script of ours.
 *
 * - `state` is how the section stands, as a pill on its title line, open or
 *   shut. A section whose first state needs attention (a warning or a danger)
 *   opens by itself, so a problem is never folded away; a state that turns
 *   later keeps to its pill and never springs open under the reader.
 * - `meta` is what it holds (a count, a verdict), shown only while it's shut,
 *   since the body then says the same thing properly.
 * - `said` is spoken when it changes while the section is shut: an outcome a
 *   screen reader would never reach in a shut body. Pass `""` from the first
 *   render when there's nothing to say yet, so the status line is there
 *   before its words arrive.
 *
 * Which sections a reader opens or shuts is remembered in `localStorage`
 * under `id`. Only their own clicks count: a section that opens for its
 * state, or because a link landed inside it (`landOn`), wasn't their choice.
 * Storage can throw in a private window, so it's guarded.
 */
import { useId, useLayoutEffect, useRef, useState, type ReactNode, type SyntheticEvent } from "react";

import { Icon } from "./Icon";
import { Pill, type Tone } from "./Pill";
import { OPENED_BY_LINK } from "./place";

export type SectionState = { tone: Tone; label: string };

export type AccordionProps = {
  id: string;
  title: ReactNode;
  /** Its title's heading level: 3 inside a section whose own title is an h2. */
  level?: 2 | 3 | 4;
  meta?: ReactNode;
  state?: SectionState;
  said?: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

const needsAttention = (state: SectionState | undefined): boolean =>
  state?.tone === "warning" || state?.tone === "danger";

export function Accordion({ id, title, level = 2, meta, state, said, defaultOpen = false, children }: AccordionProps) {
  const titleId = useId();
  const attention = needsAttention(state);
  const [open, setOpen] = useState(() => attention || (remembered(id) ?? defaultOpen));
  // What this component last made the section, so the toggle event that only
  // echoes its own change is told apart from the reader's click.
  const shown = useRef(open);
  const touched = useRef(false);
  const arrived = useRef(state !== undefined);
  const hasState = state !== undefined;

  // A first state that arrives needing attention (once the page's data comes
  // in) opens the section, unless the reader has moved it already.
  useLayoutEffect(() => {
    if (!hasState) return;
    const first = !arrived.current;
    arrived.current = true;
    if (first && attention && !touched.current && !shown.current) {
      shown.current = true;
      setOpen(true);
    }
  }, [hasState, attention]);

  // `said`, taken when it changes while the section is shut; opening empties it.
  const [heard, setHeard] = useState({ said, spoken: "" });
  if (heard.said !== said) setHeard({ said, spoken: open ? "" : (said ?? "") });
  const spoken = heard.said === said ? heard.spoken : "";

  function onToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    // React hands a toggle up to every section around the one that moved.
    if (event.target !== event.currentTarget) return;
    const section = event.currentTarget;
    const next = section.open;
    const byLink = section.hasAttribute(OPENED_BY_LINK);
    section.removeAttribute(OPENED_BY_LINK);
    if (next === shown.current) return;
    shown.current = next;
    setOpen(next);
    if (next) setHeard((now) => (now.spoken ? { ...now, spoken: "" } : now));
    if (byLink) return;
    touched.current = true;
    remember(id, next);
  }

  const Heading = level === 4 ? "h4" : level === 3 ? "h3" : "h2";
  const section = (
    <details className="mf-accordion" open={open} onToggle={onToggle} aria-labelledby={titleId}>
      <summary className="mf-accordion-summary">
        <Heading id={titleId} className="mf-accordion-title">
          {title}
        </Heading>
        {meta && !open ? <span className="mf-accordion-meta">{meta}</span> : null}
        {state ? <Pill tone={state.tone}>{state.label}</Pill> : null}
        <Icon name="chevron-down" className="mf-accordion-chevron" />
      </summary>
      <div className="mf-accordion-body">{children}</div>
    </details>
  );
  if (said === undefined) return section;
  return (
    <>
      {section}
      <span className="mf-visually-hidden" role="status">
        {spoken}
      </span>
    </>
  );
}

const OPEN_KEY = "mf_open_sections";

/** Whether this reader last left the section open, or null if unknown. */
function remembered(id: string): boolean | null {
  try {
    const raw = window.localStorage.getItem(OPEN_KEY);
    if (!raw) return null;
    const map = JSON.parse(raw) as Record<string, unknown>;
    const value = map[id];
    return typeof value === "boolean" ? value : null;
  } catch {
    return null;
  }
}

function remember(id: string, open: boolean): void {
  try {
    const raw = window.localStorage.getItem(OPEN_KEY);
    const map = raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
    map[id] = open;
    window.localStorage.setItem(OPEN_KEY, JSON.stringify(map));
  } catch {
    // A private window, or storage switched off: the default is fine.
  }
}
