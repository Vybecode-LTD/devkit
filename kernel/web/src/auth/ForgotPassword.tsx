/**
 * `/forgot-password` (VM Website design/site/Auth.dc.html, "Reset password"
 * and "Check your email"): an email, then a link to choose a new password.
 * The answer is the same whether the address has an account or not, and a
 * second ask within a minute sends nothing more (auth-api.md), so "Send it
 * again" can't be used to flood an inbox.
 */
import { useState, type SubmitEvent } from "react";
import { Link } from "react-router";

import { ApiProblem, api } from "../api/client";
import { useTitle } from "../app/pages/KernelPages";
import { Seo } from "../seo/Seo";
import { Button } from "../ui/Button";
import { Field, Input } from "../ui/Field";
import { useToast } from "../ui/Toast";
import { AuthPanel, FormError } from "./AuthFrame";
import { said } from "./words";

const EMAIL = /^[^\s@]+@[^\s@]+$/;

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState("");
  const toast = useToast();
  const title = useTitle("Forgot password");

  const ask = async (address: string): Promise<boolean> => {
    setBusy(true);
    setError("");
    try {
      await api.POST("/api/auth/password/reset-request", { body: { email: address } });
      return true;
    } catch (caught) {
      if (!(caught instanceof ApiProblem)) throw caught;
      setError(said(caught));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const send = (event: SubmitEvent) => {
    event.preventDefault();
    const address = email.trim();
    const ok = EMAIL.test(address);
    setEmailError(ok ? "" : "Enter the email address of your account.");
    if (!ok) return;
    void ask(address).then((asked) => {
      if (asked) setSent(address);
    });
  };

  return (
    <>
      <Seo title={title} noindex />
      {sent ? (
        <AuthPanel
          title="Check your email"
          lead={`If ${sent} belongs to an account, a link to choose a new password is on its way. It works for 30 minutes.`}
          step="sent"
          focus
        >
          <FormError>{error}</FormError>
          <Button
            size="large"
            disabled={busy}
            onClick={() => {
              void ask(sent).then((asked) => {
                if (asked) toast({ tone: "success", text: "If the address has an account, another link is on its way." });
              });
            }}
          >
            Send it again
          </Button>
          <p className="mf-auth-note">
            Nothing after a few minutes? Check spam.{" "}
            <Link className="mf-text-link" to="/sign-in">
              Back to sign in
            </Link>
          </p>
        </AuthPanel>
      ) : (
        <AuthPanel title="Reset password" lead="Enter your email. If it belongs to an account, we'll send a link to choose a new password." step="form">
          <form className="mf-auth-form" noValidate onSubmit={send}>
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
            <FormError>{error}</FormError>
            <Button type="submit" variant="primary" size="large" disabled={busy}>
              Send reset link
            </Button>
          </form>
          <p className="mf-auth-note">
            <Link className="mf-text-link" to="/sign-in">
              Back to sign in
            </Link>
          </p>
        </AuthPanel>
      )}
    </>
  );
}
