/**
 * A settings section's history, one click deeper (ported from VybeSite's
 * `components/SectionHistory.tsx`; the kernel keeps every version, SPEC 7):
 * a shut accordion at the foot of the section, saying how many saves it
 * holds, and read only once it's opened, and again when a save moves the
 * section on while it's open.
 *
 * Each save, newest first: who, how and when, and what it changed, by label.
 * `load` reads it (the admin's settings history route); `names` gives each
 * saver's name by their id. The kernel's versions keep no values, so there's
 * no "load into the form" as VybeSite has.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Icon } from "./Icon";
import { LoadError } from "./LoadError";
import { and, quoted, when } from "./words";

/** One saved version, as `kernel.settings.history` answers it. */
export type HistoryVersion = {
  number: number;
  changed: string[];
  /** How it was saved: "form" for the admin's form; a module may name others. */
  via: string;
  saved_at: string;
  saved_by_id: string | null;
};

export type SectionHistoryProps = {
  /** The version the form holds: how many saves there are. Null until the form is read. */
  version: number | null;
  /** Each field's label, as the form says it. */
  labels: Readonly<Record<string, string>>;
  load: () => Promise<readonly HistoryVersion[]>;
  /** Savers' names by their id. */
  names?: Readonly<Record<string, string>>;
};

function how(via: string): string {
  return via === "form" ? "in the form" : `by ${via}`;
}

export function SectionHistory({ version, labels, load, names = {} }: SectionHistoryProps) {
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [versions, setVersions] = useState<readonly HistoryVersion[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const asked = useRef(0);
  const reader = useRef(load);
  useEffect(() => {
    reader.current = load;
  });

  // Its answer, never an earlier one that comes late, replaces what's shown.
  const read = useCallback(() => {
    const mine = ++asked.current;
    reader.current().then(
      (got) => {
        if (mine !== asked.current) return;
        setError(null);
        setVersions(got);
      },
      (failed: unknown) => {
        if (mine === asked.current) setError(failed ?? new Error("It couldn't be read."));
      },
    );
  }, []);
  const again = () => {
    setError(null);
    read();
  };

  useEffect(() => {
    if (open) read();
  }, [open, version, read]);

  if (version === null) return null;
  // The newest the history knows, or the form's own once a save moves past it while shut.
  const saves = Math.max(versions?.[0]?.number ?? 0, version);
  const count = saves === 0 ? "no saves yet" : saves === 1 ? "1 save" : `${String(saves)} saves`;
  const newest = versions?.[0]?.number;

  return (
    <details
      className="mf-accordion mf-history"
      open={open}
      aria-labelledby={titleId}
      onToggle={(event) => {
        if (event.target === event.currentTarget) setOpen(event.currentTarget.open);
      }}
    >
      <summary className="mf-accordion-summary">
        <h3 id={titleId} className="mf-accordion-title">
          History · {count}
        </h3>
        <Icon name="chevron-down" className="mf-accordion-chevron" />
      </summary>
      <div className="mf-accordion-body">
        {error ? (
          <LoadError what="The history" error={error} onRetry={again} inline />
        ) : versions === null ? (
          <p className="mf-history-quiet">Loading…</p>
        ) : versions.length === 0 ? (
          <p className="mf-history-quiet">No saves yet: each save from now on is kept here.</p>
        ) : (
          <ol className="mf-history-list">
            {versions.map((each) => {
              const changed = each.changed.map((field) => quoted(labels[field] ?? field));
              const who = (each.saved_by_id && names[each.saved_by_id]) || "Someone";
              return (
                <li key={each.number}>
                  <h4 className="mf-history-version">Version {each.number}</h4>
                  <p>
                    {who}, {how(each.via)}, <time dateTime={each.saved_at}>{when(each.saved_at)}</time>.
                    {changed.length > 0 ? ` Changed ${and(changed)}.` : ""}
                  </p>
                  {each.number === newest ? <p className="mf-history-quiet">What's saved now.</p> : null}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </details>
  );
}
