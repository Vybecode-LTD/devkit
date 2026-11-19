/**
 * A save someone else got to first (ported from VybeSite's
 * `components/SaveConflict.tsx`, for the kernel's settings: SPEC 7,
 * `kernel.settings`). The server saved nothing and answered 409
 * `kernel.settings_conflict` with each field both changed. Its sentence comes
 * first, in a status line that also describes the heading focus moves to;
 * then each field, theirs and yours side by side, asks Use theirs or Keep
 * mine. Once each is chosen, Save with these choices goes again
 * (`resolveConflict`); Back to the form puts it away, the edits kept, and
 * focus goes back to the form's Save.
 *
 * A secret is never sent back: both typed a new one, and that's all it says.
 */
import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";

import { ApiProblem } from "../api/problem";
import { Button } from "./Button";
import { when } from "./words";

export type FieldConflict = { field: string; yours: unknown; theirs: unknown } | { field: string; secret: true };

/** The conflict a settings save answered, as the kernel sends it in the problem's extra fields. */
export type SettingsConflict = {
  detail: string;
  /** The version to save at next. */
  version: number;
  conflicts: FieldConflict[];
  /** When the version that won was saved. */
  at: string | null;
};

export type Choices = Record<string, "theirs" | "mine">;

/** The conflict in a refused save, or null when the refusal is something else. */
export function settingsConflict(error: unknown): SettingsConflict | null {
  if (!(error instanceof ApiProblem) || error.code !== "kernel.settings_conflict") return null;
  const { version, conflicts, at } = error.extra;
  if (typeof version !== "number" || !Array.isArray(conflicts)) return null;
  return {
    detail: error.detail,
    version,
    conflicts: conflicts as FieldConflict[],
    at: typeof at === "string" ? at : null,
  };
}

/**
 * The save to send again: at the conflict's version, with what the person
 * changed, less each field where they chose theirs. `changes` must be only
 * what they changed: the server keeps every other field as it now stands.
 */
export function resolveConflict(
  changes: Readonly<Record<string, unknown>>,
  conflict: SettingsConflict,
  choices: Choices,
): { version: number; changes: Record<string, unknown> } {
  const theirs = new Set(conflict.conflicts.filter(({ field }) => choices[field] === "theirs").map(({ field }) => field));
  return { version: conflict.version, changes: Object.fromEntries(Object.entries(changes).filter(([field]) => !theirs.has(field))) };
}

/** A value as a form shows it: a switch on or off, a list a line each, a blank said as one. */
function shown(value: unknown): ReactNode {
  if (value === null || value === undefined) return <span className="mf-conflict-quiet">None</span>;
  if (value === "") return <span className="mf-conflict-quiet">Blank</span>;
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="mf-conflict-quiet">None</span>;
    return (
      <ul>
        {value.map((item, at) => (
          <li key={at}>{typeof item === "object" ? JSON.stringify(item) : String(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "bigint") return value.toString();
  return JSON.stringify(value);
}

export type SaveConflictProps = {
  conflict: SettingsConflict;
  /** Each field's label, as the form says it. */
  labels: Readonly<Record<string, string>>;
  saving: boolean;
  onResolve: (choices: Choices) => void;
  onCancel: () => void;
  /** How a field's value reads, where the default (its JSON) won't do: a stored id by its name. */
  format?: (field: string, value: unknown) => ReactNode;
  /** Where focus goes once it's put away; the form's submit button by default. */
  returnTo?: RefObject<HTMLElement | null>;
};

export function SaveConflict({ conflict, labels, saving, onResolve, onCancel, format, returnTo }: SaveConflictProps) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [choices, setChoices] = useState<Choices>({});
  // A new conflict (someone saved again meanwhile) is a fresh choice.
  const [seen, setSeen] = useState(conflict);
  if (seen !== conflict) {
    setSeen(conflict);
    setChoices({});
  }
  const back = useRef(returnTo);
  useEffect(() => {
    back.current = returnTo;
  });

  useEffect(() => {
    heading.current?.focus();
  }, [conflict]);

  // Gone, it hands focus back rather than leaving it on the page's body.
  useEffect(() => {
    const form = panel.current?.closest("form");
    return () => {
      const at = document.activeElement;
      if (at && at !== document.body && document.contains(at)) return;
      const target = back.current?.current ?? form?.querySelector<HTMLElement>('[type="submit"]');
      target?.focus();
    };
  }, []);

  const ready = conflict.conflicts.every((each) => choices[each.field]);
  const value = (field: string, raw: unknown) => (format ? format(field, raw) : shown(raw));

  return (
    <div ref={panel} role="group" aria-labelledby={`${id}-title`} className="mf-conflict">
      <h3 id={`${id}-title`} ref={heading} tabIndex={-1} className="mf-conflict-title" aria-describedby={`${id}-said`}>
        Saved by someone else since you opened it
      </h3>
      <p id={`${id}-said`} role="status" className="mf-conflict-said">
        {conflict.detail}
      </p>
      {conflict.conflicts.map((each) => {
        const name = `${id}-${each.field}`;
        const secret = "secret" in each;
        const choose = (choice: "theirs" | "mine") => {
          setChoices((now) => ({ ...now, [each.field]: choice }));
        };
        return (
          <fieldset key={each.field} className="mf-conflict-field">
            <legend>{labels[each.field] ?? each.field}</legend>
            <div className="mf-conflict-sides">
              <div className="mf-conflict-side">
                <label className="mf-conflict-pick">
                  <input
                    type="radio"
                    name={name}
                    checked={choices[each.field] === "theirs"}
                    onChange={() => {
                      choose("theirs");
                    }}
                  />
                  Use theirs
                </label>
                <p className="mf-conflict-who">Theirs{conflict.at ? `, ${when(conflict.at)}` : ""}</p>
                <div className="mf-conflict-value">{secret ? "A new one they typed" : value(each.field, each.theirs)}</div>
              </div>
              <div className="mf-conflict-side">
                <label className="mf-conflict-pick">
                  <input
                    type="radio"
                    name={name}
                    checked={choices[each.field] === "mine"}
                    onChange={() => {
                      choose("mine");
                    }}
                  />
                  Keep mine
                </label>
                <p className="mf-conflict-who">Yours</p>
                <div className="mf-conflict-value">{secret ? "The one you typed" : value(each.field, each.yours)}</div>
              </div>
            </div>
          </fieldset>
        );
      })}
      {ready ? null : (
        <p id={`${id}-wait`} className="mf-conflict-quiet">
          Choose theirs or yours for each field to save.
        </p>
      )}
      <div className="mf-conflict-actions">
        <Button
          variant="primary"
          disabled={!ready || saving}
          aria-describedby={ready ? undefined : `${id}-wait`}
          onClick={() => {
            onResolve(choices);
          }}
        >
          {saving ? "Saving…" : "Save with these choices"}
        </Button>
        <Button onClick={onCancel}>Back to the form</Button>
      </div>
    </div>
  );
}
