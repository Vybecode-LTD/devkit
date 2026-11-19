/**
 * `/sign-up` (VM Website design/site/Auth.dc.html, "Sign up" and "Check your
 * email"): an email and a password, then a link mailed to confirm the
 * address. The answer is the same whether the address has an account or not
 * (auth-api.md), so the next step always says a link is on its way.
 *
 * The board's name field and its news box have no home in the kernel's
 * sign-up (`{email, password}`), so they're left off rather than faked.
 */
import { useState, type SubmitEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { ApiProblem, api } from "../api/client";
import { useTitle } from "../app/pages/KernelPages";
import { Seo } from "../seo/Seo";
import { useSession } from "../session/session";
import { Button } from "../ui/Button";
import { Field, Input } from "../ui/Field";
import { AuthPanel, FormError } from "./AuthFrame";
import { useNextPath } from "./SignIn";
import { said } from "./words";

export const PASSWORD_HINT = "At least 12 characters. A few random words work well; no rules about symbols.";
const EMAIL = /^[^\s@]+@[^\s@]+$/;

export default function SignUp() {
  const session = useSession();
  const next = useNextPath();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState("");
  const title = useTitle("Sign up");
  const back = params.get("next") ? `/sign-in?next=${encodeURIComponent(params.get("next") ?? "")}` : "/sign-in";

  if (session.status === "signed-in" && !sent) return <Navigate to={next} replace />;

  const create = (event: SubmitEvent) => {
    event.preventDefault();
    const address = email.trim();
    const emailOk = EMAIL.test(address);
    setEmailError(emailOk ? "" : "Enter your email address.");
    setPasswordError(password.length >= 12 ? "" : "Use at least 12 characters.");
    if (!emailOk || password.length < 12) return;
    setBusy(true);
    setError("");
    void (async () => {
      try {
        await api.POST("/api/auth/sign-up", { body: { email: address, password } });
        setSent(address);
      } catch (caught) {
        if (!(caught instanceof ApiProblem)) throw caught;
        if (caught.code === "auth.password_rejected") setPasswordError(caught.detail || "Choose another password.");
        else if (caught.code === "kernel.invalid_request") setEmailError("Enter one email address.");
        else
          setError(
            said(caught, {
              "auth.sign_up_closed": "This site isn't taking new accounts right now.",
              "auth.invite_required": "This site is invite-only: you need an invite to join.",
            }),
          );
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <>
      <Seo title={title} noindex />
      {sent ? (
        <AuthPanel
          title="Check your email"
          lead={`We sent a link to ${sent} to confirm it's yours. Open it to finish setting up your account.`}
          step="sent"
          focus
        >
          <p className="mf-auth-note">
            Nothing after a few minutes? Check spam.{" "}
            <Link className="mf-text-link" to={back}>
              Back to sign in
            </Link>
          </p>
        </AuthPanel>
      ) : (
        <AuthPanel title="Create an account" lead="It's free, and one account works everywhere on this site." step="form">
          <form className="mf-auth-form" noValidate onSubmit={create}>
            <Field label="Email" size="large" error={emailError}>
              <Input
                type="email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                }}
              />
            </Field>
            <Field label="Password" size="large" hint={PASSWORD_HINT} error={passwordError}>
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
            <Button type="submit" variant="primary" size="large" disabled={busy}>
              Create account
            </Button>
          </form>
          <p className="mf-auth-note">
            You can add a passkey once your email is confirmed. Have an account?{" "}
            <Link className="mf-text-link" to={back}>
              Sign in
            </Link>
          </p>
        </AuthPanel>
      )}
    </>
  );
}
