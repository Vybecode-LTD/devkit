/**
 * The frame the sign-in screens sit in (VM Website design/site/Auth.dc.html):
 * the site's name, home, and "Back to the site" above; one column of form
 * beside the site's mark; the year and the site's name below. No site menus:
 * a person signing in has one thing to do. Every public kernel page, the
 * landings from mail among them, sits in it.
 *
 * `AuthPanel` is a screen's column: its heading (focused when the screen
 * moves on to another step, `focus`), its lead line, then the form.
 */
import "./auth.css";

import { useEffect, useRef, type ReactNode } from "react";
import { Link, Outlet } from "react-router";

import { Skip } from "../app/frames";
import { useSite } from "../site/site";

export function AuthFrame() {
  const site = useSite();
  const mark = site?.logo ?? "";
  return (
    <div className="mf-auth mf-site-look">
      <Skip />
      <header className="mf-auth-header">
        <div className="mf-auth-bar">
          {site ? (
            <Link to="/" className="mf-auth-name">
              {mark ? <img src={mark} alt="" /> : null}
              {site.name}
            </Link>
          ) : (
            <span />
          )}
          <Link to="/" className="mf-text-link mf-auth-back">
            Back to the site
          </Link>
        </div>
      </header>
      <main id="main" className={mark ? "mf-auth-main" : "mf-auth-main mf-auth-main--alone"}>
        <Outlet />
        {mark ? (
          <div className="mf-auth-art" aria-hidden="true">
            <div className="mf-auth-art-frame">
              <img src={mark} alt="" />
            </div>
          </div>
        ) : null}
      </main>
      <footer className="mf-auth-footer">
        <div className="mf-auth-bar">
          <span>
            © {new Date().getFullYear()} {site?.name}
          </span>
        </div>
      </footer>
    </div>
  );
}

export type AuthPanelProps = {
  title: ReactNode;
  lead?: ReactNode;
  /** Which step the screen is at. */
  step?: string;
  /** A step the person moved to on this page: its heading takes the focus as it's drawn, so it's read from its top.
   * The page's first step leaves the focus to the move between pages (`RouteFocus`). */
  focus?: boolean;
  children?: ReactNode;
};

export function AuthPanel({ title, lead, step = "", focus = false, children }: AuthPanelProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus) heading.current?.focus();
  }, [focus, step]);
  return (
    <div className="mf-auth-panel">
      <h1 ref={heading} tabIndex={-1} className="mf-auth-title">
        {title}
      </h1>
      {lead ? <p className="mf-auth-lead">{lead}</p> : null}
      {children}
    </div>
  );
}

/** What went wrong with a form, said at once. */
export function FormError({ children }: { children: ReactNode }) {
  return children ? (
    <p className="mf-form-error" role="alert">
      {children}
    </p>
  ) : null;
}

/** The thin "or" between two ways in. The words are only drawn: each way's own label says what it is. */
export function Or() {
  return (
    <div className="mf-or" aria-hidden="true">
      or
    </div>
  );
}
