/**
 * The account's signed-in devices (SPEC 14.5; VM Website
 * design/site/Account.dc.html, "Signed-in devices"): this one first, marked
 * Now, then each other with its place when the site knows it and when it was
 * last seen, a sign-out for each, and "Sign out everywhere else". None asks
 * for a recent sign-in: ending a session only ever takes access away.
 */
import { api, useApiQuery } from "../api/client";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Pill } from "../ui/Pill";
import { Day, Row, Rows, useAction } from "./AccountPage";

const DEVICES = ["get", "/api/auth/sessions"] as const;

export function Devices() {
  const list = useApiQuery("get", "/api/auth/sessions");
  const { busy, run } = useAction();
  const items = list.data?.items ?? [];
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
    </Card>
  );
}
