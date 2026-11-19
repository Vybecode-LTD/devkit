import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";

import { renderApp, testUser } from "../../testing";
import { problem, routedFetch } from "../test-fetch";

// The screens load lazily; import them once before the tests, so none waits on a first import.
beforeAll(async () => {
  await Promise.all([import("./SignIn")]);
});

const user = testUser({ email: "ann@mechframe.test" });
const signedIn = { status: 200, body: { status: "signed_in", user } };
const secondFactor = (methods: string[]) => ({ status: 200, body: { status: "second_factor", challenge: "c-1", methods } });

function at(router: ReturnType<typeof renderApp>["router"]) {
  return router.state.location.pathname + router.state.location.search;
}

async function bodyOf(request: Request | undefined): Promise<unknown> {
  if (!request) throw new Error("Nothing was sent.");
  return (await request.clone().json()) as unknown;
}

async function typePassword(email = "ann@mechframe.test", password = "quiet orbit lantern") {
  await userEvent.type(await screen.findByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("signing in with a password", () => {
  it("sends the email and password, shows the person signed in and goes on to next", async () => {
    const { sent } = routedFetch({ "POST /api/auth/sign-in": signedIn });
    const { router } = renderApp({ path: "/sign-in?next=%2Fblog%3Fsort%3Dnew" });
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    await typePassword(" ann@mechframe.test ");
    await waitFor(() => {
      expect(at(router)).toBe("/blog?sort=new");
    });
    expect(await bodyOf(sent.find((request) => request.url.endsWith("/api/auth/sign-in")))).toEqual({
      email: "ann@mechframe.test",
      password: "quiet orbit lantern",
    });
  });

  it("goes home when next isn't a path on this site", async () => {
    routedFetch({ "POST /api/auth/sign-in": signedIn });
    const { router } = renderApp({ path: "/sign-in?next=%2F%2Fevil.test" });
    await typePassword();
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
  });

  it("says a wrong password and an unknown email the same way, and stays", async () => {
    routedFetch({ "POST /api/auth/sign-in": problem(401, "auth.invalid_credentials") });
    const { router } = renderApp({ path: "/sign-in" });
    await typePassword();
    expect(await screen.findByRole("alert")).toHaveTextContent("That email and password don't match an account here.");
    expect(at(router)).toBe("/sign-in");
  });

  it("says how long to wait when there have been too many tries", async () => {
    const limited = problem(429, "kernel.rate_limited");
    routedFetch({ "POST /api/auth/sign-in": { ...limited, body: { ...(limited.body as object), retry_after: 120 } } });
    renderApp({ path: "/sign-in" });
    await typePassword();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many tries. Wait 2 minutes, then try again.");
  });

  it("asks for what's missing before sending anything", async () => {
    const { fetch } = routedFetch({});
    renderApp({ path: "/sign-in" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter the email address of your account.");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("Enter your password.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends someone already signed in on to next", async () => {
    const { router } = renderApp({ path: "/sign-in?next=%2Fblog", session: user });
    await waitFor(() => {
      expect(at(router)).toBe("/blog");
    });
  });

  it("keeps next on the way to signing up", async () => {
    renderApp({ path: "/sign-in?next=%2Fblog" });
    expect(await screen.findByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/sign-up?next=%2Fblog");
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("the second step", () => {
  it("takes the app's code, then signs in", async () => {
    const { sent } = routedFetch({
      "POST /api/auth/sign-in": secondFactor(["totp", "recovery_code"]),
      "POST /api/auth/sign-in/second-factor": signedIn,
    });
    const { router } = renderApp({ path: "/sign-in?next=%2Fblog" });
    await typePassword();
    const heading = await screen.findByRole("heading", { level: 1, name: "One more step" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(screen.getByText(/Enter the code from your authenticator app/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code from your app"), "123 456"); // as an app shows it (CodeRabbit on #83)
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => {
      expect(at(router)).toBe("/blog");
    });
    expect(await bodyOf(sent.find((request) => request.url.endsWith("/second-factor")))).toEqual({ challenge: "c-1", totp: "123456" });
  });

  it("takes a recovery code when the app isn't to hand", async () => {
    const { sent } = routedFetch({
      "POST /api/auth/sign-in": secondFactor(["totp", "recovery_code"]),
      "POST /api/auth/sign-in/second-factor": signedIn,
    });
    const { router } = renderApp({ path: "/sign-in" });
    await typePassword();
    await userEvent.click(await screen.findByText("Can't use either?"));
    await userEvent.type(screen.getByLabelText("Recovery code"), " abcd-efgh ");
    await userEvent.click(screen.getByRole("button", { name: "Use recovery code" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(await bodyOf(sent.find((request) => request.url.endsWith("/second-factor")))).toEqual({ challenge: "c-1", recovery_code: "abcd-efgh" });
  });

  it("says a wrong code, and starts again once the challenge has ended", async () => {
    let tries = 0;
    routedFetch({
      "POST /api/auth/sign-in": secondFactor(["totp"]),
      "POST /api/auth/sign-in/second-factor": () => {
        tries += 1;
        return tries === 1 ? problem(401, "auth.invalid_second_factor") : problem(401, "auth.challenge_ended");
      },
    });
    renderApp({ path: "/sign-in" });
    await typePassword();
    await userEvent.type(await screen.findByLabelText("Code from your app"), "111111");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That didn't match.");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("That sign-in ran out, or had too many tries. Start again.");
  });

  it("asks for the six digits before sending", async () => {
    const { sent } = routedFetch({ "POST /api/auth/sign-in": secondFactor(["totp"]) });
    renderApp({ path: "/sign-in" });
    await typePassword();
    await userEvent.type(await screen.findByLabelText("Code from your app"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter the 6 digits your app shows.");
    expect(sent.filter((request) => request.url.endsWith("/second-factor"))).toHaveLength(0);
  });

  it("says so, and goes back, when this browser can't use the account's only second factor (CodeRabbit on #83)", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    routedFetch({ "POST /api/auth/sign-in": secondFactor(["passkey"]) });
    renderApp({ path: "/sign-in" });
    await typePassword();
    expect(await screen.findByText(/second step is a passkey, and this browser can't use one/)).toBeInTheDocument();
    expect(screen.queryByText(/recovery codes/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers only a recovery code to an account with nothing else", async () => {
    routedFetch({ "POST /api/auth/sign-in": secondFactor(["recovery_code"]) });
    renderApp({ path: "/sign-in" });
    await typePassword();
    expect(await screen.findByLabelText("Recovery code")).toBeVisible();
    expect(screen.queryByText("Can't use either?")).toBeNull();
    expect(screen.getByText(/Use one of your recovery codes/)).toBeInTheDocument();
  });
});

describe("signing in with an emailed code", () => {
  it("sends a code to the email typed, then signs in with it", async () => {
    const { sent } = routedFetch({
      "POST /api/auth/code": { status: 202, body: { status: "check_email" } },
      "POST /api/auth/code/verify": signedIn,
    });
    const { router } = renderApp({ path: "/sign-in" });
    await userEvent.type(await screen.findByLabelText("Email"), "ann@mechframe.test");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code instead" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText(/We sent a 6-digit code to ann@mechframe.test/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code"), "654321");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(await bodyOf(sent.find((request) => request.url.endsWith("/code/verify")))).toEqual({ email: "ann@mechframe.test", code: "654321" });
  });

  it("asks for the email first, says a wrong code, and goes back to sign in", async () => {
    routedFetch({
      "POST /api/auth/code": { status: 202, body: { status: "check_email" } },
      "POST /api/auth/code/verify": problem(401, "auth.invalid_code"),
    });
    renderApp({ path: "/sign-in" });
    await userEvent.click(await screen.findByRole("button", { name: "Email me a code instead" }));
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter the email address of your account.");
    await userEvent.type(screen.getByLabelText("Email"), "ann@mechframe.test");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code instead" }));
    await userEvent.type(await screen.findByLabelText("Code"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter the 6 digits from the email.");
    await userEvent.clear(screen.getByLabelText("Code"));
    await userEvent.type(screen.getByLabelText("Code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is wrong, or it's run out.");
    await userEvent.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });

  it("takes a code typed with a space, and holds Back while it's checked (CodeRabbit on #83)", async () => {
    let answer: (value: Response) => void = () => undefined;
    const { sent } = routedFetch({ "POST /api/auth/code": { status: 202, body: { status: "check_email" } } });
    const fetch = globalThis.fetch;
    vi.stubGlobal("fetch", (request: Request) =>
      new URL(request.url).pathname === "/api/auth/code/verify"
        ? (sent.push(request), new Promise<Response>((resolve) => (answer = resolve)))
        : fetch(request),
    );
    renderApp({ path: "/sign-in" });
    await userEvent.type(await screen.findByLabelText("Email"), "ann@mechframe.test");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code instead" }));
    await userEvent.type(await screen.findByLabelText("Code"), "123 456");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Back to sign in" })).toBeDisabled();
    });
    expect(await sent.at(-1)?.clone().json()).toEqual({ email: "ann@mechframe.test", code: "123456" });
    answer(new Response(JSON.stringify({ code: "auth.invalid_code", status: 401, title: "No", detail: "No.", type: "x" }), { status: 401, headers: { "content-type": "application/problem+json" } }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Back to sign in" })).toBeEnabled();
    });
  });

  it("goes on to the second step when the account has one", async () => {
    routedFetch({
      "POST /api/auth/code": { status: 202, body: { status: "check_email" } },
      "POST /api/auth/code/verify": secondFactor(["totp"]),
    });
    renderApp({ path: "/sign-in" });
    await userEvent.type(await screen.findByLabelText("Email"), "ann@mechframe.test");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code instead" }));
    await userEvent.type(await screen.findByLabelText("Code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "One more step" })).toBeInTheDocument();
  });
});

class FakeCredential {
  constructor(
    readonly id: string,
    readonly rawId: ArrayBuffer,
    readonly response: object,
  ) {}
}

function withPasskeys(get: () => Promise<unknown>) {
  vi.stubGlobal("PublicKeyCredential", FakeCredential);
  vi.stubGlobal("navigator", { credentials: { get } });
}

const assertion = () =>
  Promise.resolve(
    new FakeCredential("k-1", new Uint8Array([1]).buffer, {
      clientDataJSON: new Uint8Array([2]).buffer,
      authenticatorData: new Uint8Array([3]).buffer,
      signature: new Uint8Array([4]).buffer,
      userHandle: null,
    }),
  );

describe("signing in with a passkey", () => {
  it("is hidden where the browser can't use one", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    renderApp({ path: "/sign-in" });
    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    expect(screen.queryByRole("button", { name: "Sign in with a passkey" })).toBeNull();
  });

  it("asks the browser with the server's options and signs in with its answer", async () => {
    withPasskeys(assertion);
    const { sent } = routedFetch({
      "POST /api/auth/passkeys/sign-in/start": { status: 200, body: { challenge: "AQID", userVerification: "required" } },
      "POST /api/auth/passkeys/sign-in/finish": signedIn,
    });
    const { router } = renderApp({ path: "/sign-in?next=%2Fblog" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in with a passkey" }));
    await waitFor(() => {
      expect(at(router)).toBe("/blog");
    });
    expect(await bodyOf(sent.find((request) => request.url.endsWith("/finish")))).toMatchObject({ id: "k-1", rawId: "AQ", type: "public-key" });
  });

  it("says nothing when the person closes the browser's prompt, and says a passkey the site doesn't know", async () => {
    let closed = true;
    withPasskeys(() => (closed ? Promise.reject(new DOMException("Closed", "NotAllowedError")) : assertion()));
    routedFetch({
      "POST /api/auth/passkeys/sign-in/start": { status: 200, body: { challenge: "AQID" } },
      "POST /api/auth/passkeys/sign-in/finish": problem(401, "auth.invalid_passkey"),
    });
    renderApp({ path: "/sign-in" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in with a passkey" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sign in with a passkey" })).toBeEnabled();
    });
    expect(screen.queryByRole("alert")).toBeNull();
    closed = false;
    await userEvent.click(screen.getByRole("button", { name: "Sign in with a passkey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That passkey isn't one this site knows.");
  });

  it("is the second step too", async () => {
    withPasskeys(assertion);
    const { sent } = routedFetch({
      "POST /api/auth/sign-in": secondFactor(["totp", "passkey", "recovery_code"]),
      "POST /api/auth/sign-in/second-factor/passkey": { status: 200, body: { challenge: "BAU" } },
      "POST /api/auth/sign-in/second-factor": signedIn,
    });
    const { router } = renderApp({ path: "/sign-in" });
    await typePassword();
    expect(await screen.findByText(/Use your passkey, or the code from your authenticator app/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use a passkey" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    const finish = sent.filter((request) => request.url.endsWith("/sign-in/second-factor")).at(-1);
    expect(await bodyOf(finish)).toMatchObject({ challenge: "c-1", passkey: { id: "k-1" } });
  });

  it("says when the browser couldn't use one at all", async () => {
    withPasskeys(() => Promise.reject(new DOMException("No", "SecurityError")));
    routedFetch({ "POST /api/auth/passkeys/sign-in/start": { status: 200, body: { challenge: "AQID" } } });
    renderApp({ path: "/sign-in" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in with a passkey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your browser couldn't use a passkey here.");
  });
});
