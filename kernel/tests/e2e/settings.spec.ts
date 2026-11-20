// The admin's Settings, as Chromium draws them (K4 contract §7, K4.8): a save on the Site tab
// reaches llms.txt; on Features, switching the probe off asks first, takes its add-on with it, and
// comes back; on System, a failed job is retried and one that can't run again is discarded; axe
// finds nothing serious with the switch's question open, in either theme. The probe modules are
// the harness's test support's (harness/probe.py); no other test switches them.
import { expect, test, type Page } from "@playwright/test";

import { THEMES, axe, makeUser, signInTo, theme } from "./support";

async function signedInAdmin(page: Page, next: string): Promise<void> {
  const user = await makeUser(page.request, "settings", { totp: true, roles: ["member", "admin"] });
  await signInTo(page, user, next);
}

test("a save on the Site tab reaches llms.txt", async ({ page }) => {
  await signedInAdmin(page, "/admin/settings");
  const summary = `Saved by the end-to-end run ${String(Date.now())}.`;
  const field = page.getByRole("textbox", { name: "Summary for AI tools" });
  await field.fill(summary);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  const llms = await page.request.get("/llms.txt");
  expect(await llms.text()).toContain(summary);
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Summary for AI tools" })).toHaveValue(summary);
});

test("switching the probe off asks first, takes its add-on with it, and comes back", async ({ page }) => {
  await signedInAdmin(page, "/admin/settings/features");
  const probe = page.getByRole("switch", { name: "Probe", exact: true });
  const addon = page.getByRole("switch", { name: "Probe add-on" });
  await expect(probe).toBeChecked();
  await probe.click();
  const dialog = page.getByRole("dialog", { name: "Switch off Probe?" });
  await expect(dialog).toContainText("Probe add-on needs Probe, so it goes off too.");
  for (const [name, canvas] of Object.entries(THEMES)) {
    await theme(page, name, canvas);
    expect(await axe(page), `the switch's question in ${name}`).toEqual([]);
  }
  await dialog.getByRole("button", { name: "Switch off 2" }).click();
  await expect(page.getByText("Probe is switched off.")).toBeVisible();
  await expect(probe).not.toBeChecked();
  await expect(addon).toBeChecked();
  await expect(addon).toHaveAccessibleDescription(/Off while Probe is off\./);
  expect((await page.request.get("/api/probe/ping")).status()).toBe(404);
  await probe.click();
  await expect(page.getByText("Probe is switched on.")).toBeVisible();
  expect((await page.request.get("/api/probe/ping")).status()).toBe(200);
});

test("a failed job is retried, and one that can't run again is discarded", async ({ page }) => {
  const fail = async (sealed: boolean): Promise<string> => {
    const made = await page.request.post("/api/_test/jobs", { data: { name: "probe.fail", sealed } });
    expect(made.status()).toBe(201);
    return ((await made.json()) as { id: string }).id;
  };
  const retried = await fail(false);
  const wiped = await fail(true);
  expect((await page.request.post("/api/_test/jobs/run")).status()).toBe(204);
  await signedInAdmin(page, "/admin/settings/system");
  await expect(page.getByText(/jobs? failed for good$/)).toBeVisible();
  const table = page.getByRole("table", { name: "Jobs that failed for good" });
  // Each test's jobs are its own; the list may hold others' too.
  const rows = table.getByRole("row").filter({ hasText: "probe.fail" });
  await expect(rows.first()).toBeVisible();
  const ids = await page.request.get("/api/kernel/admin/jobs/dead?limit=100");
  const items = ((await ids.json()) as { items: { id: string; retryable: boolean }[] }).items;
  expect(items.find((item) => item.id === retried)?.retryable).toBe(true);
  expect(items.find((item) => item.id === wiped)?.retryable).toBe(false);

  const retryable = rows.filter({ has: page.getByRole("button", { name: "Retry" }) }).first();
  await retryable.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("probe.fail will run again shortly.")).toBeVisible();

  const onlyDiscard = rows.filter({ hasNot: page.getByRole("button", { name: "Retry" }) }).first();
  await onlyDiscard.getByRole("button", { name: "Discard" }).click();
  await page.getByRole("dialog", { name: "Discard probe.fail?" }).getByRole("button", { name: "Discard" }).click();
  await expect(page.getByText("probe.fail is discarded.")).toBeVisible();
});
