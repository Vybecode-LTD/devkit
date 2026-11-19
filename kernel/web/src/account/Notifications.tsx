/**
 * `/account/notifications` (K4 contract §2; decision 0038): each notice the
 * modules on can send, on the site and by email, switched for this person
 * alone. A switch saves at once; the page shows the server's answer.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useId } from "react";

import { api, useApiQuery } from "../api/client";
import type { components } from "../api/schema";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { LoadError } from "../ui/LoadError";
import { Switch } from "../ui/Field";
import { AccountPage, useAction } from "./AccountPage";

type Preference = components["schemas"]["NoticePreference"];
const PREFERENCES = ["get", "/api/kernel/notifications/preferences"] as const;

function Choice({ item, busy, onChange }: { item: Preference; busy: boolean; onChange: (choice: { in_site: boolean; email: boolean }) => void }) {
  const id = useId();
  return (
    <li>
      <div className="mf-row" role="group" aria-labelledby={id}>
      <span className="mf-row-words">
        <span id={id} className="mf-row-name">
          {item.description}
        </span>
      </span>
      <span className="mf-row-actions">
        <Switch
          label="On the site"
          checked={item.in_site}
          disabled={busy}
          onChange={(in_site) => {
            onChange({ in_site, email: item.email });
          }}
        />
        <Switch
          label="By email"
          checked={item.email}
          disabled={busy}
          onChange={(email) => {
            onChange({ in_site: item.in_site, email });
          }}
        />
      </span>
      </div>
    </li>
  );
}

export default function Notifications() {
  const found = useApiQuery("get", "/api/kernel/notifications/preferences");
  const queryClient = useQueryClient();
  const { busy, run } = useAction();
  const items = found.data?.items ?? [];

  const choose = (key: string, choice: { in_site: boolean; email: boolean }) => {
    void run(
      async () => {
        const { data } = await api.PUT("/api/kernel/notifications/preferences", { body: { [key]: choice } });
        if (!data) return;
        // A read on its way from before the save would land over it (CodeRabbit on #83).
        await queryClient.cancelQueries({ queryKey: PREFERENCES });
        queryClient.setQueryData(PREFERENCES, data);
      },
      { done: "Saved." },
      true,
    );
  };

  return (
    <AccountPage page="Notifications" title="Notifications" lead="What this site tells you about, on the site and by email.">
      <Card title="What you hear about" description="Each one is yours to switch: nobody else's changes.">
        {found.error ? (
          <LoadError what="Your notification settings" error={found.error} onRetry={() => void found.refetch()} />
        ) : found.isPending ? null : items.length === 0 ? (
          <EmptyState title="Nothing to switch yet">None of this site&apos;s parts sends notices.</EmptyState>
        ) : (
          <ul className="mf-rows" aria-label="Notices">
            {items.map((item) => (
              <Choice
                key={item.key}
                item={item}
                busy={busy}
                onChange={(choice) => {
                  choose(item.key, choice);
                }}
              />
            ))}
          </ul>
        )}
      </Card>
    </AccountPage>
  );
}
