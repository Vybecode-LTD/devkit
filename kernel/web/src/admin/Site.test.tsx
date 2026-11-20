// The admin's Site tab (K4.8): the site's identity and who may sign up, saved
// section by section at the version each was read at.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import { defineModule } from "../modules";
import { useSettings } from "../settings/useSettings";
import { Field, Input } from "../ui/Field";
import { problem, routedFetch, type Answer } from "../test-fetch";
import { signUpHint } from "./Site";

function BlogSection() {
  const form = useSettings("blog");
  const title = typeof form.values.title === "string" ? form.values.title : "";
  return (
    <Field label="Blog title">
      <Input
        value={title}
        onChange={(event) => {
          form.set("title", event.target.value);
        }}
      />
    </Field>
  );
}

const blog = defineModule({
  id: "blog",
  routes: { public: [], member: [], admin: [] },
  slots: { "admin.settings.section": [{ id: "blog", title: "Blog", lazy: () => Promise.resolve({ default: BlogSection }) }] },
});

beforeAll(async () => {
  await import("./Site");
});

const ALL = ["kernel.settings.manage", "kernel.module.manage", "kernel.jobs.manage"];
const admin = (permissions: string[] = ALL) =>
  testUser({ roles: ["member", "admin"], second_factor: true, permissions });

const SITE_VALUES = {
  description: "Music and more.",
  kind: "MusicGroup",
  logo: "/logo.png",
  card_image: "",
  same_as: ["https://example.test/band"],
  llms_summary: "",
  ai_crawlers: "allow",
};

const form = (version: number, values: Record<string, unknown>): Answer => ({ status: 200, body: { version, values } });
const empty = { status: 200, body: { items: [], next_cursor: null, people: {} } };

function answers(more: Record<string, Answer | ((request: Request) => Answer)> = {}) {
  return routedFetch({
    "GET /api/kernel/notifications": { status: 200, body: { items: [], next_cursor: null, unread: 0 } },
    "GET /api/kernel/admin/settings/kernel.site": form(4, SITE_VALUES),
    "GET /api/kernel/admin/settings/kernel.auth": form(0, { sign_up_mode: "closed" }),
    "GET /api/kernel/admin/settings/kernel.site/history": empty,
    "GET /api/kernel/admin/settings/kernel.auth/history": empty,
    "GET /api/kernel/admin/attention": { status: 200, body: { items: [] } },
    ...more,
  });
}

async function opened(session = admin()) {
  renderApp({ path: "/admin/settings", session });
  await screen.findByRole("heading", { level: 1, name: "Settings" });
  return screen.findByRole("textbox", { name: "Description" });
}

const sentTo = (sent: Request[], method: string, path: string) =>
  sent.filter((request) => request.method === method && new URL(request.url).pathname === path);

describe("the Site tab", () => {
  it("shows the site's saved identity, its name from the host, and the sign-up switch", async () => {
    answers();
    const description = await opened();
    expect(description).toHaveValue("Music and more.");
    expect(screen.getByRole("textbox", { name: "Site name" })).toHaveValue("Test Site");
    expect(screen.getByRole("textbox", { name: "Site name" })).toHaveAttribute("readonly");
    expect(screen.getByRole("combobox", { name: "What the site is" })).toHaveValue("MusicGroup");
    expect(screen.getByRole("textbox", { name: "Profiles elsewhere" })).toHaveValue("https://example.test/band");
    expect(screen.getByRole("switch", { name: "Let AI crawlers read the site" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Anyone can sign up" })).not.toBeChecked();
    // What no section holds is left off, not faked.
    expect(screen.queryByRole("textbox", { name: "Tagline" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Contact email" })).toBeNull();
    expect(screen.queryByRole("switch", { name: /second factor/ })).toBeNull();
  });

  it("offers each tab the person may open, as links, the page's own marked", async () => {
    answers();
    await opened(admin(["kernel.settings.manage"]));
    const tabs = within(screen.getByRole("navigation", { name: "Settings" }));
    expect(tabs.getAllByRole("link").map((link) => link.textContent)).toEqual(["Site", "System"]);
    expect(tabs.getByRole("link", { name: "Site" })).toHaveAttribute("aria-current", "page");
  });

  it("saves only what changed, at the version it was read at", async () => {
    const { sent } = answers({
      "PUT /api/kernel/admin/settings/kernel.site": { status: 200, body: { version: 5, changed: ["description"], merged: [] } },
    });
    const user = userEvent.setup();
    const description = await opened();
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    await user.clear(description);
    await user.type(description, "New words.");
    expect(save).toBeEnabled();
    await user.click(save);
    expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
    const puts = sentTo(sent, "PUT", "/api/kernel/admin/settings/kernel.site");
    expect(puts).toHaveLength(1);
    expect(await puts[0]?.json()).toEqual({ version: 4, changes: { description: "New words." } });
    // The other section had nothing to save.
    expect(sentTo(sent, "PUT", "/api/kernel/admin/settings/kernel.auth")).toHaveLength(0);
  });

  it("takes one profile on each line as it's typed, Enter and all", async () => {
    const { sent } = answers({
      "PUT /api/kernel/admin/settings/kernel.site": { status: 200, body: { version: 5, changed: ["same_as"], merged: [] } },
    });
    const user = userEvent.setup();
    await opened();
    const profiles = screen.getByRole("textbox", { name: "Profiles elsewhere" });
    await user.clear(profiles);
    await user.type(profiles, "https://a.test{Enter}https://b.test");
    // The newline stays while typing (Codex on #87).
    expect(profiles).toHaveValue(["https://a.test", "https://b.test"].join(String.fromCharCode(10)));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Settings saved.");
    const [put] = sentTo(sent, "PUT", "/api/kernel/admin/settings/kernel.site");
    expect(await put?.json()).toEqual({ version: 4, changes: { same_as: ["https://a.test", "https://b.test"] } });
  });

  it("opens sign-up by saving the accounts section", async () => {
    const { sent } = answers({
      "PUT /api/kernel/admin/settings/kernel.auth": { status: 200, body: { version: 1, changed: ["sign_up_mode"], merged: [] } },
    });
    const user = userEvent.setup();
    await opened();
    await user.click(screen.getByRole("switch", { name: "Anyone can sign up" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Settings saved.");
    const [put] = sentTo(sent, "PUT", "/api/kernel/admin/settings/kernel.auth");
    expect(await put?.json()).toEqual({ version: 0, changes: { sign_up_mode: "open" } });
  });

  it("shows a refused value beside its field", async () => {
    answers({
      "PUT /api/kernel/admin/settings/kernel.site": {
        ...problem(422, "kernel.invalid_request"),
        body: {
          ...(problem(422, "kernel.invalid_request").body as object),
          errors: { logo: ["'ftp://x' isn't an https address or a path on this site."] },
        },
      },
    });
    const user = userEvent.setup();
    await opened();
    const logo = screen.getByRole("textbox", { name: "Logo" });
    await user.clear(logo);
    await user.type(logo, "ftp://x");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Some of these settings aren't valid. Check the fields marked.")).toBeInTheDocument();
    expect(logo).toHaveAttribute("aria-invalid", "true");
    expect(logo).toHaveAccessibleDescription(/isn't an https address/);
  });

  it("asks which value to keep when someone else saved the field meanwhile", async () => {
    let tries = 0;
    const { sent } = answers({
      "PUT /api/kernel/admin/settings/kernel.site": () => {
        tries += 1;
        if (tries > 1) return { status: 200, body: { version: 6, changed: ["description"], merged: [] } };
        const conflict = problem(409, "kernel.settings_conflict");
        return {
          ...conflict,
          body: {
            ...(conflict.body as object),
            version: 5,
            conflicts: [{ field: "description", yours: "Mine.", theirs: "Theirs." }],
            by: null,
            at: "2026-11-19T12:00:00Z",
          },
        };
      },
    });
    const user = userEvent.setup();
    const description = await opened();
    await user.clear(description);
    await user.type(description, "Mine.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Choose which values to keep/)).toBeInTheDocument();
    expect(await screen.findByText("Theirs.")).toBeInTheDocument();
    await waitFor(() => {
      expect(sentTo(sent, "PUT", "/api/kernel/admin/settings/kernel.site")).toHaveLength(1);
    });
  });
});

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

describe("a module's settings section", () => {
  it("holds the page's Save while the section saves", async () => {
    const { fetch } = answers({
      "GET /api/kernel/admin/settings/blog": form(1, { title: "News" }),
      "PUT /api/kernel/admin/settings/blog": { status: 200, body: { version: 2, changed: ["title"], merged: [] } },
    });
    const user = userEvent.setup();
    renderApp({ path: "/admin/settings", session: admin(), modules: [blog] });
    const title = await screen.findByRole("textbox", { name: "Blog title" });
    await waitFor(() => {
      expect(title).toHaveValue("News");
    });
    await user.type(title, "!");
    const open = gated(fetch, "PUT");
    await user.click(screen.getByRole("button", { name: "Save" }));
    // Only the module's section is saving; a second click mustn't send it again (CodeRabbit on #87).
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    open();
    await screen.findByText("Settings saved.");
  });

  it("is saved by the page's Save, and kept from a move away while it has changes", async () => {
    const { sent } = answers({
      "GET /api/kernel/admin/settings/blog": form(1, { title: "News" }),
      "PUT /api/kernel/admin/settings/blog": { status: 200, body: { version: 2, changed: ["title"], merged: [] } },
    });
    const user = userEvent.setup();
    renderApp({ path: "/admin/settings", session: admin(), modules: [blog] });
    const title = await screen.findByRole("textbox", { name: "Blog title" });
    await waitFor(() => {
      expect(title).toHaveValue("News");
    });
    await user.clear(title);
    await user.type(title, "Notes");
    // The page's one Save sees the section's change (CodeRabbit on #87).
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeEnabled();
    await user.click(within(screen.getByRole("navigation", { name: "Settings" })).getByRole("link", { name: "Features" }));
    expect(await screen.findByRole("dialog", { name: "You have changes that aren't saved" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    await user.click(save);
    await screen.findByText("Settings saved.");
    const puts = sentTo(sent, "PUT", "/api/kernel/admin/settings/blog");
    expect(puts).toHaveLength(1);
    expect(await puts[0]?.json()).toEqual({ version: 1, changes: { title: "Notes" } });
  });
});

describe("the sign-up switch's words", () => {
  it("says what each mode means", () => {
    expect(signUpHint("open")).toMatch(/members/);
    expect(signUpHint("invite")).toMatch(/Invite only/);
    expect(signUpHint("closed")).toMatch(/takes no new accounts/);
  });
});
