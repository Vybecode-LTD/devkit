/**
 * `/account`, "Sign-in and security" (K4 contract §2; VM Website
 * design/site/Account.dc.html): passkeys, the authenticator app and its
 * recovery codes, the password, the email, the signed-in devices, then each
 * module's `account.section`. Every change but a sign-out asks for a recent
 * sign-in, which the step-up dialog gives.
 *
 * Staff sent here from the admin without a second factor
 * (`?needs=second-factor`) are told why first.
 *
 * The board's "Delete account" waits for K2 step 11, and "Last changed" under
 * the password for a record of when it was: neither is faked.
 */
import { Suspense, useCallback, useState, type SubmitEvent } from "react";
import { useSearchParams } from "react-router";

import { api, useApiQuery } from "../api/client";
import { lazyPart } from "../app/lazy";
import { PASSWORD_HINT } from "../auth/SignUp";
import { SESSION_KEY, useSession, type SessionUser } from "../session/session";
import { useSlot } from "../slots/slots";
import { Attention } from "../ui/Attention";
import { Button, LinkButton } from "../ui/Button";
import { Card } from "../ui/Card";
import { Dialog } from "../ui/Dialog";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { Field, Input } from "../ui/Field";
import { AccountPage, Row, Rows, useAction } from "./AccountPage";
import { Devices } from "./Devices";
import { Authenticator, Passkeys } from "./Factors";

const DEVICES = ["get", "/api/auth/sessions"] as const;

export default function Account() {
  const session = useSession();
  const [params] = useSearchParams();
  const devices = useApiQuery("get", "/api/auth/sessions");
  const here = devices.data?.items.find((item) => item.current)?.device_label ?? "";
  if (session.status !== "signed-in") return null;
  const needs = params.get("needs") === "second-factor" && !session.user.second_factor;
  return (
    <AccountPage
      page="Your account"
      title="Sign-in and security"
      lead="How you get into your account. Changing any of this asks you to sign in again if it's been more than 10 minutes."
    >
      {needs ? (
        <Attention
          tone="warning"
          what="Add a second factor to open the admin"
          why="Staff accounts need a passkey or an authenticator app as well as a password."
        />
      ) : null}
      <div className="mf-account-grid">
        <Passkeys suggested={here || "My passkey"} />
        <Authenticator />
        <Password />
        <Email user={session.user} />
        <Devices />
        <Sections />
      </div>
    </AccountPage>
  );
}

/** Each module's `account.section`, as a card of its own that can fail alone. */
function Sections() {
  const sections = useSlot("account.section");
  const [, setTries] = useState(0);
  const again = useCallback(() => {
    setTries((tries) => tries + 1);
  }, []);
  return (
    <>
      {sections.map((section) => {
        const Part = lazyPart(section.lazy);
        return (
          <Card key={section.key} title={section.title}>
            <ErrorBoundary where={`${section.module}'s ${section.title}`} onRetry={again}>
              <Suspense fallback={null}>
                <Part />
              </Suspense>
            </ErrorBoundary>
          </Card>
        );
      })}
    </>
  );
}

function Password() {
  const security = useApiQuery("get", "/api/auth/security");
  const { busy, run } = useAction();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [currentError, setCurrentError] = useState("");
  const [nextError, setNextError] = useState("");
  const [error, setError] = useState("");
  const has = security.data?.password ?? true;

  const close = () => {
    setOpen(false);
    setCurrent("");
    setNext("");
    setCurrentError("");
    setNextError("");
    setError("");
  };

  const save = (event: SubmitEvent) => {
    event.preventDefault();
    setCurrentError(current ? "" : "Enter your current password.");
    setNextError(next.length >= 12 ? "" : "Use at least 12 characters.");
    if (!current || next.length < 12) return;
    void (async () => {
      const result = await run(() => api.POST("/api/auth/password/change", { body: { current_password: current, new_password: next } }), {
        done: "Password changed. Every other device is signed out.",
        reads: [DEVICES],
        refused: { "auth.invalid_credentials": "That isn't your current password." },
      });
      if (result.ok) {
        close();
        return;
      }
      // On the field the refusal is about, else the form's own line.
      setError("");
      if (result.code === "auth.invalid_credentials") setCurrentError(result.error);
      else if (result.code === "auth.password_rejected") setNextError(result.error);
      else setError(result.error);
    })();
  };

  return (
    <Card title="Password" description="At least 12 characters. A few random words work well.">
      <Rows label="Your password">
        <Row
          name="Password"
          meta={has ? "Used with your email to sign in." : "None yet: a reset link sets one."}
          actions={
            has ? (
              <Button
                onClick={() => {
                  setOpen(true);
                }}
              >
                Change password
              </Button>
            ) : (
              <LinkButton to="/forgot-password">Set a password</LinkButton>
            )
          }
        />
      </Rows>
      {open ? (
        <Dialog title="Change your password" onClose={close}>
          <form className="mf-dialog-form" noValidate onSubmit={save}>
            <Field label="Current password" error={currentError}>
              <Input
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => {
                  setCurrent(event.target.value);
                }}
              />
            </Field>
            <Field label="New password" hint={PASSWORD_HINT} error={nextError}>
              <Input
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(event) => {
                  setNext(event.target.value);
                }}
              />
            </Field>
            <p className="mf-dialog-lead">Every other device signed in to your account will be signed out.</p>
            {error ? (
              <p className="mf-dialog-error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="mf-dialog-actions">
              <Button onClick={close}>Cancel</Button>
              <Button type="submit" variant="primary" disabled={busy}>
                Change password
              </Button>
            </div>
          </form>
        </Dialog>
      ) : null}
    </Card>
  );
}

function Email({ user }: { user: SessionUser }) {
  const { busy, run } = useAction();
  const [open, setOpen] = useState(false);
  const [address, setAddress] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [error, setError] = useState("");
  const close = () => {
    setOpen(false);
    setAddress("");
    setSentTo("");
    setError("");
  };

  const change = (event: SubmitEvent) => {
    event.preventDefault();
    const typed = address.trim();
    if (!/^[^\s@]+@[^\s@]+$/.test(typed) || typed.toLowerCase() === user.email.toLowerCase()) {
      setError("Enter one email address, other than the one you have.");
      return;
    }
    void run(() => api.POST("/api/auth/email/change", { body: { email: typed } }), {
      refused: { "kernel.invalid_request": "Enter one email address, other than the one you have." },
    }).then((result) => {
      if (result.ok) setSentTo(typed);
      else setError(result.error);
    });
  };

  return (
    <Card title="Email" description="Where sign-in codes, links and receipts go.">
      <Rows label="Your email">
        <Row
          name={user.email}
          meta={user.verified ? "Confirmed" : "Not confirmed yet: open the link we sent you."}
          actions={
            <>
              {user.verified ? null : (
                <Button
                  disabled={busy}
                  onClick={() => {
                    void run(
                      () => api.POST("/api/auth/verify-email/resend"),
                      {
                        done: "A new link is on its way. It works for a day.",
                        reads: [SESSION_KEY],
                        refused: { "auth.already_verified": "Your email is confirmed already." },
                      },
                      true,
                    );
                  }}
                >
                  Send a new link
                </Button>
              )}
              <Button
                onClick={() => {
                  setOpen(true);
                }}
              >
                Change email
              </Button>
            </>
          }
        />
      </Rows>
      {open ? (
        <Dialog title={sentTo ? "Check your new address" : "Change your email"} onClose={close}>
          {sentTo ? (
            <>
              <p className="mf-dialog-lead">
                We sent a link to {sentTo}. Open it within a day to make it your account&apos;s. Your current address works until then.
              </p>
              <div className="mf-dialog-actions">
                <Button variant="primary" onClick={close}>
                  Done
                </Button>
              </div>
            </>
          ) : (
            <form className="mf-dialog-form" noValidate onSubmit={change}>
              <p className="mf-dialog-lead">We&apos;ll send a link to the new address. Your current one works until you open it.</p>
              <Field label="New email">
                <Input
                  type="email"
                  autoComplete="email"
                  value={address}
                  onChange={(event) => {
                    setAddress(event.target.value);
                  }}
                />
              </Field>
              {error ? (
                <p className="mf-dialog-error" role="alert">
                  {error}
                </p>
              ) : null}
              <div className="mf-dialog-actions">
                <Button onClick={close}>Cancel</Button>
                <Button type="submit" variant="primary" disabled={busy}>
                  Send link
                </Button>
              </div>
            </form>
          )}
        </Dialog>
      ) : null}
    </Card>
  );
}
