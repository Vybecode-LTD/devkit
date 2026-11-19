/**
 * The account's second factors (VM Website design/site/Account.dc.html):
 * its passkeys, added, renamed and removed; and its authenticator app, set
 * up, removed, with its recovery codes made again. Each change asks for a
 * recent sign-in (the step-up dialog), and removing a passkey or the app
 * signs every other device out (SPEC 14.5).
 */
import { useEffect, useRef, useState, type SubmitEvent } from "react";

import { api, useApiQuery } from "../api/client";
import type { components } from "../api/schema";
import { PasskeyCancelled, makePasskey, passkeysWork } from "../auth/passkey";
import { SESSION_KEY } from "../session/session";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Dialog } from "../ui/Dialog";
import { Field, Input } from "../ui/Field";
import { LoadError } from "../ui/LoadError";
import { Pill } from "../ui/Pill";
import { QrCode } from "../ui/QrCode";
import { Day, Row, Rows, useAction } from "./AccountPage";

type Passkey = components["schemas"]["PasskeyView"];

const PASSKEYS = ["get", "/api/auth/passkeys"] as const;
const SECURITY = ["get", "/api/auth/security"] as const;
const DEVICES = ["get", "/api/auth/sessions"] as const;
/** What a second factor's change can move: the factors, whether the account has one, and its other devices. */
const AFTER_FACTOR = [PASSKEYS, SECURITY, SESSION_KEY, DEVICES];

const UNVERIFIED = "Confirm your email first: open the link we sent you.";

function NameDialog({
  title,
  lead,
  given,
  action,
  busy,
  error,
  onSave,
  onClose,
}: {
  title: string;
  lead?: string;
  given: string;
  action: string;
  busy: boolean;
  error: string;
  onSave: (name: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(given);
  const [wrong, setWrong] = useState("");
  const save = (event: SubmitEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 1 || trimmed.length > 80) {
      setWrong("Give it a name of 1 to 80 characters.");
      return;
    }
    setWrong("");
    onSave(trimmed);
  };
  return (
    <Dialog title={title} onClose={onClose}>
      <form className="mf-dialog-form" noValidate onSubmit={save}>
        {lead ? <p className="mf-dialog-lead">{lead}</p> : null}
        <Field label="Name" hint="So you can tell your passkeys apart: the device or the app it's in." error={wrong}>
          <Input
            value={name}
            maxLength={80}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </Field>
        {error ? (
          <p className="mf-dialog-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mf-dialog-actions">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {action}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function Confirm({
  title,
  lead,
  action,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  title: string;
  lead: string;
  action: string;
  busy: boolean;
  error: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog title={title} onClose={onClose}>
      <p className="mf-dialog-lead">{lead}</p>
      {error ? (
        <p className="mf-dialog-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mf-dialog-actions">
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={busy} onClick={onConfirm}>
          {action}
        </Button>
      </div>
    </Dialog>
  );
}

type Open = { at: "add" } | { at: "rename"; passkey: Passkey } | { at: "remove"; passkey: Passkey } | null;

export function Passkeys({ suggested }: { suggested: string }) {
  const list = useApiQuery("get", "/api/auth/passkeys");
  const { busy, run } = useAction();
  const [open, setOpen] = useState<Open>(null);
  const [error, setError] = useState("");
  const close = () => {
    setOpen(null);
    setError("");
  };
  const done = (result: { ok: boolean; error: string }) => {
    if (result.ok) close();
    else setError(result.error);
  };

  const add = (name: string) =>
    void run(
      async () => {
        const { data: options } = await api.POST("/api/auth/passkeys/register/start", { body: { name } });
        if (!options) throw new PasskeyCancelled();
        const credential = await makePasskey(options);
        await api.POST("/api/auth/passkeys/register/finish", { body: credential });
      },
      {
        done: "Passkey added. We've emailed you about it, with a way to undo it.",
        reads: AFTER_FACTOR,
        refused: {
          "auth.email_unverified": UNVERIFIED,
          "auth.too_many_passkeys": "Your account has 20 passkeys, the most it can have. Remove one first.",
          "auth.invalid_passkey": "That passkey couldn't be added. It may be on this account already.",
        },
      },
    ).then(done);

  const items = list.data?.items ?? [];
  return (
    <Card
      title="Passkeys"
      description="The safest way in: your device checks it's you with your face, fingerprint or PIN."
      actions={
        passkeysWork() ? (
          <Button
            variant="primary"
            onClick={() => {
              setOpen({ at: "add" });
            }}
          >
            Add a passkey
          </Button>
        ) : null
      }
    >
      {list.error ? <LoadError what="Your passkeys" error={list.error} onRetry={() => void list.refetch()} inline /> : null}
      <Rows label="Your passkeys">
        {list.isPending || list.error ? null : items.length === 0 ? (
          <Row name="No passkeys yet" meta={passkeysWork() ? "Add one to sign in without your password." : "This browser can't make one."} />
        ) : (
          items.map((passkey) => (
            <Row
              key={passkey.id}
              name={passkey.name}
              meta={
                <>
                  Added <Day at={passkey.created_at} />,{" "}
                  {passkey.last_used_at ? (
                    <>
                      last used <Day at={passkey.last_used_at} />
                    </>
                  ) : (
                    "never used"
                  )}
                </>
              }
              actions={
                <>
                  <Button
                    aria-label={`Rename ${passkey.name}`}
                    onClick={() => {
                      setOpen({ at: "rename", passkey });
                    }}
                  >
                    Rename
                  </Button>
                  <Button
                    aria-label={`Remove ${passkey.name}`}
                    onClick={() => {
                      setOpen({ at: "remove", passkey });
                    }}
                  >
                    Remove
                  </Button>
                </>
              }
            />
          ))
        )}
      </Rows>
      {open?.at === "add" ? (
        <NameDialog
          title="Add a passkey"
          lead="Your browser will ask you to make it, with your face, fingerprint or PIN."
          given={suggested}
          action="Add passkey"
          busy={busy}
          error={error}
          onSave={add}
          onClose={close}
        />
      ) : open?.at === "rename" ? (
        <NameDialog
          title="Rename the passkey"
          given={open.passkey.name}
          action="Save"
          busy={busy}
          error={error}
          onSave={(name) => {
            void run(() => api.PATCH("/api/auth/passkeys/{id}", { params: { path: { id: open.passkey.id } }, body: { name } }), {
              done: "Passkey renamed.",
              reads: [PASSKEYS],
            }).then(done);
          }}
          onClose={close}
        />
      ) : open?.at === "remove" ? (
        <Confirm
          title={`Remove ${open.passkey.name}?`}
          lead="You won't be able to sign in with it any more. Every other device signed in to your account will be signed out."
          action="Remove passkey"
          busy={busy}
          error={error}
          onConfirm={() => {
            void run(() => api.DELETE("/api/auth/passkeys/{id}", { params: { path: { id: open.passkey.id } } }), {
              done: "Passkey removed. Every other device is signed out.",
              reads: AFTER_FACTOR,
            }).then(done);
          }}
          onClose={close}
        />
      ) : null}
    </Card>
  );
}

function grouped(secret: string): string {
  return (secret.match(/.{1,4}/g) ?? [secret]).join(" ");
}

function Codes({ codes }: { codes: readonly string[] }) {
  return (
    <ul className="mf-codes" aria-label="Your recovery codes">
      {codes.map((code) => (
        <li key={code}>{code}</li>
      ))}
    </ul>
  );
}

/** Setting the app up: its key, the code it then shows, and the recovery codes once it's confirmed. */
function SetUp({ onClose }: { onClose: () => void }) {
  const { busy, run } = useAction();
  const [setup, setSetup] = useState<components["schemas"]["TotpSetup"] | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  // Once, even where StrictMode runs effects twice: a second setup would replace the first key.
  const asked = useRef(false);
  const start = useRef({ run, onClose });
  useEffect(() => {
    start.current = { run, onClose };
  });

  useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void start.current
      .run(
        async () => {
          const { data } = await api.POST("/api/auth/totp/setup");
          if (data) setSetup(data);
        },
        { refused: { "auth.email_unverified": UNVERIFIED, "auth.totp_exists": "Your account has an authenticator app already." } },
      )
      .then((result) => {
        if (!result.ok && !result.error) start.current.onClose(); // the step-up was closed
        else setError(result.error);
      });
  }, []);

  const confirm = (event: SubmitEvent) => {
    event.preventDefault();
    const typed = code.replace(/\s/g, "");
    if (!/^\d{6}$/.test(typed)) {
      setError("Enter the 6 digits your app shows.");
      return;
    }
    void run(
      async () => {
        const { data } = await api.POST("/api/auth/totp/confirm", { body: { code: typed } });
        if (data) setCodes(data.recovery_codes);
      },
      {
        reads: AFTER_FACTOR,
        refused: {
          "auth.invalid_second_factor": "That code didn't match. Check the time on your phone, then try the newest code.",
          "auth.no_pending_totp": "That setup ran out. Close this and start again.",
          "auth.email_unverified": UNVERIFIED,
        },
      },
    ).then((result) => {
      setError(result.error);
    });
  };

  return (
    <Dialog title={codes ? "Save your recovery codes" : "Set up an authenticator app"} onClose={onClose} wide>
      {codes ? (
        <>
          <p className="mf-dialog-lead">Each one works once, if you lose your phone. Keep them somewhere safe: they won&apos;t be shown again.</p>
          <Codes codes={codes} />
          <div className="mf-dialog-actions">
            <Button variant="primary" onClick={onClose}>
              I&apos;ve saved them
            </Button>
          </div>
        </>
      ) : (
        <form className="mf-dialog-form" noValidate onSubmit={confirm}>
          <p className="mf-dialog-lead">Scan the code with your authenticator app, or add an account in it with the key below.</p>
          {setup ? (
            <>
              <QrCode value={setup.otpauth_uri} label="A QR code for your authenticator app" />
              <p className="mf-secret" aria-label="Your key">
                {grouped(setup.secret)}
              </p>
              <a className="mf-text-link" href={setup.otpauth_uri}>
                Open in your authenticator app
              </a>
              <Field label="Code from your app" hint="The 6 digits it shows for this account.">
                <Input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value);
                  }}
                />
              </Field>
            </>
          ) : null}
          {error ? (
            <p className="mf-dialog-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="mf-dialog-actions">
            <Button onClick={onClose}>Cancel</Button>
            {setup ? (
              <Button type="submit" variant="primary" disabled={busy}>
                Turn it on
              </Button>
            ) : null}
          </div>
        </form>
      )}
    </Dialog>
  );
}

type AppOpen = "setup" | "remove" | "codes" | null;

export function Authenticator() {
  const security = useApiQuery("get", "/api/auth/security");
  const { busy, run } = useAction();
  const [open, setOpen] = useState<AppOpen>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const close = () => {
    setOpen(null);
    setCodes(null);
    setError("");
  };
  const totp = security.data?.totp ?? null;
  const left = security.data?.recovery_codes_left ?? 0;

  return (
    <Card title="Authenticator app" description="A 6-digit code from an app on your phone, asked for after your password.">
      {security.error ? (
        <LoadError what="Your authenticator app" error={security.error} onRetry={() => void security.refetch()} inline />
      ) : null}
      <Rows label="Your authenticator app">
        {security.isPending || security.error ? null : totp ? (
          <>
            <Row
              name={<Pill tone="success">On</Pill>}
              meta={
                <>
                  Set up <Day at={totp.since} />
                </>
              }
              actions={
                <Button
                  aria-label="Remove the authenticator app"
                  onClick={() => {
                    setOpen("remove");
                  }}
                >
                  Remove
                </Button>
              }
            />
            <Row
              name="Recovery codes"
              meta={`${String(left)} of 10 left. Each one works once, if you lose your phone.`}
              actions={
                <Button
                  onClick={() => {
                    setOpen("codes");
                  }}
                >
                  Make new codes
                </Button>
              }
            />
          </>
        ) : (
          <Row
            name={<Pill>Off</Pill>}
            meta="Not set up"
            actions={
              <Button
                onClick={() => {
                  setOpen("setup");
                }}
              >
                Set up
              </Button>
            }
          />
        )}
      </Rows>
      {open === "setup" ? <SetUp onClose={close} /> : null}
      {open === "remove" ? (
        <Confirm
          title="Remove your authenticator app?"
          lead="Its recovery codes stop working too, and every other device signed in to your account will be signed out."
          action="Remove app"
          busy={busy}
          error={error}
          onConfirm={() => {
            void run(() => api.DELETE("/api/auth/totp"), {
              done: "Authenticator app removed. Every other device is signed out.",
              reads: AFTER_FACTOR,
            }).then((result) => {
              if (result.ok) close();
              else setError(result.error);
            });
          }}
          onClose={close}
        />
      ) : null}
      {open === "codes" ? (
        codes ? (
          <Dialog title="Save your new recovery codes" onClose={close} wide>
            <p className="mf-dialog-lead">Your old codes don&apos;t work any more. Each new one works once; they won&apos;t be shown again.</p>
            <Codes codes={codes} />
            <div className="mf-dialog-actions">
              <Button variant="primary" onClick={close}>
                I&apos;ve saved them
              </Button>
            </div>
          </Dialog>
        ) : (
          <Confirm
            title="Make new recovery codes?"
            lead="Your old codes stop working, used or not."
            action="Make new codes"
            busy={busy}
            error={error}
            onConfirm={() => {
              void run(
                async () => {
                  const { data } = await api.POST("/api/auth/recovery-codes");
                  if (data) setCodes(data.recovery_codes);
                },
                { reads: [SECURITY], refused: { "auth.no_second_factor": "Set up the authenticator app first." } },
              ).then((result) => {
                setError(result.error);
              });
            }}
            onClose={close}
          />
        )
      ) : null}
    </Card>
  );
}
