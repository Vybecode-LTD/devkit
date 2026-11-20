// useSettings (K4.8): a settings section as an admin form edits it — only
// what changed is sent, at the version read; a conflict resolves with the
// person's choices; a refused field says so beside itself.
import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithKernel, testUser } from "../../testing";
import { problem, routedFetch, type Answer } from "../test-fetch";
import { useSettings, type SettingsForm } from "./useSettings";

const admin = testUser({ roles: ["member", "admin"], second_factor: true, permissions: ["kernel.settings.manage"] });
const SECTION = "/api/kernel/admin/settings/blog";

function shown(fetched: Record<string, Answer | ((request: Request) => Answer)>) {
  const net = routedFetch(fetched);
  const held: { form?: SettingsForm } = {};
  function Probe() {
    held.form = useSettings("blog");
    return null;
  }
  const { queryClient } = renderWithKernel(<Probe />, { session: admin });
  const form = () => {
    if (!held.form) throw new Error("not drawn");
    return held.form;
  };
  return { ...net, form, queryClient };
}

const read = (version: number, values: Record<string, unknown>): Answer => ({ status: 200, body: { version, values } });

/** Holds the first `method` request open until the returned function is called. */
function gated(fetch: ReturnType<typeof routedFetch>["fetch"], method: string): () => void {
  let open: () => void = () => undefined;
  const opened = new Promise<void>((resolve) => {
    open = resolve;
  });
  const original = fetch.getMockImplementation();
  if (!original) throw new Error("no fetch to hold");
  let held = false;
  fetch.mockImplementation((request: Request) => {
    if (request.method !== method || held) return original(request);
    held = true;
    return opened.then(() => original(request));
  });
  return open;
}


const bodies = async (sent: Request[], method: string) =>
  Promise.all(sent.filter((request) => request.method === method && new URL(request.url).pathname === SECTION).map((request) => request.clone().json()));

describe("useSettings", () => {
  it("counts as changed only what differs from what's saved", async () => {
    const { form } = shown({ [`GET ${SECTION}`]: read(2, { title: "News", per_page: 10 }) });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("title", "News");
    });
    expect(form().dirty).toBe(false);
    act(() => {
      form().set("per_page", 12);
    });
    expect(form().changes).toEqual({ per_page: 12 });
    expect(form().values).toEqual({ title: "News", per_page: 12 });
  });

  it("sends only the changes at the version read, then reads the section again", async () => {
    let version = 2;
    const { form, sent } = shown({
      [`GET ${SECTION}`]: () => read(version, { title: version === 2 ? "News" : "Notes" }),
      [`PUT ${SECTION}`]: () => {
        version = 3;
        return { status: 200, body: { version: 3, changed: ["title"], merged: [] } };
      },
    });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("title", "Notes");
    });
    let outcome;
    await act(async () => {
      outcome = await form().save();
    });
    expect(outcome).toEqual({ status: "saved", changed: ["title"], merged: [] });
    expect(await bodies(sent, "PUT")).toEqual([{ version: 2, changes: { title: "Notes" } }]);
    await waitFor(() => {
      expect(form().version).toBe(3);
    });
    expect(form().dirty).toBe(false);
  });

  it("saves at the version the person's changes began from, though the section was read again since", async () => {
    let version = 2;
    const { form, sent, queryClient } = shown({
      [`GET ${SECTION}`]: () => read(version, { title: version === 2 ? "News" : "Theirs" }),
      [`PUT ${SECTION}`]: { status: 200, body: { version: 4, changed: ["title"], merged: [] } },
    });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("title", "Mine");
    });
    // Someone else saves; the page reads the section again (a focus, say).
    version = 3;
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/settings/{id}"] });
    });
    await waitFor(() => {
      expect(form().saved).toEqual({ title: "Theirs" });
    });
    expect(form().changes).toEqual({ title: "Mine" });
    await act(async () => {
      await form().save();
    });
    // At version 2, so the server can tell this edit never saw theirs (Codex on #87).
    expect(await bodies(sent, "PUT")).toEqual([{ version: 2, changes: { title: "Mine" } }]);
  });

  it("resolves a conflict with the person's choices, dropping the fields they gave up", async () => {
    let tries = 0;
    const { form, sent } = shown({
      [`GET ${SECTION}`]: read(2, { title: "News", per_page: 10 }),
      [`PUT ${SECTION}`]: () => {
        tries += 1;
        if (tries > 1) return { status: 200, body: { version: 4, changed: ["per_page"], merged: [] } };
        const refused = problem(409, "kernel.settings_conflict");
        return {
          ...refused,
          body: { ...(refused.body as object), version: 3, conflicts: [{ field: "title", yours: "Mine", theirs: "Theirs" }], by: null, at: null },
        };
      },
    });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("title", "Mine");
      form().set("per_page", 20);
    });
    await act(async () => {
      expect((await form().save()).status).toBe("conflict");
    });
    expect(form().conflict?.version).toBe(3);
    await act(async () => {
      expect((await form().resolve({ title: "theirs" })).status).toBe("saved");
    });
    const sentBodies = await bodies(sent, "PUT");
    expect(sentBodies[1]).toEqual({ version: 3, changes: { per_page: 20 } });
    expect(form().conflict).toBeNull();
    expect(form().changes).not.toHaveProperty("title");
  });

  it("keeps an edit made while a resolution was saving, of a field given to the other save", async () => {
    let tries = 0;
    const { form } = shown({
      [`GET ${SECTION}`]: read(2, { title: "News" }),
      [`PUT ${SECTION}`]: () => {
        tries += 1;
        if (tries > 1) return { status: 200, body: { version: 3, changed: [], merged: [] } };
        const refused = problem(409, "kernel.settings_conflict");
        return {
          ...refused,
          body: { ...(refused.body as object), version: 3, conflicts: [{ field: "title", yours: "Mine", theirs: "Theirs" }], by: null, at: null },
        };
      },
    });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("title", "Mine");
    });
    await act(async () => {
      await form().save();
    });
    let pending: Promise<unknown> = Promise.resolve();
    act(() => {
      pending = form().resolve({ title: "theirs" });
      form().set("title", "Newer");
    });
    await act(async () => {
      await pending;
    });
    // "Newer" came after the choice; it isn't the value given up (CodeRabbit on #87).
    expect(form().changes).toEqual({ title: "Newer" });
  });

  it("lets a field changed and changed back show what's saved since", async () => {
    let now = { version: 2, values: { title: "News" } as Record<string, unknown> };
    const { form, queryClient } = shown({ [`GET ${SECTION}`]: () => read(now.version, now.values) });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("title", "Mine");
    });
    act(() => {
      form().set("title", "News");
    });
    now = { version: 3, values: { title: "Theirs" } };
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["get", "/api/kernel/admin/settings/{id}"] });
    });
    // Nothing is changed, so the form shows what's saved (CodeRabbit on #87).
    await waitFor(() => {
      expect(form().values).toEqual({ title: "Theirs" });
    });
    expect(form().dirty).toBe(false);
  });

  it("keeps an edit made while a save was on its way protected from a later save", async () => {
    let now = { version: 2, values: { title: "News", per_page: 10 } as Record<string, unknown> };
    const { form, fetch, sent } = shown({
      [`GET ${SECTION}`]: () => read(now.version, now.values),
      [`PUT ${SECTION}`]: () => {
        if (now.version === 2) {
          // The title saves as 3; then someone else saves the page size as 4.
          now = { version: 4, values: { title: "Notes", per_page: 30 } };
          return { status: 200, body: { version: 3, changed: ["title"], merged: [] } };
        }
        return { status: 200, body: { version: 5, changed: ["per_page"], merged: [] } };
      },
    });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("title", "Notes");
    });
    const open = gated(fetch, "PUT");
    let pending: Promise<unknown> = Promise.resolve();
    act(() => {
      pending = form().save();
    });
    act(() => {
      form().set("per_page", 20);
    });
    open();
    await act(async () => {
      await pending;
    });
    await waitFor(() => {
      expect(form().saved).toEqual({ title: "Notes", per_page: 30 });
    });
    await act(async () => {
      await form().save();
    });
    // At 3, what the title's save left, so the kernel sees both changed the page size (CodeRabbit on #87).
    const puts = await bodies(sent, "PUT");
    expect(puts[1]).toEqual({ version: 3, changes: { per_page: 20 } });
  });

  it("puts a refused value's words beside its field", async () => {
    const refused = problem(422, "kernel.invalid_request");
    const { form } = shown({
      [`GET ${SECTION}`]: read(1, { links: [] }),
      [`PUT ${SECTION}`]: { ...refused, body: { ...(refused.body as object), errors: { "links.0": ["Not an address."] } } },
    });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    act(() => {
      form().set("links", ["nowhere"]);
    });
    await act(async () => {
      expect((await form().save()).status).toBe("refused");
    });
    expect(form().errors).toEqual({ links: "Not an address." });
    act(() => {
      form().set("links", ["https://example.test"]);
    });
    expect(form().errors).toEqual({});
  });

  it("reads the history with each saver's name, or their address", async () => {
    const { form } = shown({
      [`GET ${SECTION}`]: read(2, {}),
      [`GET ${SECTION}/history`]: {
        status: 200,
        body: {
          items: [{ number: 2, changed: ["title"], via: "form", saved_at: "2026-11-19T10:00:00Z", saved_by_id: "a" }],
          next_cursor: null,
          people: { a: { name: null, email: "ann@site.test" }, b: { name: "Bo", email: "bo@site.test" } },
        },
      },
    });
    await waitFor(() => {
      expect(form().read).toBe("read");
    });
    const history = await form().history();
    expect(history.versions).toHaveLength(1);
    expect(history.names).toEqual({ a: "ann@site.test", b: "Bo" });
  });
});
