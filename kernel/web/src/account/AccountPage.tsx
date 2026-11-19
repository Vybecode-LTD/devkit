/**
 * What every account page shares (VM Website design/site/Account.dc.html):
 * who is signed in, the account's pages as pills, the page's display title
 * and its lead; then the page. And the small parts its cards are made of:
 * rows of a name, a line under it and its actions; a day as words; and
 * `useAction`, which runs a write, says how it went and asks the caches
 * that changed to read again.
 */
import "./account.css";

import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router";

import { ApiProblem } from "../api/problem";
import { useTitle } from "../app/pages/KernelPages";
import { refusedQuietly } from "../auth/StepUp";
import { said } from "../auth/words";
import { Seo } from "../seo/Seo";
import { useSession } from "../session/session";
import { useToast } from "../ui/Toast";

const PAGES = [
  { to: "/account", label: "Sign-in and security" },
  { to: "/account/notifications", label: "Notifications" },
  { to: "/account/activity", label: "Activity" },
] as const;

export function AccountPage({ page, title, lead, children }: { page: string; title: string; lead: ReactNode; children: ReactNode }) {
  const session = useSession();
  const heading = useTitle(page);
  return (
    <div className="mf-account">
      <Seo title={heading} noindex />
      <div className="mf-account-head">
        {session.status === "signed-in" ? <p className="mf-account-who">Signed in as {session.user.email}</p> : null}
        <nav aria-label="Your account" className="mf-account-nav">
          <ul>
            {PAGES.map((each) => (
              <li key={each.to}>
                <NavLink to={each.to} end>
                  {each.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <h1 className="mf-account-title">{title}</h1>
        <p className="mf-account-lead">{lead}</p>
      </div>
      {children}
    </div>
  );
}

export function Rows({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <ul className="mf-rows" aria-label={label}>
      {children}
    </ul>
  );
}

export function Row({ name, meta, actions }: { name: ReactNode; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <li className="mf-row">
      <span className="mf-row-words">
        <span className="mf-row-name">{name}</span>
        {meta ? <span className="mf-row-meta">{meta}</span> : null}
      </span>
      {actions ? <span className="mf-row-actions">{actions}</span> : null}
    </li>
  );
}

/** A day, as the reader's browser writes one ("18 Nov 2026"), in a `<time>`. */
export function Day({ at }: { at: string }) {
  const day = new Date(at);
  const shown = Number.isNaN(day.getTime()) ? at : day.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  return <time dateTime={at}>{shown}</time>;
}

type Outcome = { done?: string; refused?: Readonly<Record<string, string>>; reads?: readonly QueryKey[] };

/** How a write went: its words when refused (none for a closed prompt) and the refusal's code. */
export type Done = { ok: boolean; error: string; code: string };

/**
 * Runs a write: `busy` while it's on its way, then the caches named in
 * `reads` read again, and a note to say it's done. A refusal comes back as
 * its words, for the dialog that asked to show, or as a note when no dialog
 * is open (`toastRefusal`). A closed step-up or passkey prompt says nothing.
 */
export function useAction() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async (work: () => Promise<unknown>, outcome: Outcome = {}, toastRefusal = false): Promise<Done> => {
    setBusy(true);
    try {
      await work();
      await Promise.all((outcome.reads ?? []).map((queryKey) => queryClient.invalidateQueries({ queryKey })));
      if (outcome.done) toast({ tone: "success", text: outcome.done });
      return { ok: true, error: "", code: "" };
    } catch (caught) {
      if (refusedQuietly(caught)) return { ok: false, error: "", code: "" };
      const words = caught instanceof ApiProblem ? said(caught, outcome.refused) : "Your browser couldn't do that here.";
      if (toastRefusal) toast({ tone: "danger", text: words });
      return { ok: false, error: words, code: caught instanceof ApiProblem ? caught.code : "" };
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}
