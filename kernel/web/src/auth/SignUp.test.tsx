import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import { problem, routedFetch } from "../test-fetch";

// The screens load lazily; import them once before the tests, so none waits on a first import.
beforeAll(async () => {
  await Promise.all([import("./SignUp"), import("./ForgotPassword"), import("./SignIn")]);
});

const sentEmail = { status: 202, body: { status: "check_email" } };

async function fill(email: string, password: string) {
  await userEvent.type(await screen.findByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Create account" }));
}

describe("signing up", () => {
  it("sends the email and password, then says a link is on its way", async () => {
    const { sent } = routedFetch({ "POST /api/auth/sign-up": sentEmail });
    renderApp({ path: "/sign-up" });
    expect(await screen.findByRole("heading", { level: 1, name: "Create an account" })).toBeInTheDocument();
    await fill("new@mechframe.test", "copper heron valley");
    expect(await screen.findByRole("heading", { level: 1, name: "Check your email" })).toHaveFocus();
    expect(screen.getByText(/We sent a link to new@mechframe.test/)).toBeInTheDocument();
    expect(await sent[0]?.clone().json()).toEqual({ email: "new@mechframe.test", password: "copper heron valley" });
  });

  it("asks for an address and 12 characters before sending", async () => {
    const { fetch } = routedFetch({});
    renderApp({ path: "/sign-up" });
    await fill("not-an-address", "short");
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter your email address.");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(expect.stringContaining("Use at least 12 characters.") as string);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("puts the server's refusal on the field it's about", async () => {
    const rejected = problem(422, "auth.password_rejected");
    routedFetch({ "POST /api/auth/sign-up": { ...rejected, body: { ...(rejected.body as object), detail: "That password is on a list of breached ones." } } });
    renderApp({ path: "/sign-up" });
    await fill("new@mechframe.test", "copper heron valley");
    await waitFor(() => {
      expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(expect.stringContaining("breached") as string);
    });
  });

  it("says when the site isn't taking accounts, or wants an invite, or the email is no address", async () => {
    for (const [code, words] of [
      ["auth.sign_up_closed", "This site isn't taking new accounts right now."],
      ["auth.invite_required", "This site is invite-only"],
    ] as const) {
      routedFetch({ "POST /api/auth/sign-up": problem(403, code) });
      const { unmount } = renderApp({ path: "/sign-up" });
      await fill("new@mechframe.test", "copper heron valley");
      expect(await screen.findByRole("alert")).toHaveTextContent(words);
      unmount();
    }
    routedFetch({ "POST /api/auth/sign-up": problem(422, "kernel.invalid_request") });
    renderApp({ path: "/sign-up" });
    await fill("a@b", "copper heron valley");
    await waitFor(() => {
      expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter one email address.");
    });
  });

  it("sends someone signed in on, and keeps next on the way back to sign in", async () => {
    const { router, unmount } = renderApp({ path: "/sign-up?next=%2Fblog", session: testUser() });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/blog");
    });
    unmount();
    renderApp({ path: "/sign-up?next=%2Fblog" });
    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in?next=%2Fblog");
  });
});

describe("forgetting the password", () => {
  it("sends the email, says a link may be on its way, and sends again when asked", async () => {
    const { sent } = routedFetch({ "POST /api/auth/password/reset-request": sentEmail });
    renderApp({ path: "/forgot-password" });
    expect(await screen.findByRole("heading", { level: 1, name: "Reset password" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter the email address of your account.");
    await userEvent.type(screen.getByLabelText("Email"), "ann@mechframe.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(/If ann@mechframe.test belongs to an account/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send it again" }));
    expect(await screen.findByText(/another link is on its way/)).toBeInTheDocument();
    expect(sent).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/sign-in");
  });

  it("says when it couldn't send", async () => {
    routedFetch({});
    renderApp({ path: "/forgot-password" });
    await userEvent.type(await screen.findByLabelText("Email"), "ann@mechframe.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Check your connection");
    expect(screen.getByRole("heading", { level: 1, name: "Reset password" })).toBeInTheDocument();
  });
});

describe("the frame", () => {
  it("has the site's name, the way back, its mark when it has one, and no site menus", async () => {
    renderApp({ path: "/sign-in", site: { name: "Vibrant", logo: "/mark.svg" } });
    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    expect(screen.getByRole("link", { name: "Vibrant" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Back to the site" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("contentinfo")).toHaveTextContent(`© ${String(new Date().getFullYear())} Vibrant`);
    expect(screen.queryByRole("navigation", { name: "Site" })).toBeNull();
    expect(document.querySelectorAll("img")).toHaveLength(2);
  });
});
