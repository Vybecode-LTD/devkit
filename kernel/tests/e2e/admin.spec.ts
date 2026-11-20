// The admin's frame, Dashboard, Activity, People, Roles and Settings, as Chromium draws them (K4
// contract §7, K4.6 to K4.8; Settings' own flows are settings.spec.ts):
// staff with a second factor land on the Dashboard with what needs them, Ctrl K jumps to a
// page, the activity log shows the sign-in that brought them, the notices open and shut, the
// phone's Menu opens the sidebar; each admin page answers (a smoke test); nothing scrolls
// sideways at 390 px; axe finds nothing serious in either theme, a dialog or panel open too.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { PASSWORD, THEMES, axe, makeUser, signInTo, theme } from "./support";

const ADMIN_PAGES = [
  ["/admin", /^Good (morning|afternoon|evening)$/],
  ["/admin/people", "People"],
  ["/admin/roles", "Roles and permissions"],
  ["/admin/activity", "Activity log"],
  ["/admin/settings", "Settings"],
  ["/admin/settings/features", "Settings"],
  ["/admin/settings/system", "Settings"],
] as const;

/** The admin pages the phone and axe loops open; Settings' three tabs (K4.8) have an axe test of their own. */
const OTHERS = ["/admin", "/admin/activity", "/admin/people", "/admin/roles"];
const SETTINGS = ["/admin/settings", "/admin/settings/features", "/admin/settings/system"];
const LOOPED = [...OTHERS, ...SETTINGS];

/**
 * `email`'s own sign-in in `table`, paging back with Show older until it shows: every test
 * writes to the one log side by side, so it needn't be among the newest fifty (CodeRabbit on #84).
 */
async function ownSignIn(page: Page, table: Locator, email: string): Promise<Locator> {
  await expect(table).toBeVisible();
  const rows = table.getByRole("row");
  const mine = rows.filter({ hasText: email }).filter({ hasText: "Signed in" }).first();
  const older = page.getByRole("button", { name: "Show older" });
  for (let pages = 0; pages < 20 && !(await mine.isVisible()) && (await older.isVisible()); pages += 1) {
    const shown = await rows.count();
    await older.click();
    await expect.poll(() => rows.count()).toBeGreaterThan(shown);
  }
  return mine;
}

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

test("Ctrl K jumps to the activity log, which shows the sign-in that brought them here", async ({ page, request }) => {
  const email = await signedInAdmin(page);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  // Fifty-one newer entries, so the admin's sign-in is past the first page and ownSignIn pages back
  // to it. `request` keeps cookies of its own: the page stays signed in as the admin. Each sign-in
  // hashes a password, slow on purpose, beside the other tests: three times the usual budget.
  test.slow();
  const busy = await makeUser(request, "busy");
  for (let n = 0; n <= 50; n += 1) {
    const answer = await request.post("/api/auth/sign-in", { data: { email: busy.email, password: PASSWORD } });
    expect(answer.status()).toBe(200);
  }
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Jump to a page" });
  await expect(dialog.getByRole("combobox", { name: "Page name" })).toBeFocused();
  await page.keyboard.type("activ");
  await expect(dialog.getByRole("option")).toHaveText(["Activity People and access"]);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/admin\/activity$/);
  await expect(page.getByRole("heading", { level: 1, name: "Activity log" })).toBeVisible();
  const all = page.getByRole("table", { name: "Entries, newest first" });
  await expect(all.getByRole("row")).toHaveCount(51); // a header and the newest fifty
  await expect(all.getByRole("row").filter({ hasText: email })).toHaveCount(0);
  await expect(await ownSignIn(page, all, email)).toBeVisible();
  await page.getByRole("group", { name: "Kind" }).getByRole("button", { name: "Sign-in" }).click();
  await expect(await ownSignIn(page, page.getByRole("table", { name: "Sign-in entries, newest first" }), email)).toBeVisible();
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
    for (const path of LOOPED) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await theme(page, name, canvas);
      expect(await page.evaluate(() => document.documentElement.scrollWidth), path).toBeLessThanOrEqual(390);
      await page.getByRole("button", { name: "Menu" }).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth), `${path}, Menu open`).toBeLessThanOrEqual(390);
    }
  });

  test(`axe finds no serious or critical problem in Settings in ${name}`, async ({ page }) => {
    await signedInAdmin(page, "/admin/settings");
    for (const path of SETTINGS) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await theme(page, name, canvas);
      expect(await axe(page), path).toEqual([]);
    }
  });

  test(`axe finds no serious or critical problem in the admin in ${name}, Jump to and the notices open too`, async ({ page }) => {
    await signedInAdmin(page);
    for (const path of OTHERS) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await theme(page, name, canvas);
      expect(await axe(page), path).toEqual([]);
    }
    await page.getByRole("button", { name: "New role" }).click();
    await expect(page.getByRole("dialog", { name: "New role" })).toBeVisible();
    await theme(page, name, canvas);
    expect(await axe(page), "New role").toEqual([]);
    await page.keyboard.press("Escape");
    await page.goto("/admin/people");
    await page.getByRole("button", { name: /^Open / }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await theme(page, name, canvas);
    expect(await axe(page), "a person's roles").toEqual([]);
    await page.keyboard.press("Escape");
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

test("an admin makes a role, gives it to someone, and Roles counts them", async ({ page, request }) => {
  test.slow(); // three sign-ins' worth of password hashing beside the other tests
  await signedInAdmin(page, "/admin/roles");
  const member = await makeUser(request, "member");
  const name = `Crew ${String(Date.now()).slice(-6)}`;
  await page.getByRole("button", { name: "New role" }).click();
  const editor = page.getByRole("dialog", { name: "New role" });
  await editor.getByRole("textbox", { name: "Name" }).fill(name);
  await editor.getByRole("switch", { name: /^Read the audit log/ }).click();
  await editor.getByRole("button", { name: "Make role" }).click();
  await expect(editor).toBeHidden();
  const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name, level: 2 }) });
  await expect(card.getByText("0", { exact: true })).toBeVisible();

  await page.goto("/admin/people");
  await page.getByRole("searchbox", { name: "Search by email" }).fill(member.email);
  await page.getByRole("button", { name: `Open ${member.email}` }).click();
  const dialog = page.getByRole("dialog", { name: member.email });
  await dialog.getByRole("switch", { name: new RegExp(`^${name}`) }).click();
  await dialog.getByRole("button", { name: "Save roles" }).click();
  await expect(dialog).toBeHidden();
  const row = page.getByRole("row").filter({ hasText: member.email });
  await expect(row.getByText(name)).toBeVisible();
  await expect(row.getByText("Not set up")).toBeVisible(); // staff now, with no second factor

  await page.goto("/admin/roles");
  await expect(card.getByText("1", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: `Edit ${name}` }).click();
  await expect(page.getByText("One person holds this role.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete role" })).toHaveCount(0);
});
