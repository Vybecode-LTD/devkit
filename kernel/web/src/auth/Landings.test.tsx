import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import { problem, routedFetch } from "../test-fetch";

// The screens load lazily; import them once before the tests, so none waits on a first import.
beforeAll(async () => {
  await Promise.all([import("./Landings")]);
});

function at(router: ReturnType<typeof renderApp>["router"]) {
  return router.state.location.pathname + router.state.location.search;
}

const LANDINGS = [
  { path: "/auth/verify", heading: "Confirm your email", button: "Confirm my email", api: "/api/auth/verify-email", done: "Email confirmed" },
  { path: "/auth/email", heading: "Confirm your new email", button: "Confirm new email", api: "/api/auth/email/confirm", done: "Email changed" },
  { path: "/auth/email/undo", heading: "Undo the email change", button: "Put my old email back", api: "/api/auth/email/undo", done: "Old email back" },
  { path: "/auth/second-factor/undo", heading: "Remove the new sign-in step", button: "Remove it", api: "/api/auth/second-factor/undo", done: "Removed" },
] as const;

describe("a landing from mail", () => {
  for (const landing of LANDINGS) {
    it(`${landing.path} takes the token out of the address, acts only on the press, and says it's done`, async () => {
      const { fetch, sent } = routedFetch({ [`POST ${landing.api}`]: { status: 200, body: { status: "done" } } });
      const { router } = renderApp({ path: `${landing.path}?token=t-123&from=mail` });
      expect(await screen.findByRole("heading", { level: 1, name: landing.heading })).toBeInTheDocument();
      await waitFor(() => {
        expect(at(router)).toBe(`${landing.path}?from=mail`);
      });
      expect(fetch).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole("button", { name: landing.button }));
      expect(await screen.findByRole("heading", { level: 1, name: landing.done })).toHaveFocus();
      expect(await sent[0]?.clone().json()).toEqual({ token: "t-123" });
    });
  }

  it("says a used or old link", async () => {
    routedFetch({ "POST /api/auth/verify-email": problem(400, "auth.token_invalid") });
    renderApp({ path: "/auth/verify?token=old" });
    await userEvent.click(await screen.findByRole("button", { name: "Confirm my email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link was used already, or it's more than a day old.");
  });

  it("can't act without a token, and says so", async () => {
    renderApp({ path: "/auth/email/undo" });
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is missing its code.");
    expect(screen.getByRole("button", { name: "Put my old email back" })).toBeDisabled();
  });

  it("sends someone signed in to their account once their email is confirmed", async () => {
    routedFetch({ "POST /api/auth/verify-email": { status: 200, body: { status: "verified" } } });
    renderApp({ path: "/auth/verify?token=t", session: testUser({ verified: false }) });
    await userEvent.click(await screen.findByRole("button", { name: "Confirm my email" }));
    expect(await screen.findByRole("link", { name: "Go to your account" })).toHaveAttribute("href", "/account");
  });
});

describe("choosing a new password", () => {
  it("sends the token with the new password, and says to sign in", async () => {
    const { sent } = routedFetch({ "POST /api/auth/password/reset": { status: 200, body: { status: "password_reset" } } });
    renderApp({ path: "/auth/reset?token=r-1" });
    await userEvent.type(await screen.findByLabelText("New password"), "copper heron valley");
    await userEvent.click(screen.getByRole("button", { name: "Save password" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Password saved" })).toBeInTheDocument();
    expect(await sent[0]?.clone().json()).toEqual({ token: "r-1", password: "copper heron valley" });
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  });

  it("asks for 12 characters, puts a rejected password on its field, and says an old link", async () => {
    let tries = 0;
    routedFetch({
      "POST /api/auth/password/reset": () => {
        tries += 1;
        return tries === 1 ? problem(422, "auth.password_rejected") : problem(400, "auth.token_invalid");
      },
    });
    renderApp({ path: "/auth/reset?token=r-1" });
    await userEvent.type(await screen.findByLabelText("New password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Save password" }));
    expect(screen.getByLabelText("New password")).toHaveAccessibleDescription(expect.stringContaining("Use at least 12 characters.") as string);
    await userEvent.type(screen.getByLabelText("New password"), " and longer now");
    await userEvent.click(screen.getByRole("button", { name: "Save password" }));
    await waitFor(() => {
      expect(screen.getByLabelText("New password")).toHaveAccessibleDescription(expect.stringContaining("Refused.") as string);
    });
    await userEvent.click(screen.getByRole("button", { name: "Save password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("more than 30 minutes old");
    expect(screen.getByRole("link", { name: "Ask for a new link" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("signing in by link", () => {
  it("signs in on the press and goes home", async () => {
    const { fetch } = routedFetch({ "POST /api/auth/link/confirm": { status: 200, body: { status: "signed_in", user: testUser() } } });
    const { router } = renderApp({ path: "/auth/link?token=l-1" });
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in here?" })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Sign me in" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
  });

  it("asks for the second step, and starts again when it runs out", async () => {
    routedFetch({
      "POST /api/auth/link/confirm": { status: 200, body: { status: "second_factor", challenge: "c", methods: ["totp"] } },
      "POST /api/auth/sign-in/second-factor": problem(401, "auth.challenge_ended"),
    });
    renderApp({ path: "/auth/link?token=l-1" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign me in" }));
    await userEvent.type(await screen.findByLabelText("Code from your app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Start again" })).toBeInTheDocument();
  });

  it("says a used link", async () => {
    routedFetch({ "POST /api/auth/link/confirm": problem(401, "auth.invalid_link") });
    renderApp({ path: "/auth/link?token=l-1" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign me in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link was used already");
  });
});

describe("unsubscribing", () => {
  it("says what the link turns off, without changing it, and turns it off on the press", async () => {
    const { sent } = routedFetch({
      "GET /api/kernel/notifications/unsubscribe": { status: 200, body: { key: "blog.reply", description: "Replies to your comments", email: true } },
      "POST /api/kernel/notifications/unsubscribe": { status: 200, body: { email: false } },
    });
    renderApp({ path: "/notifications/unsubscribe?token=u-1" });
    expect(await screen.findByText("Stop emails about this: Replies to your comments")).toBeInTheDocument();
    expect(sent.map((request) => request.method)).toEqual(["GET"]);
    expect(new URL(sent[0]?.url ?? "").searchParams.get("token")).toBe("u-1");
    await userEvent.click(screen.getByRole("button", { name: "Unsubscribe" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Unsubscribed" })).toBeInTheDocument();
  });

  it("says a link already off, and one the site didn't send", async () => {
    routedFetch({
      "GET /api/kernel/notifications/unsubscribe": { status: 200, body: { key: "k", description: "News", email: false } },
    });
    const { unmount } = renderApp({ path: "/notifications/unsubscribe?token=u-1" });
    expect(await screen.findByText("You don't get emails about this now: News")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unsubscribe" })).toBeNull();
    unmount();
    routedFetch({ "GET /api/kernel/notifications/unsubscribe": problem(404, "kernel.not_found") });
    renderApp({ path: "/notifications/unsubscribe?token=forged" });
    expect(await screen.findByRole("alert")).toHaveTextContent("This link isn't one this site sent.");
  });
});
