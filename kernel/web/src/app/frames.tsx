/**
 * The frames pages sit in (K4 contract §2): the site's, around public, kernel
 * and member pages, with `nav.public`, `nav.member` and `site.footer`; and the
 * admin's, with the sidebar in its order. The admin's look comes with K4.6;
 * this is its structure.
 *
 * The site frame holds no heading or paragraph of its own, so a page's words
 * are the only ones the parity test compares with the server's copy.
 */
import type { ReactNode } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router";

import { useSession, useSignOut } from "../session/session";
import { adminSidebar } from "../slots/sidebar";
import { SlotOutlet, useSlot } from "../slots/slots";
import { useSite } from "../site/site";
import { useKernelSetup } from "./context";
import { RouteFocus } from "../ui/RouteFocus";
import { ScrollMemory } from "../ui/ScrollMemory";

/** Every page: focus moved to its heading, scroll kept per page and landed on its place (`ScrollMemory`). */
export function Root() {
  return (
    <>
      <RouteFocus />
      <ScrollMemory />
      <Outlet />
    </>
  );
}

function Skip() {
  return (
    <a className="mf-skip" href="#main">
      Skip to the content
    </a>
  );
}

function AccountLinks() {
  const session = useSession();
  const signOut = useSignOut();
  const navigate = useNavigate();
  if (session.status === "signed-out") return <Link to="/sign-in">Sign in</Link>;
  if (session.status !== "signed-in") return null;
  // Home first, then out: signed out on a member page, its guard sends the
  // person to sign in, which overtook a move home whose code was still coming.
  const leave = () => {
    Promise.resolve(navigate("/"))
      .then(signOut)
      .catch((error: unknown) => {
        console.error("Signing out failed.", error);
      });
  };
  return (
    <>
      <SlotOutlet name="nav.member" label="Your pages" />
      <Link to="/account">Your account</Link>
      {session.staff ? <Link to="/admin">Admin</Link> : null}
      <button type="button" onClick={leave}>
        Sign out
      </button>
    </>
  );
}

export function SiteFrame({ children }: { children?: ReactNode }) {
  const site = useSite();
  return (
    <div className="mf-site">
      <Skip />
      <header className="mf-site-header">
        {site ? (
          <Link to="/" className="mf-site-name">
            {site.name}
          </Link>
        ) : null}
        <nav aria-label="Site">
          <SlotOutlet name="nav.public" />
        </nav>
        <nav aria-label="Account">
          <AccountLinks />
        </nav>
      </header>
      <main id="main">{children ?? <Outlet />}</main>
      <footer className="mf-site-footer">
        <SlotOutlet name="site.footer" />
      </footer>
    </div>
  );
}

export function AdminFrame() {
  const { adminSections } = useKernelSetup();
  const entries = useSlot("nav.admin");
  const session = useSession();
  const can = session.status === "signed-in" ? session.can : () => false;
  const groups = adminSidebar(entries, adminSections, can);
  return (
    <div className="mf-admin mf-admin-look">
      <Skip />
      <nav aria-label="Admin" className="mf-admin-nav">
        {groups.map((group) => (
          <ul key={group.label ?? ""} aria-label={group.label}>
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.to === "/admin"}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        ))}
        <Link to="/">View site</Link>
      </nav>
      <main id="main">
        <Outlet />
      </main>
    </div>
  );
}
