/**
 * The admin's frame (K4 contract §4 item 6; decision 0040; VM Website
 * `AdminDashboard.dc.html` and shell-slots.md): the sidebar, the top bar and
 * the page beside them, in the admin's look.
 *
 * - **The sidebar:** the site's mark and name with an Admin badge; its
 *   sections in the contract's order (`adminSidebar`), each with its icon, a
 *   section's pages shown under it while one of them is open (VM Website
 *   `AdminBlog.dc.html`); the signed-in person at the bottom.
 * - **The top bar:** where the page sits (Admin / section / page), Search or
 *   jump to (Ctrl K or ⌘ K opens it anywhere in the admin), the notices, View
 *   site.
 * - **Under 960px** the sidebar folds away behind Menu, which opens it in
 *   place under the bar, so the pages follow Menu in the tab order; it shuts
 *   on every move, back to where it was opened too.
 */
import "./admin.css";

import { useEffect, useId, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";

import { useKernelSetup } from "../app/context";
import { Skip } from "../app/frames";
import { useSession } from "../session/session";
import { useSite } from "../site/site";
import { adminSidebar, type SidebarGroup, type SidebarItem } from "../slots/sidebar";
import { useSlot } from "../slots/slots";
import { LinkButton } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { CrumbContext } from "./AdminPage";
import { JumpTo } from "./JumpTo";
import { Notices } from "./Notices";
import { roleWords, useRoles } from "./roleAccess";

/** Whether `pathname` is `to` or a page under it. */
function within(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(`${to}/`);
}

/**
 * The sidebar's page `pathname` is on, and its section: the one whose address
 * it's at or under, the longest when several are (Features under Site).
 */
export function whereIs(groups: readonly SidebarGroup[], pathname: string): { group?: SidebarGroup; item?: SidebarItem } {
  let found: { group?: SidebarGroup; item?: SidebarItem } = {};
  for (const group of groups) {
    for (const item of group.items) {
      const deeper = item.to === "/admin" ? pathname === "/admin" : within(pathname, item.to);
      if (deeper && (found.item === undefined || item.to.length > found.item.to.length)) found = { group, item };
    }
  }
  return found;
}

/** A link's `end`: only its own address, when another page sits under it (Site, then Features). */
function exact(item: SidebarItem, all: readonly SidebarItem[]): boolean {
  return item.to === "/admin" || all.some((other) => other !== item && other.to.startsWith(`${item.to}/`));
}

function Glyph({ name }: { name?: SidebarItem["icon"] }) {
  return name ? <Icon name={name} /> : <span className="mf-admin-nav-blank" aria-hidden="true" />;
}

function Sidebar({ groups, current }: { groups: readonly SidebarGroup[]; current: SidebarGroup | undefined }) {
  const all = groups.flatMap((group) => group.items);
  return (
    <nav aria-label="Admin" className="mf-admin-nav">
      <ul className="mf-admin-nav-list">
        {groups.flatMap((group) => {
          if (group.label === undefined) {
            return group.items.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={exact(item, all)}>
                  <Glyph name={item.icon} />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ));
          }
          const [first] = group.items;
          if (!first) return [];
          const open = group === current;
          return [
            <li key={group.label}>
              <Link to={first.to} className="mf-admin-nav-section">
                <Glyph name={group.icon} />
                <span>{group.label}</span>
              </Link>
              {open ? (
                <ul className="mf-admin-nav-pages" aria-label={group.label}>
                  {group.items.map((item) => (
                    <li key={item.to}>
                      <NavLink to={item.to} end={exact(item, all)}>
                        {item.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>,
          ];
        })}
      </ul>
    </nav>
  );
}

function Brand() {
  const site = useSite();
  return (
    <div className="mf-admin-brand">
      {site?.logo ? <img className="mf-admin-brand-mark" src={site.logo} alt="" width={26} height={26} /> : null}
      {site ? <span className="mf-admin-brand-name">{site.name}</span> : null}
      <span className="mf-admin-badge">Admin</span>
    </div>
  );
}

/** "ann.example@…" → "AE"; "bo@…" → "B". */
export function initials(email: string): string {
  const name = email.split("@")[0] ?? "";
  const parts = name.split(/[._+-]+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** The signed-in person's card: their roles by name once the roles read is in (K4.7), by id before it or without it. */
function Person() {
  const session = useSession();
  const named = useRoles();
  if (session.status !== "signed-in") return null;
  const { email, roles } = session.user;
  return (
    <div className="mf-admin-person">
      <span className="mf-admin-avatar" aria-hidden="true">
        {initials(email)}
      </span>
      <span className="mf-admin-person-words">
        <span className="mf-admin-person-name">{email}</span>
        <span className="mf-admin-person-role">{roleWords(roles, named.data?.roles)}</span>
      </span>
      <Link to="/" className="mf-admin-person-site" aria-label="View site" title="View site">
        <Icon name="external" />
      </Link>
    </div>
  );
}

function Crumbs({ group, item, crumb }: { group: SidebarGroup | undefined; item: SidebarItem | undefined; crumb: string | undefined }) {
  const last = crumb ?? item?.label;
  const first = group?.label === undefined ? undefined : group.items[0];
  return (
    <nav aria-label="Breadcrumb" className="mf-admin-crumbs">
      <ol>
        <li>{last === undefined ? <span aria-current="page">Admin</span> : <Link to="/admin">Admin</Link>}</li>
        {group?.label !== undefined && first ? (
          <li>
            <Link to={first.to}>{group.label}</Link>
          </li>
        ) : null}
        {last === undefined ? null : (
          <li>
            <span aria-current="page">{last}</span>
          </li>
        )}
      </ol>
    </nav>
  );
}

export function AdminFrame() {
  const { adminSections } = useKernelSetup();
  const entries = useSlot("nav.admin");
  const session = useSession();
  const can = session.status === "signed-in" ? session.can : () => false;
  const groups = adminSidebar(entries, adminSections, can);
  const location = useLocation();
  const { pathname } = location;
  const { group, item } = whereIs(groups, pathname);
  const railId = useId();
  const [crumb, setCrumb] = useState<string>();
  // Shut on every move, a move back to where it was opened included (CodeRabbit
  // on #84): each move is a location of its own, so its key is new, or an
  // older one's on Back. Reset as the move is drawn, not in an effect after.
  const [menuOpen, setMenuOpen] = useState(false);
  const [drawnAt, setDrawnAt] = useState(location.key);
  if (drawnAt !== location.key) {
    setDrawnAt(location.key);
    setMenuOpen(false);
  }
  const [jumping, setJumping] = useState(false);

  useEffect(() => {
    const jump = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setJumping(true);
      }
    };
    document.addEventListener("keydown", jump);
    return () => {
      document.removeEventListener("keydown", jump);
    };
  }, []);

  return (
    <CrumbContext.Provider value={setCrumb}>
      <div className={menuOpen ? "mf-admin mf-admin-look mf-admin--menu" : "mf-admin mf-admin-look"}>
        <Skip />
        <div className="mf-admin-phone-bar">
          <Brand />
          <button
            type="button"
            className="mf-admin-menu"
            aria-expanded={menuOpen}
            aria-controls={railId}
            onClick={() => {
              setMenuOpen(!menuOpen);
            }}
          >
            {menuOpen ? <Icon name="close" /> : null}
            Menu
          </button>
        </div>
        <aside id={railId} className="mf-admin-rail" aria-label="Admin sections">
          <Brand />
          <Sidebar groups={groups} current={group} />
          <Person />
        </aside>
        <div className="mf-admin-column">
          <header className="mf-admin-top">
            <Crumbs group={group} item={item} crumb={crumb} />
            <button
              type="button"
              className="mf-admin-jump"
              aria-keyshortcuts="Control+K Meta+K"
              onClick={() => {
                setJumping(true);
              }}
            >
              <Icon name="search" />
              <span className="mf-admin-jump-words">Search or jump to</span>
              <kbd className="mf-admin-key">Ctrl K</kbd>
            </button>
            <Notices />
            <LinkButton to="/" size="small" className="mf-admin-view-site">
              View site
              <Icon name="external" />
            </LinkButton>
          </header>
          <main id="main" className="mf-admin-main">
            <Outlet />
          </main>
        </div>
        {jumping ? (
          <JumpTo
            groups={groups}
            onClose={() => {
              setJumping(false);
            }}
          />
        ) : null}
      </div>
    </CrumbContext.Provider>
  );
}
