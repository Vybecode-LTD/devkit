import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithKernel, testUser } from "../../testing";
import { ApiProblem, api } from "../api/client";
import { problem, routedFetch, type Answer } from "../test-fetch";
import { PasskeyCancelled } from "./passkey";
import { refusedQuietly } from "./StepUp";

/** "ok", or what the write threw. */
type Outcome = { value: unknown };

/** A button whose write needs a recent sign-in; the outcome of each press lands in `outcomes`. */
function writer(outcomes: Outcome[]) {
  return (
    <button
      type="button"
      onClick={() => {
        api.POST("/api/auth/totp/setup").then(
          () => outcomes.push({ value: "ok" }),
          (error: unknown) => outcomes.push({ value: error }),
        );
      }}
    >
      Write
    </button>
  );
}

/** The write: refused for a step-up until the session has stepped up. */
function guarded(): { answers: Record<string, Answer | ((request: Request) => Answer)>; steppedUp: () => boolean } {
  let recent = false;
  return {
    steppedUp: () => recent,
    answers: {
      "POST /api/auth/totp/setup": () => (recent ? { status: 200, body: { secret: "S", otpauth_uri: "otpauth://x" } } : problem(403, "auth.step_up_required")),
      "POST /api/auth/step-up": () => {
        recent = true;
        return { status: 200, body: { status: "recent" } };
      },
      "GET /api/auth/security": { status: 200, body: { password: true, totp: null, recovery_codes_left: 0 } },
      "GET /api/auth/passkeys": { status: 200, body: { items: [] } },
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the step-up dialog", () => {
  it("opens on a write refused for a step-up, confirms with the password, and the write goes through", async () => {
    const { answers } = guarded();
    const { sent } = routedFetch(answers);
    const outcomes: Outcome[] = [];
    renderWithKernel(writer(outcomes), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    expect(await screen.findByRole("dialog", { name: "Confirm it's you" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Password"), "quiet orbit lantern");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(outcomes).toEqual([{ value: "ok" }]);
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    const stepUp = sent.find((request) => request.url.endsWith("/api/auth/step-up"));
    expect(await stepUp?.clone().json()).toEqual({ password: "quiet orbit lantern" });
  });

  it("is closed as a no: the write fails with its refusal, which screens say nothing about", async () => {
    routedFetch(guarded().answers);
    const outcomes: Outcome[] = [];
    renderWithKernel(writer(outcomes), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(outcomes).toHaveLength(1);
    });
    expect(outcomes[0]?.value).toBeInstanceOf(ApiProblem);
    expect(refusedQuietly(outcomes[0]?.value)).toBe(true);
    expect(refusedQuietly(new PasskeyCancelled())).toBe(true);
    expect(refusedQuietly(ApiProblem.unreachable())).toBe(false);
  });

  it("says a wrong password and stays open, and asks for one before sending", async () => {
    const { answers } = guarded();
    routedFetch({ ...answers, "POST /api/auth/step-up": problem(401, "auth.invalid_credentials") });
    renderWithKernel(writer([]), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.click(await screen.findByRole("button", { name: "Confirm" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your password.");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("That password isn't right.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Confirm it's you" })).toBeInTheDocument();
  });

  it("closes when the fifth wrong try ends the session", async () => {
    const { answers } = guarded();
    routedFetch({ ...answers, "POST /api/auth/step-up": problem(401, "kernel.not_signed_in"), "GET /api/auth/session": problem(401, "kernel.not_signed_in") });
    const outcomes: Outcome[] = [];
    renderWithKernel(writer(outcomes), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.type(await screen.findByLabelText("Password"), "wrong again");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    await waitFor(() => {
      expect(outcomes).toHaveLength(1);
    });
  });

  it("asks once for writes refused together, and sends each again", async () => {
    routedFetch(guarded().answers);
    const outcomes: Outcome[] = [];
    renderWithKernel(writer(outcomes), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await screen.findByRole("dialog", { name: "Confirm it's you" });
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    await userEvent.type(screen.getByLabelText("Password"), "quiet orbit lantern");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(outcomes).toEqual([{ value: "ok" }, { value: "ok" }]);
    });
  });

  it("takes the app's code instead, and only the code when there's no password", async () => {
    const { answers } = guarded();
    const { sent } = routedFetch({
      ...answers,
      "GET /api/auth/security": { status: 200, body: { password: true, totp: { since: "2026-11-01T00:00:00Z" }, recovery_codes_left: 9 } },
    });
    const outcomes: Outcome[] = [];
    const { unmount } = renderWithKernel(writer(outcomes), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.click(await screen.findByRole("button", { name: "Use your authenticator app instead" }));
    await userEvent.type(screen.getByLabelText("Code from your app"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter the 6 digits your app shows.");
    await userEvent.clear(screen.getByLabelText("Code from your app"));
    await userEvent.type(screen.getByLabelText("Code from your app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(outcomes).toEqual([{ value: "ok" }]);
    });
    expect(await sent.find((request) => request.url.endsWith("/api/auth/step-up"))?.clone().json()).toEqual({ totp: "123456" });
    unmount();

    routedFetch({
      ...guarded().answers,
      "GET /api/auth/security": { status: 200, body: { password: false, totp: { since: "2026-11-01T00:00:00Z" }, recovery_codes_left: 9 } },
    });
    renderWithKernel(writer([]), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    expect(await screen.findByLabelText("Code from your app")).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).toBeNull();
    expect(screen.queryByRole("button", { name: /instead/ })).toBeNull();
  });

  it("takes a passkey, and takes the admin's look over the admin", async () => {
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
        get: () =>
          Promise.resolve(
            new FakeCredential("k", new Uint8Array([1]).buffer, {
              clientDataJSON: new Uint8Array([1]).buffer,
              authenticatorData: new Uint8Array([1]).buffer,
              signature: new Uint8Array([1]).buffer,
              userHandle: null,
            }),
          ),
      },
    });
    const { answers } = guarded();
    const { sent } = routedFetch({
      ...answers,
      "GET /api/auth/passkeys": { status: 200, body: { items: [{ id: "p", name: "Phone", created_at: "2026-11-01T00:00:00Z", last_used_at: null }] } },
      "POST /api/auth/step-up/passkey": { status: 200, body: { challenge: "AQID" } },
    });
    const outcomes: Outcome[] = [];
    renderWithKernel(<div className="mf-admin-look">{writer(outcomes)}</div>, { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.click(await screen.findByRole("button", { name: "Use a passkey" }));
    await waitFor(() => {
      expect(outcomes).toEqual([{ value: "ok" }]);
    });
    expect(await sent.find((request) => request.url.endsWith("/api/auth/step-up"))?.clone().json()).toMatchObject({ passkey: { id: "k" } });
  });

  it("lets a closed dialog's late answer leave the next one alone (CodeRabbit on #83)", async () => {
    routedFetch(guarded().answers);
    const base = globalThis.fetch;
    let release: () => void = () => undefined;
    vi.stubGlobal("fetch", (request: Request) =>
      new URL(request.url).pathname === "/api/auth/step-up"
        ? new Promise<Response>((resolve) => {
            release = () => {
              resolve(new Response(JSON.stringify({ status: "recent" }), { status: 200, headers: { "content-type": "application/json" } }));
            };
          })
        : base(request),
    );
    const outcomes: Outcome[] = [];
    renderWithKernel(writer(outcomes), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.type(await screen.findByLabelText("Password"), "quiet orbit lantern");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" })); // while its confirmation is on its way
    await waitFor(() => {
      expect(outcomes).toHaveLength(1);
    });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    expect(await screen.findByRole("dialog", { name: "Confirm it's you" })).toBeInTheDocument();
    release(); // the first dialog's confirmation lands now
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole("dialog", { name: "Confirm it's you" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(outcomes).toHaveLength(2); // the second write was answered too, not left waiting
    });
  });

  it("says when it can't read the account's ways in, with Try again, and asks for nothing meanwhile (CodeRabbit on #83)", async () => {
    let tries = 0;
    routedFetch({
      ...guarded().answers,
      "GET /api/auth/security": () => {
        tries += 1;
        return tries === 1
          ? problem(500, "kernel.unexpected")
          : { status: 200, body: { password: false, totp: { since: "2026-11-01T00:00:00Z" }, recovery_codes_left: 9 } };
      },
    });
    renderWithKernel(writer([]), { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirm it's you" });
    expect(await within(dialog).findByText("Your ways to confirm it's you couldn't be loaded.")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Password")).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Try again" }));
    expect(await within(dialog).findByLabelText("Code from your app")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Password")).toBeNull();
  });

  it("draws in the frame's look it opened over", async () => {
    routedFetch(guarded().answers);
    renderWithKernel(<div className="mf-admin-look">{writer([])}</div>, { session: testUser() });
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirm it's you" });
    expect(dialog.querySelector(".mf-admin-look")).not.toBeNull();
  });
});
