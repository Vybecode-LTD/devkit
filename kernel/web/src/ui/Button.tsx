/**
 * The admin's buttons (VM Website `admin_kit.py`, `.a-btn`): secondary is
 * outlined, primary is filled with the accent and hovers to `accent-hover`.
 * One primary per view: the action the page is for.
 *
 * `large` is the sign-in screens' (VM Website `Auth.dc.html`): 54px, fully
 * round, a form's width. In the site's look (`.mf-site-look`, on the site's
 * frames) every button is fully round, and a medium one is the account
 * board's 44px.
 *
 * A `Button` is `type="button"` unless it says otherwise, so one in a form
 * never sends it by accident. `LinkButton` is a link drawn as a button, for a
 * move to another page ("View site", a Needs-you item's action).
 */
import type { ComponentPropsWithRef, ReactNode } from "react";
import { Link } from "react-router";

import { Icon } from "./Icon";
import type { IconName } from "./icons";

export type ButtonLook = {
  /** `primary` for the page's own action; `secondary` (the default) for the rest; `strong`, filled with the strongest words' colour, for sign-in's passkey. */
  variant?: "primary" | "secondary" | "strong" | undefined;
  /** `small` is the top bar's and a Needs-you item's: 34px against 38px; `large` is sign-in's 54px. */
  size?: "medium" | "small" | "large" | undefined;
  /** An icon after the words. */
  icon?: IconName | undefined;
};

export function buttonClass({ variant = "secondary", size = "medium" }: ButtonLook, extra?: string): string {
  return ["mf-button", `mf-button--${variant}`, size === "medium" ? "" : `mf-button--${size}`, extra ?? ""]
    .filter(Boolean)
    .join(" ");
}

function Words({ children, icon }: { children: ReactNode; icon: IconName | undefined }) {
  return (
    <>
      {children}
      {icon ? <Icon name={icon} size={16} /> : null}
    </>
  );
}

export type ButtonProps = ComponentPropsWithRef<"button"> & ButtonLook;

export function Button({ variant, size, icon, className, type = "button", children, ...rest }: ButtonProps) {
  return (
    <button {...rest} type={type} className={buttonClass({ variant, size }, className)}>
      <Words icon={icon}>{children}</Words>
    </button>
  );
}

export type LinkButtonProps = ComponentPropsWithRef<typeof Link> & ButtonLook;

export function LinkButton({ variant, size, icon, className, children, ...rest }: LinkButtonProps) {
  return (
    <Link {...rest} className={buttonClass({ variant, size }, className)}>
      <Words icon={icon}>{children}</Words>
    </Link>
  );
}
