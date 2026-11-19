/**
 * An admin page's header (VM Website `AdminDashboard.dc.html`, shell-slots.md
 * "Page header"): its title, one line of context, and its actions at the
 * right, the primary one filled, the rest outlined. The page's words follow.
 *
 * The top bar's breadcrumb ends in the sidebar's name for the page; `crumb`
 * says it otherwise ("Activity log" where the sidebar says "Activity"). The
 * head's title is "{page} · {site}", `page` being the kernel's or the
 * module's name for it.
 */
import { createContext, useContext, useLayoutEffect, type ReactNode } from "react";

import { useTitle } from "../app/pages/KernelPages";
import { Seo } from "../seo/Seo";

/** The frame's: what the breadcrumb's last part says while a page is drawn. */
export const CrumbContext = createContext<(crumb: string | undefined) => void>(() => undefined);

export type AdminPageProps = {
  /** The head's title: "Dashboard", "Activity". */
  page: string;
  /** The page's heading: "Good evening", "Activity log". */
  title: ReactNode;
  /** One line under it: what the page is for, or how things stand. */
  lead?: ReactNode;
  /** At the right of the heading: the primary action and any others. */
  actions?: ReactNode;
  /** The breadcrumb's last part, when it isn't the sidebar's name for the page. */
  crumb?: string;
  children: ReactNode;
};

export function AdminPage({ page, title, lead, actions, crumb, children }: AdminPageProps) {
  const setCrumb = useContext(CrumbContext);
  useLayoutEffect(() => {
    setCrumb(crumb);
    return () => {
      setCrumb(undefined);
    };
  }, [crumb, setCrumb]);
  return (
    <>
      <Seo title={useTitle(page)} noindex />
      <div className="mf-admin-page-head">
        <div className="mf-admin-page-words">
          <h1 className="mf-admin-page-title">{title}</h1>
          {lead === undefined || lead === null || lead === "" ? null : <p className="mf-admin-page-lead">{lead}</p>}
        </div>
        {actions ? <div className="mf-admin-page-actions">{actions}</div> : null}
      </div>
      {children}
    </>
  );
}
