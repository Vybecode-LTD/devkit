// The site in a browser (K5 contract §7): the home page and sign-in draw, the
// home page says only what the server's copy says, a missing address is a real
// 404, and axe finds no serious or critical problem.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const WORDS = ":is(h1, h2, h3, p)";

async function visibleWords(page: Page, within: string): Promise<string[]> {
  const found = await page.locator(`${within} ${WORDS}`).filter({ visible: true }).allInnerTexts();
  return found.map((text) => text.replace(/\s+/g, " ").trim()).filter(Boolean);
}

async function seriousProblems(page: Page): Promise<string[]> {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  return violations
    .filter((each) => each.impact === "serious" || each.impact === "critical")
    .map((each) => `${each.id}: ${each.help}`);
}

test("the home page draws, with nothing serious for axe", async ({ page }) => {
  const answer = await page.goto("/");
  expect(answer?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Test Site" })).toBeVisible();
  expect(await seriousProblems(page)).toEqual([]);
});

test("the home page says only what the server's copy says", async ({ page, browser }) => {
  const plain = await browser.newContext({ javaScriptEnabled: false });
  const reader = await plain.newPage();
  await reader.goto("/");
  const served = await visibleWords(reader, "[data-server-copy]");
  expect(served.length).toBeGreaterThanOrEqual(2); // the site's name and its description
  await plain.close();

  await page.goto("/");
  await expect(page.locator("[data-server-copy]")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  // The same words, all of them, in the same order (CodeRabbit on #92).
  expect(await visibleWords(page, "main")).toEqual(served);
});

test("sign-in draws, with nothing serious for axe", async ({ page }) => {
  const answer = await page.goto("/sign-in");
  expect(answer?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  expect(await seriousProblems(page)).toEqual([]);
});

test("an address the site doesn't have is a real 404", async ({ page }) => {
  const answer = await page.goto("/nowhere");
  expect(answer?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
});
