/**
 * `/account/activity` (K4 contract §2; SPEC 14.10): the person's own
 * security activity, newest first (`GET /api/auth/activity`), fifty at a
 * time: what happened, whether it went through, whether they did it, when
 * and from which address. So someone who didn't do a thing can see it.
 */
import { useInfiniteQuery } from "@tanstack/react-query";

import { ApiProblem, api } from "../api/client";
import type { components } from "../api/schema";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { LoadError } from "../ui/LoadError";
import { AccountPage } from "./AccountPage";

type Entry = components["schemas"]["OwnActivityEntry"];

/** What each of auth's entries says, as the person reads it. */
export const DONE: Readonly<Record<string, string>> = {
  "auth.sign_up": "Created the account",
  "auth.email_verified": "Confirmed the email",
  "auth.verification_resent": "Asked for a new confirmation link",
  "auth.sign_in": "Signed in",
  "auth.code_sent": "Asked for a sign-in code",
  "auth.second_factor": "Used a second factor",
  "auth.step_up": "Confirmed it was them",
  "auth.sign_out": "Signed out",
  "auth.session_ended": "Signed a device out",
  "auth.password_reset_requested": "Asked to reset the password",
  "auth.password_reset": "Reset the password",
  "auth.password_changed": "Changed the password",
  "auth.email_change_requested": "Asked to change the email",
  "auth.email_changed": "Changed the email",
  "auth.email_restored": "Put the old email back",
  "auth.totp_setup_started": "Began setting up an authenticator app",
  "auth.totp_confirmed": "Turned on an authenticator app",
  "auth.totp_removed": "Removed the authenticator app",
  "auth.recovery_codes_replaced": "Made new recovery codes",
  "auth.passkey_registration_started": "Began adding a passkey",
  "auth.passkey_added": "Added a passkey",
  "auth.passkey_renamed": "Renamed a passkey",
  "auth.passkey_removed": "Removed a passkey",
  "auth.second_factor_undone": "Removed a second factor from its email",
  "auth.user.suspended": "The account was suspended",
  "auth.user.restored": "The account was restored",
};

function When({ at }: { at: string }) {
  const moment = new Date(at);
  const shown = Number.isNaN(moment.getTime())
    ? at
    : moment.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
  return <time dateTime={at}>{shown}</time>;
}

function Line({ entry }: { entry: Entry }) {
  const what = DONE[entry.action] ?? entry.action;
  const failed = entry.result !== "success";
  return (
    <li className="mf-row">
      <span className="mf-row-words">
        <span className="mf-row-name">
          {what}
          {failed ? " (didn't go through)" : ""}
        </span>
        <span className="mf-row-meta">
          <When at={entry.at} />
          {entry.by_you ? "" : ", by someone else"}
          {entry.ip ? `, from ${entry.ip}` : ""}
        </span>
      </span>
    </li>
  );
}

export default function Activity() {
  const pages = useInfiniteQuery({
    queryKey: ["get", "/api/auth/activity", "pages"],
    initialPageParam: "",
    queryFn: async ({ pageParam }) => {
      const { data } = await api.GET("/api/auth/activity", { params: { query: pageParam ? { cursor: pageParam } : {} } });
      if (!data) throw ApiProblem.unreachable();
      return data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const entries = pages.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <AccountPage page="Your activity" title="Activity" lead="What's happened with your sign-in and security, newest first. If you didn't do something here, change your password.">
      <Card title="Recent activity" className="mf-activity">
        {pages.error ? (
          <LoadError what="Your activity" error={pages.error} onRetry={() => void pages.refetch()} />
        ) : pages.isPending ? null : entries.length === 0 ? (
          <EmptyState title="Nothing yet" />
        ) : (
          <>
            <ul className="mf-rows" aria-label="Your activity">
              {entries.map((entry) => (
                <Line key={entry.id} entry={entry} />
              ))}
            </ul>
            {pages.hasNextPage ? (
              <Button disabled={pages.isFetchingNextPage} onClick={() => void pages.fetchNextPage()}>
                Show older
              </Button>
            ) : null}
          </>
        )}
      </Card>
    </AccountPage>
  );
}
