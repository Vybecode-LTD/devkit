/**
 * `/sign-in` (K4 contract §2; VM Website design/site/Auth.dc.html): a
 * passkey, an email and password, or a code emailed to the address, then
 * the second step for an account that has one. A sign-in's answer sets the
 * session (`setSessionUser`), and the page then moves on to `?next=` when it's
 * a path on this site, else home.
 *
 * The answers never say whether an account exists (auth-api.md): a wrong
 * password and an unknown address read the same, and the code step says a
 * code was sent whether or not one was.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState, type SubmitEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { ApiProblem, api } from "../api/client";
import type { components } from "../api/schema";
import { safeNext } from "../guards/next";
import { Seo } from "../seo/Seo";
import { setSessionUser, useSession, type SessionUser } from "../session/session";
import { useSite } from "../site/site";
import { useTitle } from "../app/pages/KernelPages";
import { Button } from "../ui/Button";
import { Field, Input } from "../ui/Field";
import { Icon } from "../ui/Icon";
import { AuthPanel, FormError, Or } from "./AuthFrame";
import { PasskeyCancelled, getPasskey, passkeysWork } from "./passkey";
import { said } from "./words";

export type Method = components["schemas"]["SecondFactorNeeded"]["methods"][number];
type Answer = components["schemas"]["SignedIn"] | components["schemas"]["SecondFactorNeeded"];

/** Where a sign-in goes on to: `?next=` when it's a path on this site, else home. */
export function useNextPath(): string {
  const [params] = useSearchParams();
  return safeNext(params.get("next")) ?? "/";
}

/** Shows the person signed in; the page they're on then moves on (it watches the session). */
export function useSignedIn(): (user: SessionUser) => Promise<void> {
  const queryClient = useQueryClient();
  return (user) => setSessionUser(queryClient, user);
}

/** A call's refusal, or nothing wrong: a closed passkey prompt is the person's choice. */
function refusal(error: unknown, own: Readonly<Record<string, string>>): string {
  if (error instanceof PasskeyCancelled) return "";
  if (error instanceof ApiProblem) return said(error, own);
  return "Your browser couldn't use a passkey here. Try another way in.";
}

const EMAIL = /^[^\s@]+@[^\s@]+$/;

type Step = { at: "start" } | { at: "code"; email: string } | { at: "second"; challenge: string; methods: Method[] };

export default function SignIn() {
  const session = useSession();
  const next = useNextPath();
  const site = useSite();
  const signedIn = useSignedIn();
  const [step, setStep] = useState<Step>({ at: "start" });
  const [moved, setMoved] = useState(false);
  const [notice, setNotice] = useState("");
  const goTo = (next: Step) => {
    setMoved(true);
    setStep(next);
  };
  const title = useTitle("Sign in");

  if (session.status === "signed-in") return <Navigate to={next} replace />;

  const answered = async (answer: Answer) => {
    if (answer.status === "signed_in") await signedIn(answer.user);
    else goTo({ at: "second", challenge: answer.challenge, methods: answer.methods });
  };

  return (
    <>
      <Seo title={title} noindex />
      {step.at === "start" ? (
        <Start
          lead={site ? `Welcome back to ${site.name}.` : "Welcome back."}
          notice={notice}
          moved={moved}
          onAnswer={answered}
          onCodeSent={(email) => {
            setNotice("");
            goTo({ at: "code", email });
          }}
        />
      ) : step.at === "code" ? (
        <CodeStep
          email={step.email}
          onAnswer={answered}
          onBack={() => {
            goTo({ at: "start" });
          }}
        />
      ) : (
        <SecondStep
          challenge={step.challenge}
          methods={step.methods}
          onSignedIn={signedIn}
          onEnded={() => {
            setNotice("That sign-in ran out, or had too many tries. Start again.");
            goTo({ at: "start" });
          }}
        />
      )}
    </>
  );
}

function Start({
  lead,
  notice,
  moved,
  onAnswer,
  onCodeSent,
}: {
  lead: string;
  notice: string;
  moved: boolean;
  onAnswer: (answer: Answer) => Promise<void>;
  onCodeSent: (email: string) => void;
}) {
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [error, setError] = useState(notice);
  const [busy, setBusy] = useState(false);
  const next = params.get("next");
  const signUp = next ? `/sign-up?next=${encodeURIComponent(next)}` : "/sign-up";

  const run = async (work: () => Promise<void>, own: Record<string, string>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (caught) {
      setError(refusal(caught, own));
    } finally {
      setBusy(false);
    }
  };

  const checkEmail = (): boolean => {
    const ok = EMAIL.test(email.trim());
    setEmailError(ok ? "" : "Enter the email address of your account.");
    return ok;
  };

  const withPasskey = () =>
    run(
      async () => {
        const { data: options } = await api.POST("/api/auth/passkeys/sign-in/start");
        if (!options) throw ApiProblem.unreachable();
        const credential = await getPasskey(options);
        const { data } = await api.POST("/api/auth/passkeys/sign-in/finish", { body: credential });
        if (!data) throw ApiProblem.unreachable();
        await onAnswer(data);
      },
      { "auth.invalid_passkey": "That passkey isn't one this site knows. Try another way in." },
    );

  const withPassword = (event: SubmitEvent) => {
    event.preventDefault();
    const emailOk = checkEmail();
    setPasswordError(password ? "" : "Enter your password.");
    if (!emailOk || !password) return;
    void run(
      async () => {
        const { data } = await api.POST("/api/auth/sign-in", { body: { email: email.trim(), password } });
        if (!data) throw ApiProblem.unreachable();
        await onAnswer(data);
      },
      { "auth.invalid_credentials": "That email and password don't match an account here." },
    );
  };

  const byCode = () => {
    if (!checkEmail()) return;
    void run(async () => {
      await api.POST("/api/auth/code", { body: { email: email.trim() } });
      onCodeSent(email.trim());
    }, {});
  };

  return (
    <AuthPanel title="Sign in" lead={lead} step="start" focus={moved}>
      {passkeysWork() ? (
        <>
          <Button variant="strong" size="large" disabled={busy} onClick={() => void withPasskey()}>
            <Icon name="key" />
            Sign in with a passkey
          </Button>
          <Or />
        </>
      ) : null}
      <form className="mf-auth-form" noValidate onSubmit={withPassword}>
        <Field label="Email" size="large" error={emailError}>
          <Input
            type="email"
            name="email"
            autoComplete="username webauthn"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
          />
        </Field>
        <Field
          label="Password"
          size="large"
          error={passwordError}
          aside={
            <Link className="mf-text-link" to="/forgot-password">
              Forgot password?
            </Link>
          }
        >
          <Input
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
            }}
          />
        </Field>
        <FormError>{error}</FormError>
        <Button type="submit" variant="primary" size="large" disabled={busy}>
          Sign in
        </Button>
      </form>
      <Button size="large" disabled={busy} onClick={byCode}>
        <Icon name="mail" />
        Email me a code instead
      </Button>
      <p className="mf-auth-note">
        New here?{" "}
        <Link className="mf-text-link" to={signUp}>
          Create an account
        </Link>
      </p>
    </AuthPanel>
  );
}

function CodeStep({ email, onAnswer, onBack }: { email: string; onAnswer: (answer: Answer) => Promise<void>; onBack: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const verify = (event: SubmitEvent) => {
    event.preventDefault();
    const typed = code.replace(/\s/g, "");
    if (!/^\d{6}$/.test(typed)) {
      setError("Enter the 6 digits from the email.");
      return;
    }
    setBusy(true);
    setError("");
    void (async () => {
      try {
        const { data } = await api.POST("/api/auth/code/verify", { body: { email, code: typed } });
        if (!data) throw ApiProblem.unreachable();
        await onAnswer(data);
      } catch (caught) {
        setError(refusal(caught, { "auth.invalid_code": "That code is wrong, or it's run out. Check the newest email." }));
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <AuthPanel
      title="Check your email"
      lead={`We sent a 6-digit code to ${email}. It works for 10 minutes. The same email has a link too, if that's easier.`}
      step="code"
      focus
    >
      <form className="mf-auth-form" noValidate onSubmit={verify}>
        <Field label="Code" size="large">
          <Input
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="000000"
            value={code}
            onChange={(event) => {
              setCode(event.target.value);
            }}
          />
        </Field>
        <FormError>{error}</FormError>
        <Button type="submit" variant="primary" size="large" disabled={busy}>
          Sign in
        </Button>
      </form>
      <p className="mf-auth-note">
        No email? Check spam. A new code can be sent after a minute.{" "}
        <button type="button" className="mf-text-link" onClick={onBack}>
          Back to sign in
        </button>
      </p>
    </AuthPanel>
  );
}

function secondLead(methods: readonly Method[], passkeys: boolean): string {
  const passkey = passkeys && methods.includes("passkey");
  const totp = methods.includes("totp");
  if (passkey && totp) return "Your account has a second factor. Use your passkey, or the code from your authenticator app.";
  if (passkey) return "Your account has a second factor. Use your passkey.";
  if (totp) return "Your account has a second factor. Enter the code from your authenticator app.";
  return "Your account has a second factor. Use one of your recovery codes.";
}

const SECOND_REFUSED = {
  "auth.invalid_second_factor": "That didn't match. Check the code and try again.",
  "auth.invalid_passkey": "That passkey isn't one of this account's. Try your app's code.",
  "auth.no_passkey": "Your account has no passkey now. Use your app's code.",
};

/**
 * The second step, after a password, a code or a link: the account's passkey
 * or its authenticator app's code, and a recovery code when neither is to
 * hand. A challenge that ran out or had five wrong tries sends the person
 * back to the start (`onEnded`).
 */
export function SecondStep({
  challenge,
  methods,
  onSignedIn,
  onEnded,
}: {
  challenge: string;
  methods: readonly Method[];
  onSignedIn: (user: SessionUser) => Promise<void>;
  onEnded: () => void;
}) {
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const passkeys = passkeysWork();
  const byPasskey = passkeys && methods.includes("passkey");
  const byTotp = methods.includes("totp");
  const byRecovery = methods.includes("recovery_code");

  const finish = async (work: () => Promise<components["schemas"]["SignedIn"] | undefined>) => {
    setBusy(true);
    setError("");
    try {
      const done = await work();
      if (!done) throw ApiProblem.unreachable();
      await onSignedIn(done.user);
    } catch (caught) {
      if (caught instanceof ApiProblem && caught.code === "auth.challenge_ended") {
        onEnded();
        return;
      }
      setError(refusal(caught, SECOND_REFUSED));
    } finally {
      setBusy(false);
    }
  };

  const withPasskey = () =>
    finish(async () => {
      const { data: options } = await api.POST("/api/auth/sign-in/second-factor/passkey", { body: { challenge } });
      if (!options) throw ApiProblem.unreachable();
      const passkey = await getPasskey(options);
      return (await api.POST("/api/auth/sign-in/second-factor", { body: { challenge, passkey } })).data;
    });

  const withCode = (event: SubmitEvent) => {
    event.preventDefault();
    const typed = code.replace(/\s/g, "");
    if (!/^\d{6}$/.test(typed)) {
      setError("Enter the 6 digits your app shows.");
      return;
    }
    void finish(async () => (await api.POST("/api/auth/sign-in/second-factor", { body: { challenge, totp: typed } })).data);
  };

  const withRecovery = (event: SubmitEvent) => {
    event.preventDefault();
    const typed = recovery.trim();
    if (!typed) {
      setError("Enter one of your recovery codes.");
      return;
    }
    void finish(async () => (await api.POST("/api/auth/sign-in/second-factor", { body: { challenge, recovery_code: typed } })).data);
  };

  const recoveryForm = (
    <form className="mf-auth-form" noValidate onSubmit={withRecovery}>
      <Field label="Recovery code" size="large" hint="Each recovery code works once.">
        <Input
          name="recovery_code"
          autoComplete="off"
          value={recovery}
          onChange={(event) => {
            setRecovery(event.target.value);
          }}
        />
      </Field>
      <Button type="submit" size="large" disabled={busy}>
        Use recovery code
      </Button>
    </form>
  );

  return (
    <AuthPanel title="One more step" lead={secondLead(methods, passkeys)} step="second" focus>
      {byPasskey ? (
        <>
          <Button variant="strong" size="large" disabled={busy} onClick={() => void withPasskey()}>
            <Icon name="key" />
            Use a passkey
          </Button>
          {byTotp ? <Or /> : null}
        </>
      ) : null}
      {byTotp ? (
        <form className="mf-auth-form" noValidate onSubmit={withCode}>
          <Field label="Code from your app" size="large">
            <Input
              name="totp"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="000000"
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
              }}
            />
          </Field>
          <Button type="submit" variant="primary" size="large" disabled={busy}>
            Continue
          </Button>
        </form>
      ) : null}
      <FormError>{error}</FormError>
      {byRecovery ? (
        byPasskey || byTotp ? (
          <details className="mf-auth-more">
            <summary>Can&apos;t use either?</summary>
            <div className="mf-auth-more-body">{recoveryForm}</div>
          </details>
        ) : (
          recoveryForm
        )
      ) : null}
    </AuthPanel>
  );
}
