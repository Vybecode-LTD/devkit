/**
 * A labelled form field (VM Website `admin_kit.py`, `.a-in`): its label, a
 * hint, the control, and what's wrong with what was typed. The control inside
 * (`Input`, `TextArea`, `Select`) takes its id, its description and whether
 * it's invalid from the field, so the label names it, a screen reader reads
 * the hint and the error with it, and nothing is wired twice by hand.
 *
 * `error` is what the server said of the field (`ApiProblem.errors[name]`) or
 * the form's own check; several are said together.
 *
 * `size="large"` is the sign-in screens' field (VM Website `Auth.dc.html`):
 * its label in the body's words, the control 54px at a 14px radius.
 *
 * `Switch` is a setting that's on or off at once (`role="switch"`), with its
 * label beside it.
 */
import { createContext, use, useId, type AriaAttributes, type ComponentPropsWithRef, type ReactNode } from "react";

import { shows } from "./words";

type FieldWiring = { id: string; describedBy: string | undefined; invalid: boolean };

const FieldContext = createContext<FieldWiring | null>(null);

export type FieldProps = {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | readonly string[] | undefined;
  /** The control's id, when something else needs it; one is made otherwise. A control's own id inside a field gives way to it. */
  id?: string;
  /** `large` for the sign-in screens. */
  size?: "medium" | "large";
  /** Beside the label, at its right: a link out of the form ("Forgot password?"), never inside the label. */
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
};

function words(error: FieldProps["error"]): string {
  if (error === undefined) return "";
  return typeof error === "string" ? error : error.join(" ");
}

export function Field({ label, hint, error, id, size = "medium", aside, className, children }: FieldProps) {
  const made = useId();
  const control = id ?? `${made}-control`;
  const said = words(error);
  const hinted = shows(hint);
  const hintId = hinted ? `${made}-hint` : undefined;
  const errorId = said ? `${made}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={["mf-field", size === "large" ? "mf-field--large" : "", className ?? ""].filter(Boolean).join(" ")}>
      {shows(aside) ? (
        <div className="mf-field-head">
          <label className="mf-field-label" htmlFor={control}>
            {label}
          </label>
          {aside}
        </div>
      ) : (
        <label className="mf-field-label" htmlFor={control}>
          {label}
        </label>
      )}
      {hinted ? (
        <p id={hintId} className="mf-field-hint">
          {hint}
        </p>
      ) : null}
      <FieldContext value={{ id: control, describedBy, invalid: Boolean(said) }}>{children}</FieldContext>
      {said ? (
        <p id={errorId} className="mf-field-error">
          {said}
        </p>
      ) : null}
    </div>
  );
}

/** The wiring a control takes from its field, under what the control was given itself. */
type Wired = {
  id?: string | undefined;
  "aria-describedby"?: string | undefined;
  "aria-invalid"?: AriaAttributes["aria-invalid"];
};

function useWiring<P extends Wired>(props: P): P {
  const field = use(FieldContext);
  if (!field) return props;
  const describedBy = [field.describedBy, props["aria-describedby"]].filter(Boolean).join(" ") || undefined;
  return {
    ...props,
    // The field's, over the control's own: the label points at it (cubic on #82). Give an id to `Field`.
    id: field.id,
    "aria-describedby": describedBy,
    "aria-invalid": props["aria-invalid"] ?? (field.invalid ? true : undefined),
  };
}

export function Input({ className, ...props }: ComponentPropsWithRef<"input">) {
  return <input {...useWiring(props)} className={className ? `mf-input ${className}` : "mf-input"} />;
}

export function TextArea({ className, ...props }: ComponentPropsWithRef<"textarea">) {
  return <textarea {...useWiring(props)} className={className ? `mf-input ${className}` : "mf-input"} />;
}

export function Select({ className, ...props }: ComponentPropsWithRef<"select">) {
  return <select {...useWiring(props)} className={className ? `mf-input mf-select ${className}` : "mf-input mf-select"} />;
}

export type SwitchProps = {
  label: ReactNode;
  hint?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
};

export function Switch({ label, hint, checked, onChange, disabled, className }: SwitchProps) {
  const id = useId();
  const hinted = shows(hint);
  return (
    <div className={className ? `mf-switch-row ${className}` : "mf-switch-row"}>
      <span className="mf-switch-words">
        <span id={`${id}-label`} className="mf-switch-label">
          {label}
        </span>
        {hinted ? (
          <span id={`${id}-hint`} className="mf-field-hint">
            {hint}
          </span>
        ) : null}
      </span>
      <button
        type="button"
        role="switch"
        className="mf-switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={hinted ? `${id}-hint` : undefined}
        disabled={disabled}
        onClick={() => {
          onChange(!checked);
        }}
      >
        <span className="mf-switch-knob" />
      </button>
    </div>
  );
}
