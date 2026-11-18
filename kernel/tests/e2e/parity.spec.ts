// The server's words and React's agree (K4 contract §7; decision 0041): a
// crawler that runs no script and a person whose browser does read the same
// page. Every visible h1 to h3 and p React draws on `/` is in the server's
// copy. The copy is hidden while the app loads, shown at once without
// scripts, and shown after 3 s when the app never arrives. And axe finds no
// serious or critical problem on the pages the shell has so far.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const WORDS = ":is(h1, h2, h3, p)";

function normal(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

async function visibleWords(page: Page, within: string): Promise<string[]> {
  const found = await page.locator(`${within} ${WORDS}`).filter({ visible: true }).allInnerTexts();
  return found.map(normal).filter(Boolean);
}

test("the home page says only what the server's copy says", async ({ page, browser }) => {
  const plain = await browser.newContext({ javaScriptEnabled: false });
  const reader = await plain.newPage();
  const answer = await reader.goto("/");
  expect(answer?.status()).toBe(200);
  await expect(reader.locator("[data-server-copy]")).toBeVisible();
  const served = await visibleWords(reader, "[data-server-copy]");
  expect(served.length).toBeGreaterThanOrEqual(2); // the site's name and its description
  await plain.close();

  await page.goto("/");
  await expect(page.locator("[data-server-copy]")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const shown = await visibleWords(page, "body");
  expect(shown.length).toBeGreaterThanOrEqual(served.length);
  for (const words of shown) expect(served).toContain(words);
});

test("the server's words wait for the app, and show after 3 s if it never comes", async ({ page }) => {
  await page.route("**/assets/*.js", (route) => route.abort());
  await page.goto("/");
  const words = page.locator("[data-server-copy]");
  await expect(words).toBeHidden();
  await expect(words).toBeVisible({ timeout: 6_000 });
});

test("an address the site doesn't have is a real 404, and React's 404 page", async ({ page }) => {
  const answer = await page.goto("/nowhere");
  expect(answer?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
});

test("a kernel page is the shell, titled and not to be indexed", async ({ page }) => {
  const answer = await page.goto("/sign-in?next=%2Faccount");
  expect(answer?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  await expect(page).toHaveTitle(/^Sign in · /);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex");
});

test("a signed-out person asking for their account is sent to sign in, and back after", async ({ page }) => {
  await page.goto("/account");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);
});

for (const path of ["/", "/nowhere", "/sign-in"]) {
  test(`axe finds no serious or critical problem on ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = violations.filter((each) => each.impact === "serious" || each.impact === "critical");
    expect(serious.map((each) => `${each.id}: ${each.help}`)).toEqual([]);
  });
}
