import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";

import { renderApp, testUser } from "../../testing";
import { defineModule } from "../modules";
import { problem, routedFetch, type Answer } from "../test-fetch";

// The screens load lazily; import them once before the tests, so none waits on a first import.
beforeAll(async () => {
  await Promise.all([import("./Account")]);
});

const DAY = "2026-11-01T12:00:00Z";
const me = testUser({ email: "ann@mechframe.test" });
const security = (over: object = {}) => ({ status: 200, body: { password: true, totp: null, recovery_codes_left: 0, ...over } });
const passkeys = (...names: string[]) => ({
  status: 200,
  body: { items: names.map((name, at) => ({ id: `p-${String(at)}`, name, created_at: DAY, last_used_at: at === 0 ? null : DAY })) },
});
const devices = {
  status: 200,
  body: {
    items: [
      { id: "s-1", device_label: "Chrome on Windows", location: "Boston, US", started_at: DAY, last_seen_at: DAY, current: true },
      { id: "s-2", device_label: "Safari on iPhone", location: null, started_at: DAY, last_seen_at: DAY, current: false },
    ],
  },
};
const ok204: Answer = { status: 204 };

function page(answers: Record<string, Answer | ((request: Request) => Answer)> = {}) {
  return routedFetch({
    "GET /api/auth/security": security(),
    "GET /api/auth/passkeys": passkeys(),
    "GET /api/auth/sessions": devices,
    ...answers,
  });
}

async function card(name: string): Promise<HTMLElement> {
  return screen.findByRole("region", { name });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the account page", () => {
  it("says who's signed in, links the account's pages and shows each card", async () => {
    page();
    renderApp({ path: "/account", session: me });
    expect(await screen.findByRole("heading", { level: 1, name: "Sign-in and security" })).toBeInTheDocument();
    expect(screen.getByText("Signed in as ann@mechframe.test")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Your account" });
    expect(within(nav).getByRole("link", { name: "Sign-in and security" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Activity" })).toHaveAttribute("href", "/account/activity");
    for (const name of ["Passkeys", "Authenticator app", "Password", "Email", "Signed-in devices"]) {
      expect(await card(name)).toBeInTheDocument();
    }
    expect(screen.queryByText("Add a second factor to open the admin")).toBeNull();
  });

  it("tells staff sent here from the admin why", async () => {
    page();
    renderApp({ path: "/account?needs=second-factor", session: { ...me, roles: ["member", "admin"] } });
    expect(await screen.findByText("Add a second factor to open the admin")).toBeInTheDocument();
  });

  it("shows each module's section in a card of its own", async () => {
    page();
    const shop = defineModule({
      id: "shop",
      routes: { public: [], member: [], admin: [] },
      slots: { "account.section": [{ id: "orders", title: "Your orders", lazy: () => Promise.resolve({ default: () => <p>No orders yet.</p> }) }] },
    });
    renderApp({ path: "/account", session: me, modules: [shop] });
    expect(await within(await card("Your orders")).findByText("No orders yet.")).toBeInTheDocument();
  });
});

describe("passkeys", () => {
  it("lists them with when they were added and used", async () => {
    page({ "GET /api/auth/passkeys": passkeys("Laptop", "Phone") });
    renderApp({ path: "/account", session: me });
    const list = within(await card("Passkeys"));
    expect(await list.findByText("Laptop")).toBeInTheDocument();
    expect(list.getByText(/never used/)).toBeInTheDocument();
    expect(list.getByText(/last used/)).toBeInTheDocument();
    expect(list.getByRole("button", { name: "Rename Phone" })).toBeInTheDocument();
  });

  it("are renamed, and removed after asking", async () => {
    const { sent } = page({
      "GET /api/auth/passkeys": passkeys("Laptop"),
      "PATCH /api/auth/passkeys/p-0": { status: 200, body: { id: "p-0", name: "Work laptop", created_at: DAY, last_used_at: null } },
      "DELETE /api/auth/passkeys/p-0": ok204,
    });
    renderApp({ path: "/account", session: me });
    await userEvent.click(await screen.findByRole("button", { name: "Rename Laptop" }));
    const naming = await screen.findByRole("dialog", { name: "Rename the passkey" });
    await userEvent.clear(within(naming).getByLabelText("Name"));
    await userEvent.click(within(naming).getByRole("button", { name: "Save" }));
    expect(within(naming).getByLabelText("Name")).toHaveAccessibleDescription(expect.stringContaining("1 to 80 characters") as string);
    await userEvent.type(within(naming).getByLabelText("Name"), "Work laptop");
    await userEvent.click(within(naming).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(await sent.find((request) => request.method === "PATCH")?.clone().json()).toEqual({ name: "Work laptop" });
    await userEvent.click(screen.getByRole("button", { name: "Remove Laptop" }));
    const asking = await screen.findByRole("dialog", { name: "Remove Laptop?" });
    expect(asking).toHaveTextContent("Every other device signed in to your account will be signed out.");
    await userEvent.click(within(asking).getByRole("button", { name: "Remove passkey" }));
    await waitFor(() => {
      expect(sent.some((request) => request.method === "DELETE")).toBe(true);
    });
    expect(await screen.findByText("Passkey removed. Every other device is signed out.")).toBeInTheDocument();
  });

  it("are added through the browser, named after this device", async () => {
    class FakeCredential {
      constructor(
        readonly id: string,
        readonly rawId: ArrayBuffer,
        readonly response: object,
      ) {}
    }
    vi.stubGlobal("PublicKeyCredential", FakeCredential);
    vi.stubGlobal("navigator", {
      credentials: {
        create: () =>
          Promise.resolve(new FakeCredential("n", new Uint8Array([1]).buffer, { clientDataJSON: new Uint8Array([1]).buffer, attestationObject: new Uint8Array([2]).buffer })),
      },
    });
    const { sent } = page({
      "POST /api/auth/passkeys/register/start": {
        status: 200,
        body: { rp: { name: "S" }, user: { id: "AQ", name: "a", displayName: "a" }, challenge: "AQID", pubKeyCredParams: [{ type: "public-key", alg: -7 }] },
      },
      "POST /api/auth/passkeys/register/finish": { status: 201, body: { id: "p-9", name: "Chrome on Windows", created_at: DAY, last_used_at: null } },
    });
    renderApp({ path: "/account", session: me });
    await waitFor(() => {
      expect(sent.some((request) => request.url.endsWith("/api/auth/sessions"))).toBe(true);
    });
    await userEvent.click(await screen.findByRole("button", { name: "Add a passkey" }));
    const adding = await screen.findByRole("dialog", { name: "Add a passkey" });
    await waitFor(() => {
      expect(within(adding).getByLabelText("Name")).toHaveValue("Chrome on Windows");
    });
    await userEvent.click(within(adding).getByRole("button", { name: "Add passkey" }));
    expect(await screen.findByText(/Passkey added/)).toBeInTheDocument();
    expect(await sent.find((request) => request.url.endsWith("/register/start"))?.clone().json()).toEqual({ name: "Chrome on Windows" });
    expect(await sent.find((request) => request.url.endsWith("/register/finish"))?.clone().json()).toMatchObject({ id: "n", response: { attestationObject: "Ag" } });
  });

  it("say why one couldn't be added, in the dialog", async () => {
    vi.stubGlobal("PublicKeyCredential", vi.fn());
    vi.stubGlobal("navigator", { credentials: {} });
    page({ "POST /api/auth/passkeys/register/start": problem(403, "auth.email_unverified") });
    renderApp({ path: "/account", session: me });
    await userEvent.click(await screen.findByRole("button", { name: "Add a passkey" }));
    const adding = await screen.findByRole("dialog", { name: "Add a passkey" });
    await userEvent.click(within(adding).getByRole("button", { name: "Add passkey" }));
    expect(await within(adding).findByRole("alert")).toHaveTextContent("Confirm your email first");
  });

  it("can't be added in a browser without them", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    page();
    renderApp({ path: "/account", session: me });
    expect(await within(await card("Passkeys")).findByText("This browser can't make one.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add a passkey" })).toBeNull();
  });
});

describe("the authenticator app", () => {
  it("is set up with its key and a code, then shows the recovery codes once", async () => {
    const { sent } = page({
      "POST /api/auth/totp/setup": { status: 200, body: { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/Site:ann?secret=JBSWY3DPEHPK3PXP" } },
      "POST /api/auth/totp/confirm": { status: 200, body: { recovery_codes: ["aaaa-bbbb", "cccc-dddd"] } },
    });
    renderApp({ path: "/account", session: me });
    await userEvent.click(await within(await card("Authenticator app")).findByRole("button", { name: "Set up" }));
    const setting = await screen.findByRole("dialog", { name: "Set up an authenticator app" });
    expect(await within(setting).findByText("JBSW Y3DP EHPK 3PXP")).toBeInTheDocument();
    expect(within(setting).getByRole("link", { name: "Open in your authenticator app" })).toHaveAttribute("href", expect.stringMatching(/^otpauth:/) as string);
    await userEvent.type(within(setting).getByLabelText("Code from your app"), "12");
    await userEvent.click(within(setting).getByRole("button", { name: "Turn it on" }));
    expect(within(setting).getByRole("alert")).toHaveTextContent("Enter the 6 digits");
    await userEvent.clear(within(setting).getByLabelText("Code from your app"));
    await userEvent.type(within(setting).getByLabelText("Code from your app"), "123456");
    await userEvent.click(within(setting).getByRole("button", { name: "Turn it on" }));
    const saved = await screen.findByRole("dialog", { name: "Save your recovery codes" });
    expect(within(saved).getByRole("list", { name: "Your recovery codes" })).toHaveTextContent("aaaa-bbbb");
    await userEvent.click(within(saved).getByRole("button", { name: "I've saved them" }));
    expect(sent.filter((request) => request.url.endsWith("/totp/setup"))).toHaveLength(1);
    expect(await sent.find((request) => request.url.endsWith("/totp/confirm"))?.clone().json()).toEqual({ code: "123456" });
  });

  it("says a wrong code, and says why setup was refused", async () => {
    page({
      "POST /api/auth/totp/setup": { status: 200, body: { secret: "S", otpauth_uri: "otpauth://x" } },
      "POST /api/auth/totp/confirm": problem(401, "auth.invalid_second_factor"),
    });
    const { unmount } = renderApp({ path: "/account", session: me });
    await userEvent.click(await within(await card("Authenticator app")).findByRole("button", { name: "Set up" }));
    const setting = await screen.findByRole("dialog", { name: "Set up an authenticator app" });
    await userEvent.type(await within(setting).findByLabelText("Code from your app"), "123456");
    await userEvent.click(within(setting).getByRole("button", { name: "Turn it on" }));
    expect(await within(setting).findByRole("alert")).toHaveTextContent("That code didn't match.");
    unmount();
    page({ "POST /api/auth/totp/setup": problem(403, "auth.email_unverified") });
    renderApp({ path: "/account", session: me });
    await userEvent.click(await within(await card("Authenticator app")).findByRole("button", { name: "Set up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Confirm your email first");
  });

  it("when on, shows since when and the codes left, makes new codes and is removed after asking", async () => {
    const { sent } = page({
      "GET /api/auth/security": security({ totp: { since: DAY }, recovery_codes_left: 7 }),
      "POST /api/auth/recovery-codes": { status: 200, body: { recovery_codes: ["eeee-ffff"] } },
      "DELETE /api/auth/totp": ok204,
    });
    renderApp({ path: "/account", session: me });
    const app = await card("Authenticator app");
    expect(await within(app).findByText("On")).toBeInTheDocument();
    expect(within(app).getByText(/7 of 10 left/)).toBeInTheDocument();
    await userEvent.click(within(app).getByRole("button", { name: "Make new codes" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Make new recovery codes?" })).getByRole("button", { name: "Make new codes" }));
    const shown = await screen.findByRole("dialog", { name: "Save your new recovery codes" });
    expect(shown).toHaveTextContent("eeee-ffff");
    await userEvent.click(within(shown).getByRole("button", { name: "I've saved them" }));
    await userEvent.click(within(app).getByRole("button", { name: "Remove the authenticator app" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Remove your authenticator app?" })).getByRole("button", { name: "Remove app" }));
    await waitFor(() => {
      expect(sent.some((request) => request.method === "DELETE" && request.url.endsWith("/api/auth/totp"))).toBe(true);
    });
  });
});

describe("the password", () => {
  it("is changed with the current one, each refusal on its field", async () => {
    let tries = 0;
    const { sent } = page({
      "POST /api/auth/password/change": () => {
        tries += 1;
        if (tries === 1) return problem(401, "auth.invalid_credentials");
        if (tries === 2) return problem(422, "auth.password_rejected");
        return { status: 200, body: { status: "password_changed" } };
      },
    });
    renderApp({ path: "/account", session: me });
    await userEvent.click(await within(await card("Password")).findByRole("button", { name: "Change password" }));
    const changing = await screen.findByRole("dialog", { name: "Change your password" });
    await userEvent.click(within(changing).getByRole("button", { name: "Change password" }));
    expect(within(changing).getByLabelText("Current password")).toHaveAccessibleDescription("Enter your current password.");
    await userEvent.type(within(changing).getByLabelText("Current password"), "old one");
    await userEvent.type(within(changing).getByLabelText("New password"), "copper heron valley");
    await userEvent.click(within(changing).getByRole("button", { name: "Change password" }));
    await waitFor(() => {
      expect(within(changing).getByLabelText("Current password")).toHaveAccessibleDescription("That isn't your current password.");
    });
    await userEvent.click(within(changing).getByRole("button", { name: "Change password" }));
    await waitFor(() => {
      expect(within(changing).getByLabelText("New password")).toHaveAccessibleDescription(expect.stringContaining("Refused.") as string);
    });
    await userEvent.click(within(changing).getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("Password changed. Every other device is signed out.")).toBeInTheDocument();
    expect(await sent.find((request) => request.url.endsWith("/password/change"))?.clone().json()).toEqual({
      current_password: "old one",
      new_password: "copper heron valley",
    });
  });

  it("is set by a reset link when the account has none", async () => {
    page({ "GET /api/auth/security": security({ password: false }) });
    renderApp({ path: "/account", session: me });
    expect(await within(await card("Password")).findByRole("link", { name: "Set a password" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("the email", () => {
  it("is changed by a link to the new address", async () => {
    const { sent } = page({ "POST /api/auth/email/change": { status: 202, body: { status: "check_email" } } });
    renderApp({ path: "/account", session: me });
    const email = await card("Email");
    expect(within(email).getByText("ann@mechframe.test")).toBeInTheDocument();
    expect(within(email).getByText("Confirmed")).toBeInTheDocument();
    await userEvent.click(within(email).getByRole("button", { name: "Change email" }));
    const changing = await screen.findByRole("dialog", { name: "Change your email" });
    await userEvent.type(within(changing).getByLabelText("New email"), "ANN@mechframe.test");
    await userEvent.click(within(changing).getByRole("button", { name: "Send link" }));
    expect(within(changing).getByRole("alert")).toHaveTextContent("other than the one you have");
    await userEvent.clear(within(changing).getByLabelText("New email"));
    await userEvent.type(within(changing).getByLabelText("New email"), "new@mechframe.test");
    await userEvent.click(within(changing).getByRole("button", { name: "Send link" }));
    expect(await screen.findByRole("dialog", { name: "Check your new address" })).toHaveTextContent("We sent a link to new@mechframe.test.");
    expect(await sent.find((request) => request.url.endsWith("/email/change"))?.clone().json()).toEqual({ email: "new@mechframe.test" });
  });

  it("not yet confirmed, can ask for a new link", async () => {
    const { sent } = page({ "POST /api/auth/verify-email/resend": { status: 202, body: { status: "check_email" } } });
    renderApp({ path: "/account", session: { ...me, verified: false } });
    const email = await card("Email");
    expect(within(email).getByText(/Not confirmed yet/)).toBeInTheDocument();
    await userEvent.click(within(email).getByRole("button", { name: "Send a new link" }));
    expect(await screen.findByText(/A new link is on its way/)).toBeInTheDocument();
    expect(sent.some((request) => request.url.endsWith("/verify-email/resend"))).toBe(true);
  });
});

describe("the signed-in devices", () => {
  it("show this one first with its place, and each other with when it was last seen", async () => {
    page();
    renderApp({ path: "/account", session: me });
    const list = within(await card("Signed-in devices"));
    expect(await list.findByText("This device")).toBeInTheDocument();
    expect(list.getByText("Chrome on Windows, Boston, US")).toBeInTheDocument();
    expect(list.getByText("Now")).toBeInTheDocument();
    expect(list.getByText("Safari on iPhone")).toBeInTheDocument();
    expect(list.getByText(/Last active/)).toBeInTheDocument();
  });

  it("sign one out, or every other", async () => {
    const { sent } = page({ "DELETE /api/auth/sessions/s-2": ok204, "POST /api/auth/sessions/sign-out-others": ok204 });
    renderApp({ path: "/account", session: me });
    await userEvent.click(await screen.findByRole("button", { name: "Sign out Safari on iPhone" }));
    expect(await screen.findByText("Safari on iPhone is signed out.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere else" }));
    expect(await screen.findByText("Every other device is signed out.")).toBeInTheDocument();
    expect(sent.filter((request) => request.method !== "GET").map((request) => new URL(request.url).pathname)).toEqual([
      "/api/auth/sessions/s-2",
      "/api/auth/sessions/sign-out-others",
    ]);
  });

  it("say a refusal as a note", async () => {
    page({ "DELETE /api/auth/sessions/s-2": problem(404, "auth.session_not_found") });
    renderApp({ path: "/account", session: me });
    await userEvent.click(await screen.findByRole("button", { name: "Sign out Safari on iPhone" }));
    expect(await screen.findByText("That device was signed out already.")).toBeInTheDocument();
  });
});
