/**
 * A load that failed, said as a failure (ported from VybeSite's
 * `components/LoadError.tsx`). Never an empty list in its place ("No people
 * yet" when they couldn't be read) and never an empty form, which could be
 * saved over what's really stored. The server's own words follow, then Try
 * again. Children sit beside Try again, such as a way back. `inline` drops
 * the card, for a failure inside a panel that's a card already.
 */
import type { ReactNode } from "react";

import { ApiProblem } from "../api/problem";
import { Button } from "./Button";

/** What a failure says, in words: the server's detail or title, an error's message. */
export function failureWords(error: unknown): string {
  if (error instanceof ApiProblem) return error.detail || error.title;
  if (error instanceof Error) return error.message;
  return typeof error === "string" ? error : "";
}

export type LoadErrorProps = {
  /** What couldn't be loaded, as the sentence's subject: "The people". */
  what: string;
  error: unknown;
  onRetry: () => void;
  inline?: boolean;
  children?: ReactNode;
};

export function LoadError({ what, error, onRetry, inline = false, children }: LoadErrorProps) {
  const said = failureWords(error);
  return (
    <div className={inline ? "mf-load-error mf-load-error--inline" : "mf-load-error"} role="alert">
      <p className="mf-load-error-what">{what} couldn't be loaded.</p>
      {said ? <p className="mf-load-error-why">{said}</p> : null}
      <div className="mf-load-error-actions">
        <Button size="small" onClick={onRetry}>
          Try again
        </Button>
        {children}
      </div>
    </div>
  );
}
