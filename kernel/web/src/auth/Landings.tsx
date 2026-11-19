/**
 * The pages a link in the kernel's mail opens (K4 contract §2): confirming
 * an address, signing in by link, choosing a new password, confirming or
 * undoing an email change, removing a second factor someone else added, and
 * unsubscribing. Each takes its `?token=` out of the address bar first, and
 * acts only when the person presses its button, never on load: mail
 * scanners open links (auth-api.md). None of them signs anybody in but the
 * sign-in link, whose answer may still ask for the second step.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState, type SubmitEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { ApiProblem, api, useApiQuery } from "../api/client";
import { useTitle } from "../app/pages/KernelPages";
import { Seo } from "../seo/Seo";
import { recheckSession, useSession, type SessionUser } from "../session/session";
import { Button } from "../ui/Button";
import { Field, Input } from "../ui/Field";
import { AuthPanel, FormError } from "./AuthFrame";
import { PASSWORD_HINT } from "./SignUp";
import { SecondStep, useSignedIn, type Method } from "./SignIn";
import { useAddressToken } from "./token";
import { said } from "./words";

const NO_TOKEN = "This link is missing its code. Open it from the email again.";

type LandingProps = {
  /** The page's title in the tab (the kernel page's own). */
  page: string;
  title: string;
  lead: ReactNode;
  action: string;
  /** Sends the token; throws the API's refusal. */
  run: (token: string) => Promise<unknown>;
  /** What the page says once it's done. */
  done: { title: string; lead: ReactNode; next?: ReactNode };
  /** The page's own words for its refusals. */
  refused: Readonly<Record<string, string>>;
  note?: ReactNode;
};

function Landing({ page, title, lead, action, run, done, refused, note }: LandingProps) {
  const token = useAddressToken();
  const queryClient = useQueryClient();
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const heading = useTitle(page);

  const act = () => {
    if (!token) {
      setError(NO_TOKEN);
      return;
    }
    setBusy(true);
    setError("");
    void (async () => {
      try {
        await run(token);
        // Success changed the account (confirmed, changed, ended its sessions) and no
        // 401 will say so: read it again (Codex and CodeRabbit on #83).
        await recheckSession(queryClient);
        setFinished(true);
      } catch (caught) {
        if (!(caught instanceof ApiProblem)) throw caught;
        setError(said(caught, refused));
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <>
      <Seo title={heading} noindex />
      {finished ? (
        <AuthPanel title={done.title} lead={done.lead} step="done" focus>
          {done.next}
        </AuthPanel>
      ) : (
        <AuthPanel title={title} lead={lead} step="ask">
          <FormError>{error || (token ? "" : NO_TOKEN)}</FormError>
          <Button variant="primary" size="large" disabled={busy || !token} onClick={act}>
            {action}
          </Button>
          {note ? <p className="mf-auth-note">{note}</p> : null}
        </AuthPanel>
      )}
    </>
  );
}

function SignInLink({ words = "Sign in" }: { words?: string }) {
  return (
    <p className="mf-auth-note">
      <Link className="mf-text-link" to="/sign-in">
        {words}
      </Link>
    </p>
  );
}

const SIGNED_OUT_EVERYWHERE = "Every device that was signed in to your account is signed out.";

export function VerifyEmail() {
  const session = useSession();
  return (
    <Landing
      page="Verify your email"
      title="Confirm your email"
      lead="Press the button to confirm this address is yours."
      action="Confirm my email"
      run={(token) => api.POST("/api/auth/verify-email", { body: { token } })}
      done={{
        title: "Email confirmed",
        lead: "Your address is confirmed.",
        next:
          session.status === "signed-in" ? (
            <p className="mf-auth-note">
              <Link className="mf-text-link" to="/account">
                Go to your account
              </Link>
            </p>
          ) : (
            <SignInLink words="Sign in now" />
          ),
      }}
      refused={{
        "auth.token_invalid": "This link was used already, or it's more than a day old. Sign in, and ask for a new one from your account.",
      }}
    />
  );
}

export function ResetPassword() {
  const token = useAddressToken();
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [error, setError] = useState(token ? "" : NO_TOKEN);
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState(false);
  const heading = useTitle("Choose a new password");
  const queryClient = useQueryClient();

  const save = (event: SubmitEvent) => {
    event.preventDefault();
    if (!token) return;
    setPasswordError(password.length >= 12 ? "" : "Use at least 12 characters.");
    if (password.length < 12) return;
    setBusy(true);
    setError("");
    void (async () => {
      try {
        await api.POST("/api/auth/password/reset", { body: { token, password } });
        // Every session ended, this one too, and the answer was a success (Codex on #83).
        await recheckSession(queryClient);
        setFinished(true);
      } catch (caught) {
        if (!(caught instanceof ApiProblem)) throw caught;
        if (caught.code === "auth.password_rejected") setPasswordError(caught.detail || "Choose another password.");
        else setError(said(caught, { "auth.token_invalid": "This link was used already, or it's more than 30 minutes old. Ask for a new one." }));
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <>
      <Seo title={heading} noindex />
      {finished ? (
        <AuthPanel title="Password saved" lead={`Sign in with your new password. ${SIGNED_OUT_EVERYWHERE}`} step="done" focus>
          <SignInLink />
        </AuthPanel>
      ) : (
        <AuthPanel title="New password" lead="Choose a new password for your account." step="ask">
          <form className="mf-auth-form" noValidate onSubmit={save}>
            <Field label="New password" size="large" hint={PASSWORD_HINT} error={passwordError}>
              <Input
                type="password"
                name="new-password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
              />
            </Field>
            <FormError>{error}</FormError>
            <Button type="submit" variant="primary" size="large" disabled={busy || !token}>
              Save password
            </Button>
          </form>
          <p className="mf-auth-note">
            <Link className="mf-text-link" to="/forgot-password">
              Ask for a new link
            </Link>
          </p>
        </AuthPanel>
      )}
    </>
  );
}

export function ConfirmEmailChange() {
  return (
    <Landing
      page="Confirm your new email"
      title="Confirm your new email"
      lead="Press the button to make this address your account's."
      action="Confirm new email"
      run={(token) => api.POST("/api/auth/email/confirm", { body: { token } })}
      done={{
        title: "Email changed",
        lead: "Your account uses this address now. We've told your old address, in case this wasn't you.",
        next: <SignInLink words="Back to sign in" />,
      }}
      refused={{ "auth.token_invalid": "This link was used already, or it's more than a day old. Ask for the change again from your account." }}
    />
  );
}

export function UndoEmailChange() {
  return (
    <Landing
      page="Undo the email change"
      title="Undo the email change"
      lead={`Your account's email was changed. If it wasn't you, put your old address back. ${SIGNED_OUT_EVERYWHERE.replace("is signed out", "will be signed out")}`}
      action="Put my old email back"
      run={(token) => api.POST("/api/auth/email/undo", { body: { token } })}
      done={{
        title: "Old email back",
        lead: `${SIGNED_OUT_EVERYWHERE} Sign in, then change your password if someone else may know it.`,
        next: <SignInLink />,
      }}
      refused={{ "auth.token_invalid": "This link was used already, or it's more than 7 days old." }}
    />
  );
}

export function UndoSecondFactor() {
  return (
    <Landing
      page="Remove the new sign-in step"
      title="Remove the new sign-in step"
      lead="A passkey or an authenticator app was added to your account. If you didn't add it, remove it here. Every device signed in to your account will be signed out."
      action="Remove it"
      run={(token) => api.POST("/api/auth/second-factor/undo", { body: { token } })}
      done={{
        title: "Removed",
        lead: `${SIGNED_OUT_EVERYWHERE} Sign in, then change your password if someone else may know it.`,
        next: <SignInLink />,
      }}
      refused={{ "auth.token_invalid": "This link was used already, or it's more than 7 days old." }}
    />
  );
}

/** `/auth/link`: the board's "Sign in here?", then the second step if the account has one. */
export function SignInByLink() {
  const token = useAddressToken();
  const setUser = useSignedIn();
  const [second, setSecond] = useState<{ challenge: string; methods: Method[] } | null>(null);
  const [ended, setEnded] = useState(false);
  const [arrived, setArrived] = useState(false);
  const [error, setError] = useState(token ? "" : NO_TOKEN);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const heading = useTitle("Sign in with a link");

  // Signed in by this link: home. Someone already signed in may still use a link for another account.
  if (arrived) return <Navigate to="/" replace />;
  const signedIn = async (user: SessionUser) => {
    await setUser(user);
    setArrived(true);
  };

  const confirm = () => {
    if (!token) return;
    setBusy(true);
    setError("");
    void (async () => {
      try {
        const { data } = await api.POST("/api/auth/link/confirm", { body: { token } });
        if (!data) throw ApiProblem.unreachable();
        if (data.status === "signed_in") await signedIn(data.user);
        else setSecond({ challenge: data.challenge, methods: data.methods });
      } catch (caught) {
        if (!(caught instanceof ApiProblem)) throw caught;
        setError(said(caught, { "auth.invalid_link": "This link was used already, or it's run out. Sign in again for a new one." }));
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <>
      <Seo title={heading} noindex />
      {ended ? (
        <AuthPanel title="Start again" lead="That sign-in ran out, or had too many tries." step="ended" focus>
          <SignInLink words="Back to sign in" />
        </AuthPanel>
      ) : second ? (
        <SecondStep
          challenge={second.challenge}
          methods={second.methods}
          onSignedIn={signedIn}
          onEnded={() => {
            setEnded(true);
          }}
          onBack={() => {
            void navigate("/sign-in");
          }}
        />
      ) : (
        <AuthPanel title="Sign in here?" lead="You opened a sign-in link. Confirm to finish signing in on this device." step="ask">
          <FormError>{error}</FormError>
          <Button variant="primary" size="large" disabled={busy || !token} onClick={confirm}>
            Sign me in
          </Button>
          <p className="mf-auth-note">Didn&apos;t ask for this? Close this page. Nothing happens until you confirm.</p>
        </AuthPanel>
      )}
    </>
  );
}

/** `/notifications/unsubscribe`: what the link turns off, read without changing it, then off on the press. */
export function Unsubscribe() {
  const token = useAddressToken();
  const heading = useTitle("Unsubscribe");
  const found = useApiQuery("get", "/api/kernel/notifications/unsubscribe", { params: { query: { token } } }, { enabled: Boolean(token) });
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const off = () => {
    setBusy(true);
    setError("");
    void (async () => {
      try {
        await api.POST("/api/kernel/notifications/unsubscribe", { params: { query: { token } } });
        setDone(true);
      } catch (caught) {
        if (!(caught instanceof ApiProblem)) throw caught;
        setError(said(caught, { "kernel.not_found": "This link isn't one this site sent." }));
      } finally {
        setBusy(false);
      }
    })();
  };

  const link = found.data;
  const problem = !token ? NO_TOKEN : found.error ? said(found.error, { "kernel.not_found": "This link isn't one this site sent." }) : "";
  return (
    <>
      <Seo title={heading} noindex />
      {done ? (
        <AuthPanel title="Unsubscribed" lead="You won't get these by email any more. You can turn them back on from your account." step="done" focus>
          <p className="mf-auth-note">
            <Link className="mf-text-link" to="/account/notifications">
              Your notification settings
            </Link>
          </p>
        </AuthPanel>
      ) : (
        <AuthPanel
          title="Unsubscribe"
          lead={link ? (link.email ? `Stop emails about this: ${link.description}` : `You don't get emails about this now: ${link.description}`) : undefined}
          step="ask"
        >
          <FormError>{error || problem}</FormError>
          {link?.email ? (
            <Button variant="primary" size="large" disabled={busy} onClick={off}>
              Unsubscribe
            </Button>
          ) : null}
        </AuthPanel>
      )}
    </>
  );
}
