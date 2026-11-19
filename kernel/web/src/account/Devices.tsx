/**
 * The account's signed-in devices (SPEC 14.5; VM Website
 * design/site/Account.dc.html, "Signed-in devices"): this one first, marked
 * Now, then each other with its place when the site knows it and when it was
 * last seen, a sign-out for each, and "Sign out everywhere else". None asks
 * for a recent sign-in: ending a session only ever takes access away.
 */
import { useInfiniteQuery } from "@tanstack/react-query";

import { ApiProblem, api } from "../api/client";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { LoadError } from "../ui/LoadError";
import { Pill } from "../ui/Pill";
import { Day, Row, Rows, useAction } from "./AccountPage";

const DEVICES = ["get", "/api/auth/sessions"] as const;

export function Devices() {
  // In pages, as every list (SPEC 7): the first one holds the latest seen.
  const list = useInfiniteQuery({
    queryKey: ["get", "/api/auth/sessions", "pages"],
    initialPageParam: "",
    queryFn: async ({ pageParam }) => {
      const { data } = await api.GET("/api/auth/sessions", { params: { query: pageParam ? { cursor: pageParam } : {} } });
      if (!data) throw ApiProblem.unreachable();
      return data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const { busy, run } = useAction();
  const items = list.data?.pages.flatMap((page) => page.items) ?? [];
  const mine = items.find((item) => item.current);
  const others = items.filter((item) => !item.current);

  return (
    <Card
      title="Signed-in devices"
      description="Anywhere your account is open right now."
      actions={
        others.length > 0 ? (
          <Button
            disabled={busy}
            onClick={() => {
              void run(() => api.POST("/api/auth/sessions/sign-out-others"), { done: "Every other device is signed out.", reads: [DEVICES] }, true);
            }}
          >
            Sign out everywhere else
          </Button>
        ) : null
      }
    >
      {list.error ? <LoadError what="Your signed-in devices" error={list.error} onRetry={() => void list.refetch()} inline /> : null}
      <Rows label="Your signed-in devices">
        {mine ? (
          <Row
            name="This device"
            meta={mine.location ? `${mine.device_label}, ${mine.location}` : mine.device_label}
            actions={<Pill>Now</Pill>}
          />
        ) : null}
        {others.map((device) => (
          <Row
            key={device.id}
            name={device.device_label}
            meta={
              <>
                {device.location ? `${device.location}, last active ` : "Last active "}
                <Day at={device.last_seen_at} />
              </>
            }
            actions={
              <Button
                aria-label={`Sign out ${device.device_label}`}
                disabled={busy}
                onClick={() => {
                  void run(
                    () => api.DELETE("/api/auth/sessions/{id}", { params: { path: { id: device.id } } }),
                    { done: `${device.device_label} is signed out.`, reads: [DEVICES], refused: { "auth.session_not_found": "That device was signed out already." } },
                    true,
                  );
                }}
              >
                Sign out
              </Button>
            }
          />
        ))}
      </Rows>
      {list.hasNextPage ? (
        <Button disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
          Show more devices
        </Button>
      ) : null}
    </Card>
  );
}
