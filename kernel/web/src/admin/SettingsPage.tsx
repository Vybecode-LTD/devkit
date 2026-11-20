/**
 * What the three Settings pages share (VM Website `AdminSettings.dc.html`):
 * the page header, then Site, Features and System as tabs. Each tab is a page
 * of its own (`/admin/settings`, `/features`, `/system`), so the tabs are
 * links, the current one marked as the page; a tab shows only for those who
 * may open its page.
 */
import "./settings.css";

import type { ReactNode } from "react";
import { NavLink } from "react-router";

import { useSession } from "../session/session";
import { AdminPage } from "./AdminPage";

export const SETTINGS_TABS = [
  { to: "/admin/settings", label: "Site", permission: "kernel.settings.manage" },
  { to: "/admin/settings/features", label: "Features", permission: "kernel.module.manage" },
  { to: "/admin/settings/system", label: "System", permission: "kernel.settings.manage" },
] as const;

export type SettingsPageProps = {
  /** The head's title: "Settings", "Features", "System". */
  page: string;
  actions?: ReactNode;
  children: ReactNode;
};

export function SettingsPage({ page, actions, children }: SettingsPageProps) {
  const session = useSession();
  const tabs = SETTINGS_TABS.filter((tab) => session.status === "signed-in" && session.can(tab.permission));
  return (
    <AdminPage page={page} title="Settings" lead="How the site runs. Changes are written to the activity log." actions={actions}>
      <nav aria-label="Settings" className="mf-settings-tabs">
        <ul className="mf-tab-row">
          {tabs.map((tab) => (
            <li key={tab.to}>
              <NavLink to={tab.to} end className="mf-tab mf-tab-link">
                {tab.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="mf-settings">{children}</div>
    </AdminPage>
  );
}
