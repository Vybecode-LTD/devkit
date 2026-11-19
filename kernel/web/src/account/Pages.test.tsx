import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { renderApp, testUser } from "../../testing";
import { problem, routedFetch } from "../test-fetch";
import { DONE } from "./Activity";

// The screens load lazily; import them once before the tests, so none waits on a first import.
beforeAll(async () => {
  await Promise.all([import("./Notifications"), import("./Activity")]);
});

const me = testUser();

describe("the notifications page", () => {
  it("switches each notice on the site and by email, saving at once", async () => {
    const { sent } = routedFetch({
      "GET /api/kernel/notifications/preferences": {
        status: 200,
        body: { items: [{ key: "blog.reply", description: "Replies to your comments", default: "both", in_site: true, email: true }] },
      },
      "PUT /api/kernel/notifications/preferences": {
        status: 200,
        body: { items: [{ key: "blog.reply", description: "Replies to your comments", default: "both", in_site: true, email: false }] },
      },
    });
    renderApp({ path: "/account/notifications", session: me });
    expect(await screen.findByRole("heading", { level: 1, name: "Notifications" })).toBeInTheDocument();
    const notice = await screen.findByRole("group", { name: "Replies to your comments" });
    const email = within(notice).getByRole("switch", { name: "By email" });
    expect(email).toHaveAttribute("aria-checked", "true");
    await userEvent.click(email);
    await waitFor(() => {
      expect(within(notice).getByRole("switch", { name: "By email" })).toHaveAttribute("aria-checked", "false");
    });
    expect(await sent.find((request) => request.method === "PUT")?.clone().json()).toEqual({ "blog.reply": { in_site: true, email: false } });
  });

  it("keeps a saved switch when an older read lands after the save (CodeRabbit on #83)", async () => {
    const item = (email: boolean) => ({ key: "blog.reply", description: "Replies to your comments", default: "both", in_site: true, email });
    let reads = 0;
    let lateRead: () => void = () => undefined;
    routedFetch({ "PUT /api/kernel/notifications/preferences": { status: 200, body: { items: [item(false)] } } });
    const base = globalThis.fetch;
    vi.stubGlobal("fetch", (request: Request) => {
      if (request.method !== "GET" || new URL(request.url).pathname !== "/api/kernel/notifications/preferences") return base(request);
      reads += 1;
      const answer = new Response(JSON.stringify({ items: [item(true)] }), { status: 200, headers: { "content-type": "application/json" } });
      if (reads === 1) return Promise.resolve(answer);
      return new Promise<Response>((resolve) => {
        lateRead = () => {
          resolve(answer);
        };
      });
    });
    const { queryClient } = renderApp({ path: "/account/notifications", session: me });
    const notice = await screen.findByRole("group", { name: "Replies to your comments" });
    void queryClient.refetchQueries({ queryKey: ["get", "/api/kernel/notifications/preferences"] }); // a read on its way, from before the save
    await userEvent.click(within(notice).getByRole("switch", { name: "By email" }));
    await waitFor(() => {
      expect(within(notice).getByRole("switch", { name: "By email" })).toHaveAttribute("aria-checked", "false");
    });
    lateRead();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(notice).getByRole("switch", { name: "By email" })).toHaveAttribute("aria-checked", "false");
  });

  it("says when nothing sends notices, and when the settings didn't load", async () => {
    routedFetch({ "GET /api/kernel/notifications/preferences": { status: 200, body: { items: [] } } });
    const { unmount } = renderApp({ path: "/account/notifications", session: me });
    expect(await screen.findByText("Nothing to switch yet")).toBeInTheDocument();
    unmount();
    routedFetch({ "GET /api/kernel/notifications/preferences": problem(500, "kernel.unexpected") });
    renderApp({ path: "/account/notifications", session: me });
    expect(await screen.findByText("Your notification settings couldn't be loaded.")).toBeInTheDocument();
  });
});

describe("the activity page", () => {
  it("says what happened, newest first, and shows older entries when asked", async () => {
    const { sent } = routedFetch({
      "GET /api/auth/activity": (request) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        const entry = (id: number, action: string, result: string, by_you: boolean) => ({
          id,
          at: "2026-11-18T21:40:00Z",
          action,
          result,
          by_you,
          target: null,
          ip: "203.0.113.9",
          user_agent: "",
          details: {},
        });
        return cursor
          ? { status: 200, body: { items: [entry(1, "auth.sign_up", "success", true)], next_cursor: null } }
          : { status: 200, body: { items: [entry(3, "auth.sign_in", "failure", true), entry(2, "auth.user.suspended", "success", false)], next_cursor: "c-2" } };
      },
    });
    renderApp({ path: "/account/activity", session: me });
    expect(await screen.findByText("Signed in (didn't go through)")).toBeInTheDocument();
    expect(screen.getByText("The account was suspended").parentElement).toHaveTextContent("by someone else, from 203.0.113.9");
    await userEvent.click(screen.getByRole("button", { name: "Show older" }));
    expect(await screen.findByText("Created the account")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show older" })).toBeNull();
    expect(new URL(sent.at(-1)?.url ?? "").searchParams.get("cursor")).toBe("c-2");
  });

  it("names every action the kernel writes about a person", () => {
    expect(DONE["auth.passkey_added"]).toBe("Added a passkey");
    expect(Object.keys(DONE).every((action) => action.startsWith("auth."))).toBe(true);
  });

  it("says when there's nothing yet, and when it didn't load", async () => {
    routedFetch({ "GET /api/auth/activity": { status: 200, body: { items: [], next_cursor: null } } });
    const { unmount } = renderApp({ path: "/account/activity", session: me });
    expect(await screen.findByText("Nothing yet")).toBeInTheDocument();
    unmount();
    routedFetch({});
    renderApp({ path: "/account/activity", session: me });
    expect(await screen.findByText("Your activity couldn't be loaded.")).toBeInTheDocument();
  });
});
