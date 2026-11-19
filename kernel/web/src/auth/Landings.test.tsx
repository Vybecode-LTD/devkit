import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { renderApp, testUser } from "../../testing";
import { SESSION_KEY, type SessionUser } from "../session/session";
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

  it("reads the session again after a confirmation, so the account shows it as it is now (CodeRabbit on #83)", async () => {
    for (const landing of LANDINGS.slice(0, 2)) {
      const { sent } = routedFetch({
        [`POST ${landing.api}`]: { status: 200, body: { status: "done" } },
        "GET /api/auth/session": { status: 200, body: { user: testUser({ verified: true }) } },
      });
      const { unmount } = renderApp({ path: `${landing.path}?token=t`, session: testUser({ verified: false }) });
      await userEvent.click(await screen.findByRole("button", { name: landing.button }));
      await screen.findByRole("heading", { level: 1, name: landing.done });
      const paths = sent.map((request) => `${request.method} ${new URL(request.url).pathname}`);
      expect(paths.indexOf("GET /api/auth/session")).toBeGreaterThan(paths.indexOf(`POST ${landing.api}`));
      unmount();
    }
  });

  it("reads the session fresh after a confirmation, not by joining an older read on its way (CodeRabbit on #83)", async () => {
    let reads = 0;
    let lateRead: () => void = () => undefined;
    routedFetch({ "POST /api/auth/verify-email": { status: 200, body: { status: "verified" } } });
    const base = globalThis.fetch;
    vi.stubGlobal("fetch", (request: Request) => {
      if (new URL(request.url).pathname !== "/api/auth/session") return base(request);
      reads += 1;
      const answer = (verified: boolean) =>
        new Response(JSON.stringify({ user: testUser({ verified }) }), { status: 200, headers: { "content-type": "application/json" } });
      if (reads === 1) {
        return new Promise<Response>((resolve) => {
          lateRead = () => {
            resolve(answer(false));
          };
        });
      }
      return Promise.resolve(answer(true));
    });
    const { queryClient } = renderApp({ path: "/auth/verify?token=t", session: testUser({ verified: false }) });
    void queryClient.refetchQueries({ queryKey: SESSION_KEY }); // a read on its way, from before the confirmation
    await userEvent.click(await screen.findByRole("button", { name: "Confirm my email" }));
    await screen.findByRole("heading", { level: 1, name: "Email confirmed" });
    lateRead();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(queryClient.getQueryData<SessionUser>(SESSION_KEY)?.verified).toBe(true);
  });

  it("marks the session to be read again when the re-read after a confirmation fails", async () => {
    routedFetch({
      "POST /api/auth/verify-email": { status: 200, body: { status: "verified" } },
      "GET /api/auth/session": problem(503, "kernel.busy"),
    });
    const { queryClient } = renderApp({ path: "/auth/verify?token=t", session: testUser({ verified: false }) });
    await userEvent.click(await screen.findByRole("button", { name: "Confirm my email" }));
    await screen.findByRole("heading", { level: 1, name: "Email confirmed" });
    expect(queryClient.getQueryState(SESSION_KEY)?.isInvalidated).toBe(true);
  });

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
    routedFetch({
      "POST /api/auth/verify-email": { status: 200, body: { status: "verified" } },
      "GET /api/auth/session": { status: 200, body: { user: testUser({ verified: true }) } },
    });
    renderApp({ path: "/auth/verify?token=t", session: testUser({ verified: false }) });
    await userEvent.click(await screen.findByRole("button", { name: "Confirm my email" }));
    expect(await screen.findByRole("link", { name: "Go to your account" })).toHaveAttribute("href", "/account");
  });
});

describe("choosing a new password", () => {
  it("sends the token with the new password, and says to sign in", async () => {
    const { sent } = routedFetch({
      "POST /api/auth/password/reset": { status: 200, body: { status: "password_reset" } },
      "GET /api/auth/session": problem(401, "kernel.not_signed_in"),
    });
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

describe("a landing that ends every session", () => {
  for (const landing of [
    { path: "/auth/reset?token=t", api: "/api/auth/password/reset", fill: true, button: "Save password" },
    { path: "/auth/email/undo?token=t", api: "/api/auth/email/undo", fill: false, button: "Put my old email back" },
    { path: "/auth/second-factor/undo?token=t", api: "/api/auth/second-factor/undo", fill: false, button: "Remove it" },
  ]) {
    it(`${landing.path.split("?")[0] ?? ""} shows this browser signed out too, so Sign in opens the form (Codex on #83)`, async () => {
      routedFetch({
        [`POST ${landing.api}`]: { status: 200, body: { status: "done" } },
        "GET /api/auth/session": problem(401, "kernel.not_signed_in"),
      });
      const { router } = renderApp({ path: landing.path, session: testUser() });
      if (landing.fill) await userEvent.type(await screen.findByLabelText("New password"), "copper heron valley");
      await userEvent.click(await screen.findByRole("button", { name: landing.button }));
      await userEvent.click(await screen.findByRole("link", { name: "Sign in" }));
      expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/sign-in");
    });
  }
});

describe("a landing whose session check fails", () => {
  it("offers to check again, and the way to sign in only once it's known (CodeRabbit on #83)", async () => {
    let reads = 0;
    routedFetch({
      "POST /api/auth/password/reset": { status: 200, body: { status: "password_reset" } },
      "GET /api/auth/session": () => {
        reads += 1;
        return reads === 1 ? problem(503, "kernel.busy") : problem(401, "kernel.not_signed_in");
      },
    });
    const { router } = renderApp({ path: "/auth/reset?token=t", session: testUser() });
    await userEvent.type(await screen.findByLabelText("New password"), "copper heron valley");
    await userEvent.click(screen.getByRole("button", { name: "Save password" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Password saved" })).toBeInTheDocument();
    expect(await screen.findByText("This browser's sign-in couldn't be checked just now.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await userEvent.click(await screen.findByRole("link", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/sign-in");
  });

  it("checks again on Try again without sending the confirmation again (CodeRabbit on #83)", async () => {
    let reads = 0;
    const { sent } = routedFetch({
      "POST /api/auth/verify-email": { status: 200, body: { status: "verified" } },
      "GET /api/auth/session": () => {
        reads += 1;
        return reads === 1 ? problem(503, "kernel.busy") : { status: 200, body: { user: testUser({ verified: true }) } };
      },
    });
    const { queryClient } = renderApp({ path: "/auth/verify?token=t", session: testUser({ verified: false }) });
    await userEvent.click(await screen.findByRole("button", { name: "Confirm my email" }));
    expect(await screen.findByText("This browser's sign-in couldn't be checked just now.")).toBeInTheDocument();
    expect(queryClient.getQueryData<SessionUser>(SESSION_KEY)?.verified).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Go to your account" })).toBeInTheDocument();
    expect(queryClient.getQueryData<SessionUser>(SESSION_KEY)?.verified).toBe(true);
    expect(sent.filter((request) => request.method === "POST")).toHaveLength(1);
  });

  it("keeps an account still signed in here when the check finds it", async () => {
    routedFetch({
      "POST /api/auth/email/undo": { status: 200, body: { status: "email_restored" } },
      "GET /api/auth/session": { status: 200, body: { user: testUser({ email: "other@mechframe.test" }) } },
    });
    const { queryClient } = renderApp({ path: "/auth/email/undo?token=t", session: testUser() });
    await userEvent.click(await screen.findByRole("button", { name: "Put my old email back" }));
    await screen.findByRole("heading", { level: 1, name: "Old email back" });
    expect(queryClient.getQueryData<SessionUser>(SESSION_KEY)?.email).toBe("other@mechframe.test");
    expect(screen.queryByText(/couldn't be checked/)).toBeNull();
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
