/**
 * One item of the dashboard's "Needs you" list (SPEC 8, the owner's lens;
 * VM Website `admin_kit.py`, `attention`): what's wrong, why it matters, and
 * the one action that fixes it. Its edge is in its tone, and its icon and
 * words say the tone too, so colour is never the only sign. `info` is worth
 * knowing with nothing wrong (the board's "The spotlight single ends in 2
 * days"; K4.6).
 */
import type { ReactNode } from "react";

import { LinkButton } from "./Button";
import { Icon } from "./Icon";

export type AttentionProps = {
  tone: "info" | "warning" | "danger";
  /** What's wrong, in a few words: "The site has no description". */
  what: ReactNode;
  /** Why it matters: "Search engines show the first words of the home page instead." */
  why: ReactNode;
  /** Where it's fixed. */
  action?: { label: string; to: string };
};

const LABEL = { info: "Note", warning: "Warning", danger: "Problem" } as const;

export function Attention({ tone, what, why, action }: AttentionProps) {
  return (
    <div className={`mf-attention mf-attention--${tone}`}>
      <Icon name={tone === "info" ? "info" : "warning"} label={LABEL[tone]} className="mf-attention-icon" />
      <div className="mf-attention-words">
        <span className="mf-attention-what">{what}</span>
        <span className="mf-attention-why">{why}</span>
      </div>
      {action ? (
        <LinkButton to={action.to} size="small">
          {action.label}
        </LinkButton>
      ) : null}
    </div>
  );
}
