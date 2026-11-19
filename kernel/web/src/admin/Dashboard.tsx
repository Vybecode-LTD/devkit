/**
 * `/admin`, the Dashboard (K4 contract §2 and §4 item 6; SPEC 8, the owner's
 * lens; VM Website `AdminDashboard.dc.html`): a greeting and the day, then
 * "Needs you", what's wrong with why it matters and what fixes it, each item
 * only for those who can act on it (`GET /api/kernel/admin/attention`), then
 * the modules' cards (`admin.dashboard.widget`), each a `StatCard` most often.
 * The board's launch checklist is the site's own, a module's to draw.
 */
import { useId } from "react";

import { useApiQuery } from "../api/client";
import { SlotOutlet, useSlot } from "../slots/slots";
import { Attention } from "../ui/Attention";
import { LoadError } from "../ui/LoadError";
import { AdminPage } from "./AdminPage";

/** "Good morning" to noon, "Good afternoon" to six, else "Good evening", by the reader's clock. */
export function greeting(now: Date): string {
  const hour = now.getHours();
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour >= 12 && hour < 18) return "Good afternoon";
  return "Good evening";
}

function NeedsYou() {
  const id = useId();
  const needs = useApiQuery("get", "/api/kernel/admin/attention");
  const items = needs.data?.items ?? [];
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className="mf-needs-title">
        Needs you
        {needs.data ? (
          <>
            {" "}
            <span className="mf-needs-count">{items.length}</span>
          </>
        ) : null}
      </h2>
      {needs.error ? (
        <LoadError what="What needs you" error={needs.error} onRetry={() => void needs.refetch()} />
      ) : needs.isPending ? (
        <p className="mf-needs-clear" role="status">
          Checking what needs you…
        </p>
      ) : items.length === 0 ? (
        <p className="mf-needs-clear">Nothing needs you right now.</p>
      ) : (
        <ul className="mf-needs-list">
          {items.map((item) => (
            <li key={item.key}>
              <Attention tone={item.tone} what={item.what} why={item.why} action={item.action} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Cards() {
  const cards = useSlot("admin.dashboard.widget");
  if (cards.length === 0) return null;
  return (
    <div className="mf-dashboard-cards">
      <SlotOutlet name="admin.dashboard.widget" />
    </div>
  );
}

export default function Dashboard() {
  const now = new Date();
  const day = now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  return (
    <AdminPage page="Dashboard" title={greeting(now)} lead={`${day}. Here's what needs you and how the site is doing.`}>
      <NeedsYou />
      <Cards />
    </AdminPage>
  );
}
