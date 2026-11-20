// The admin's System tab (K4.8): the background jobs, the ones that failed for
// good with Retry and Discard, and the services as the host set them up.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { renderApp, testUser } from "../../testing";
import { routedFetch, type Answer } from "../test-fetch";
import { emailRow, storageRow, type DeadJob, type SystemRead } from "./System";

beforeAll(async () => {
  await import("./System");
});

const ACTS = ["kernel.settings.manage", "kernel.jobs.manage"];
const staff = (permissions = ACTS) => testUser({ roles: ["member", "admin"], second_factor: true, permissions });

const SYSTEM: SystemRead = {
  jobs: { queued: 3, running: 0, dead: 2, worker: "ok" },
  services: { email: "smtp", storage: { configured: true, public: true } },
  version: "0.1.0",
  modules: { installed: 4, on: 3 },
};

function job(id: string, fields: Partial<DeadJob> = {}): DeadJob {
  return {
    id: `00000000-0000-4000-8000-0000000000${id}`,
    name: "blog.send_digest",
    module: "blog",
    tries: 5,
    last_error: "TimeoutError",
    failed_at: "2026-11-19T10:00:00Z",
    retryable: true,
    ...fields,
  };
}

const DIGEST = job("a1");
const MAIL = job("b2", { name: "kernel.send_mail", module: "kernel", retryable: false, last_error: "SMTPException" });

function answers(more: Record<string, Answer | ((request: Request) => Answer)> = {}, system: SystemRead = SYSTEM) {
  return routedFetch({
    "GET /api/kernel/notifications": { status: 200, body: { items: [], next_cursor: null, unread: 0 } },
    "GET /api/kernel/admin/system": { status: 200, body: system },
    "GET /api/kernel/admin/jobs/dead": { status: 200, body: { items: [DIGEST, MAIL], next_cursor: null } },
    "GET /api/kernel/admin/attention": { status: 200, body: { items: [] } },
    ...more,
  });
}

async function opened(session = staff()) {
  renderApp({ path: "/admin/settings/system", session });
  await screen.findByRole("heading", { level: 2, name: "Jobs that failed for good" });
  return within(await screen.findByRole("table", { name: "Jobs that failed for good" }));
}

const sentTo = (sent: Request[], method: string, path: string) =>
  sent.filter((request) => request.method === method && new URL(request.url).pathname === path);

describe("the System tab", () => {
  it("says what failed, how the queue stands and how the services are set up", async () => {
    answers();
    const table = await opened();
    expect(screen.getByText("2 jobs failed for good")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review below" })).toHaveAttribute("href", "/admin/settings/system#failed-jobs");
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("Sending by SMTP")).toBeInTheDocument();
    expect(screen.getByText("Two buckets: public files and private downloads")).toBeInTheDocument();
    expect(screen.getByText(/Kernel 0\.1\.0; 4 modules, 3 on/)).toBeInTheDocument();
    expect(table.getByText("blog.send_digest")).toBeInTheDocument();
    expect(table.getByText("TimeoutError")).toBeInTheDocument();
  });

  it("retries a job that can run again; one that can't is only discarded", async () => {
    const { sent } = answers({
      [`POST /api/kernel/admin/jobs/${DIGEST.id}/retry`]: { status: 200, body: { state: "queued" } },
    });
    const user = userEvent.setup();
    const table = await opened();
    const [digestRow, mailRow] = table.getAllByRole("row").slice(1);
    expect(within(mailRow as HTMLElement).queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.getByText(/A job without Retry can't run again/)).toBeInTheDocument();
    await user.click(within(digestRow as HTMLElement).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("blog.send_digest will run again shortly.")).toBeInTheDocument();
    expect(sentTo(sent, "POST", `/api/kernel/admin/jobs/${DIGEST.id}/retry`)).toHaveLength(1);
  });

  it("asks before discarding a job for good", async () => {
    const { sent } = answers({ [`DELETE /api/kernel/admin/jobs/${MAIL.id}`]: { status: 204 } });
    const user = userEvent.setup();
    const table = await opened();
    const mailRow = table.getAllByRole("row")[2] as HTMLElement;
    await user.click(within(mailRow).getByRole("button", { name: "Discard" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Discard kernel.send_mail?" }));
    await user.click(dialog.getByRole("button", { name: "Keep it" }));
    expect(sentTo(sent, "DELETE", `/api/kernel/admin/jobs/${MAIL.id}`)).toHaveLength(0);
    await user.click(within(mailRow).getByRole("button", { name: "Discard" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard" }));
    expect(await screen.findByText("kernel.send_mail is discarded.")).toBeInTheDocument();
    expect(sentTo(sent, "DELETE", `/api/kernel/admin/jobs/${MAIL.id}`)).toHaveLength(1);
  });

  it("puts the focus on the list's heading once a discarded job's row is gone", async () => {
    let gone = false;
    answers({
      "GET /api/kernel/admin/jobs/dead": () => ({ status: 200, body: { items: gone ? [DIGEST] : [DIGEST, MAIL], next_cursor: null } }),
      [`DELETE /api/kernel/admin/jobs/${MAIL.id}`]: () => {
        gone = true;
        return { status: 204 };
      },
    });
    const user = userEvent.setup();
    const table = await opened();
    await user.click(within(table.getAllByRole("row")[2] as HTMLElement).getByRole("button", { name: "Discard" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard" }));
    await screen.findByText("kernel.send_mail is discarded.");
    // Its Discard button went with the row; the focus isn't left on nothing (CodeRabbit on #87).
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 2, name: "Jobs that failed for good" })).toHaveFocus();
    });
  });

  it("offers no Retry or Discard without the jobs permission", async () => {
    answers();
    const table = await opened(staff(["kernel.settings.manage"]));
    expect(table.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(table.queryByRole("button", { name: "Discard" })).toBeNull();
    expect(screen.getByText(/needs the jobs permission/)).toBeInTheDocument();
  });

  it("says when the worker is behind, and when nothing has failed", async () => {
    answers(
      { "GET /api/kernel/admin/jobs/dead": { status: 200, body: { items: [], next_cursor: null } } },
      { ...SYSTEM, jobs: { queued: 9, running: 0, dead: 0, worker: "behind" } },
    );
    renderApp({ path: "/admin/settings/system", session: staff() });
    // An empty table is its caption over the empty state.
    expect(await screen.findByText("No job has failed for good.")).toBeInTheDocument();
    expect(screen.getAllByText("Behind").length).toBeGreaterThan(0);
    expect(screen.getByText(/more than 2 minutes late/)).toBeInTheDocument();
    expect(screen.queryByText(/jobs? failed for good$/)).toBeNull();
  });
});

describe("the services' words", () => {
  it("says how mail goes out", () => {
    expect(emailRow("resend").line).toBe("Sending through Resend");
    expect(emailRow("log")).toMatchObject({ tone: "warning", state: "Not set up" });
  });

  it("says which buckets storage has", () => {
    expect(storageRow({ configured: false, public: false }).state).toBe("Not set up");
    expect(storageRow({ configured: true, public: false }).line).toBe("One private bucket, for downloads");
  });
});
