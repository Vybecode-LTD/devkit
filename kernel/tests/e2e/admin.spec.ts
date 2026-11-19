// The admin's frame, Dashboard and Activity, as Chromium draws them (K4 contract §7, K4.6):
// staff with a second factor land on the Dashboard with what needs them, Ctrl K jumps to a
// page, the activity log shows the sign-in that brought them, the notices open and shut, the
// phone's Menu opens the sidebar; each admin page answers (a smoke test); nothing scrolls
// sideways at 390 px; axe finds nothing serious in either theme, a dialog or panel open too.
import { expect, test, type Page } from "@playwright/test";

import { THEMES, axe, makeUser, signInTo, theme } from "./support";

const ADMIN_PAGES = [
  ["/admin", /^Good (morning|afternoon|evening)$/],
  ["/admin/people", "People"],
  ["/admin/roles", "Roles"],
  ["/admin/activity", "Activity log"],
  ["/admin/settings", "Settings"],
  ["/admin/settings/features", "Features"],
  ["/admin/settings/system", "System"],
] as const;

async function signedInAdmin(page: Page, next = "/admin"): Promise<string> {
  const user = await makeUser(page.request, "admin", { totp: true, roles: ["member", "admin"] });
  await signInTo(page, user, next);
  return user.email;
}

test("staff land on the Dashboard with what needs them, each with its fix", async ({ page }) => {
  await signedInAdmin(page);
  await expect(page.getByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)$/ })).toBeVisible();
  const needs = page.getByRole("region", { name: /^Needs you \d+$/ });
  // The e2e site has a description and no card picture (harness.e2e).
  await expect(needs.getByText("Shared links show no picture")).toBeVisible();
  await expect(needs.getByText("The site has no description")).toHaveCount(0);
  await expect(needs.getByRole("link", { name: "Choose a picture" })).toHaveAttribute("href", "/admin/settings");
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toHaveText(/Admin\s*\/?\s*Dashboard/);
});

test("Ctrl K jumps to the activity log, which shows the sign-in that brought them here", async ({ page }) => {
  const email = await signedInAdmin(page);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Jump to a page" });
  await expect(dialog.getByRole("combobox", { name: "Page name" })).toBeFocused();
  await page.keyboard.type("activ");
  await expect(dialog.getByRole("option")).toHaveText(["Activity People and access"]);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/admin\/activity$/);
  await expect(page.getByRole("heading", { level: 1, name: "Activity log" })).toBeVisible();
  const table = page.getByRole("table", { name: "Entries, newest first" });
  const mine = table.getByRole("row").filter({ hasText: email }).filter({ hasText: "Signed in" });
  await expect(mine.first()).toBeVisible();
  await page.getByRole("group", { name: "Kind" }).getByRole("button", { name: "Sign-in" }).click();
  await expect(page.getByRole("table", { name: "Sign-in entries, newest first" }).getByRole("row").filter({ hasText: email }).first()).toBeVisible();
  await expect(page.getByText(/^Kept for \d+ days\./)).toBeVisible();
});

test("the notices open from the bell and shut on Escape, the focus back on the bell", async ({ page }) => {
  await signedInAdmin(page);
  const bell = page.getByRole("button", { name: /^Notices/ });
  await bell.click();
  await expect(page.getByRole("region", { name: "Notices" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("region", { name: "Notices" })).toHaveCount(0);
  await expect(bell).toBeFocused();
});

test("on a phone, Menu opens the sidebar and the next page shuts it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signedInAdmin(page);
  const nav = page.getByRole("navigation", { name: "Admin" });
  await expect(nav).toBeHidden();
  const menu = page.getByRole("button", { name: "Menu" });
  await menu.click();
  await expect(nav).toBeVisible();
  await nav.getByRole("link", { name: "People and access" }).click();
  await expect(page).toHaveURL(/\/admin\/people$/);
  await expect(nav).toBeHidden();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
});

test("every admin page answers in the frame (a smoke test)", async ({ page }) => {
  await signedInAdmin(page);
  for (const [path, heading] of ADMIN_PAGES) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading }), path).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Admin" }), path).toBeAttached();
  }
});

for (const [name, canvas] of Object.entries(THEMES)) {
  test(`nothing in the admin scrolls sideways at 390 px in ${name}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signedInAdmin(page);
    for (const path of ["/admin", "/admin/activity"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await theme(page, name, canvas);
      expect(await page.evaluate(() => document.documentElement.scrollWidth), path).toBeLessThanOrEqual(390);
      await page.getByRole("button", { name: "Menu" }).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth), `${path}, Menu open`).toBeLessThanOrEqual(390);
    }
  });

  test(`axe finds no serious or critical problem in the admin in ${name}, Jump to and the notices open too`, async ({ page }) => {
    await signedInAdmin(page);
    for (const path of ["/admin", "/admin/activity"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await theme(page, name, canvas);
      expect(await axe(page), path).toEqual([]);
    }
    await page.getByRole("button", { name: /^Notices/ }).click();
    await expect(page.getByRole("region", { name: "Notices" })).toBeVisible();
    await theme(page, name, canvas);
    expect(await axe(page), "notices").toEqual([]);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: "Jump to a page" })).toBeVisible();
    await theme(page, name, canvas);
    expect(await axe(page), "Jump to").toEqual([]);
  });
}
