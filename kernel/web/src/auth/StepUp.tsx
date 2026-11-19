/**
 * The step-up dialog (K4 contract §2; SPEC 14.4): a write refused with 403
 * `auth.step_up_required` asks the person to confirm it's them, with a
 * passkey, their password or their authenticator app's code, and the client
 * sends the write again once they have (`setApiHandlers({stepUp})`). A read
 * never asks.
 *
 * Writes refused together share one dialog. Closing it is a no: each write
 * then fails with its `auth.step_up_required`, which a screen meets with
 * nothing said (`refusedQuietly`). The fifth wrong try ends the session
 * (401 `kernel.not_signed_in`): the dialog closes and the page's guard takes
 * the person to sign in.
 *
 * The dialog is drawn outside the page's frames, so it takes the look of the
 * frame it opened over: the admin's in the admin, else the site's.
 */
import { useEffect, useRef, useState, type SubmitEvent, type ReactNode } from "react";

import { ApiProblem, api, setApiHandlers, useApiQuery } from "../api/client";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Field, Input } from "../ui/Field";
import { Icon } from "../ui/Icon";
import { PasskeyCancelled, getPasskey, passkeysWork } from "./passkey";
import { said } from "./words";

/** A refusal a screen says nothing about: the person closed the step-up, or a passkey prompt. */
export function refusedQuietly(error: unknown): boolean {
  return error instanceof PasskeyCancelled || (error instanceof ApiProblem && error.code === "auth.step_up_required");
}

type Asking = { answer: (confirmed: boolean) => void };

export function StepUpProvider({ children }: { children: ReactNode }) {
  const [asking, setAsking] = useState<Asking | null>(null);
  const open = useRef<Promise<boolean> | null>(null);

  useEffect(() => {
    setApiHandlers({
      stepUp: () => {
        open.current ??= new Promise<boolean>((resolve) => {
          setAsking({
            answer: (confirmed) => {
              open.current = null;
              setAsking(null);
              resolve(confirmed);
            },
          });
        });
        return open.current;
      },
    });
    return () => {
      setApiHandlers({ stepUp: () => Promise.resolve(false) });
    };
  }, []);

  return (
    <>
      {children}
      {asking ? <StepUpDialog onDone={asking.answer} /> : null}
    </>
  );
}

const REFUSED = {
  "auth.invalid_credentials": "That password isn't right.",
  "auth.invalid_second_factor": "That code didn't match. Check your app and try again.",
  "auth.invalid_passkey": "That passkey isn't one of this account's.",
  "auth.no_passkey": "Your account has no passkey now. Use another way.",
};

export function StepUpDialog({ onDone }: { onDone: (confirmed: boolean) => void }) {
  const [look] = useState(() => (document.querySelector(".mf-admin-look") ? "mf-admin-look" : "mf-site-look"));
  const security = useApiQuery("get", "/api/auth/security", undefined, { staleTime: 0 });
  const passkeys = useApiQuery("get", "/api/auth/passkeys", undefined, { staleTime: 0 });
  const [chosen, setChosen] = useState<"password" | "totp">("password");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const hasPassword = security.data?.password ?? true;
  const hasTotp = Boolean(security.data?.totp);
  const way = chosen === "totp" && hasTotp ? "totp" : hasPassword ? "password" : hasTotp ? "totp" : "none";
  const byPasskey = passkeysWork() && (passkeys.data?.items.length ?? 0) > 0;

  const step = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await work();
      onDone(true);
    } catch (caught) {
      if (caught instanceof ApiProblem && caught.code === "kernel.not_signed_in") {
        onDone(false); // the fifth wrong try ended the session: the page's guard takes over
        return;
      }
      if (caught instanceof PasskeyCancelled) return;
      setError(caught instanceof ApiProblem ? said(caught, REFUSED) : "Your browser couldn't use a passkey here. Try another way.");
    } finally {
      setBusy(false);
    }
  };

  const withPasskey = () =>
    step(async () => {
      const { data: options } = await api.POST("/api/auth/step-up/passkey");
      if (!options) throw ApiProblem.unreachable();
      const passkey = await getPasskey(options);
      await api.POST("/api/auth/step-up", { body: { passkey } });
    });

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (way === "password") {
      if (!password) {
        setError("Enter your password.");
        return;
      }
      void step(() => api.POST("/api/auth/step-up", { body: { password } }));
    } else if (way === "totp") {
      const typed = code.replace(/\s/g, "");
      if (!/^\d{6}$/.test(typed)) {
        setError("Enter the 6 digits your app shows.");
        return;
      }
      void step(() => api.POST("/api/auth/step-up", { body: { totp: typed } }));
    }
  };

  return (
    <Dialog
      title="Confirm it's you"
      onClose={() => {
        onDone(false);
      }}
    >
      <div className={`${look} mf-step-up`}>
        <p className="mf-dialog-lead">It&apos;s been more than 10 minutes since you signed in. Confirm it&apos;s you to go on.</p>
        {byPasskey ? (
          <Button variant="strong" disabled={busy} onClick={() => void withPasskey()}>
            <Icon name="key" />
            Use a passkey
          </Button>
        ) : null}
        <form className="mf-step-up-form" noValidate onSubmit={submit}>
          {way === "password" ? (
            <Field label="Password">
              <Input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
              />
            </Field>
          ) : way === "totp" ? (
            <Field label="Code from your app">
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
          ) : null}
          {error ? (
            <p className="mf-dialog-error" role="alert">
              {error}
            </p>
          ) : null}
          {hasPassword && hasTotp ? (
            <button
              type="button"
              className="mf-text-link mf-step-up-switch"
              onClick={() => {
                setError("");
                setChosen(way === "password" ? "totp" : "password");
              }}
            >
              {way === "password" ? "Use your authenticator app instead" : "Use your password instead"}
            </button>
          ) : null}
          <div className="mf-dialog-actions">
            <Button
              onClick={() => {
                onDone(false);
              }}
            >
              Cancel
            </Button>
            {way !== "none" ? (
              <Button type="submit" variant="primary" disabled={busy}>
                Confirm
              </Button>
            ) : null}
          </div>
        </form>
      </div>
    </Dialog>
  );
}
