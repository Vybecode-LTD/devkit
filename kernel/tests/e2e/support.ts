// What the admin's end-to-end spec shares (K4.6): accounts made through the harness's test
// support, a TOTP code, signing in with both steps, a theme switched with its fades finished,
// and axe's serious and critical findings. sign-in.spec.ts keeps its own copies, from before.
import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { createHmac, randomBytes } from "node:crypto";

export const PASSWORD = "quiet orbit lantern 4471 marsh";

export const THEMES = {
  "machined-light": "rgb(236, 236, 234)",
  "vibrant-mindz": "rgb(7, 10, 22)",
} as const;

export type Made = { email: string; totp: string };

/** An account: verified, with a password, its roles, and a confirmed TOTP when asked. */
export async function makeUser(request: APIRequestContext, name: string, fields: { totp?: boolean; roles?: string[] } = {}): Promise<Made> {
  const email = `${name}-${randomBytes(5).toString("hex")}@mechframe.test`;
  const answer = await request.post("/api/_test/users", { data: { email, password: PASSWORD, verified: true, ...fields } });
  expect(answer.status(), await answer.text()).toBe(201);
  const body = (await answer.json()) as { totp_secret?: string };
  return { email, totp: body.totp_secret ?? "" };
}

function base32(text: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const letter of text.replace(/[\s=]/g, "").toUpperCase()) bits += alphabet.indexOf(letter).toString(2).padStart(5, "0");
  const bytes: number[] = [];
  for (let at = 0; at + 8 <= bits.length; at += 8) bytes.push(Number.parseInt(bits.slice(at, at + 8), 2));
  return Buffer.from(bytes);
}

/** RFC 6238's code for `secret` now (30-second steps, six digits, SHA-1). */
export function totp(secret: string, when = Date.now()): string {
  const step = Buffer.alloc(8);
  step.writeBigUInt64BE(BigInt(Math.floor(when / 30_000)));
  const mac = createHmac("sha1", base32(secret)).update(step).digest();
  const offset = (mac[mac.length - 1] ?? 0) & 0xf;
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

/** Signs `user` in with their password and app code, landing on `next`. */
export async function signInTo(page: Page, user: Made, next: string): Promise<void> {
  await page.goto(`/sign-in?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Code from your app").fill(totp(user.totp));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(new RegExp(`${next.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}$`));
}

/** The theme `name` on the page, once its fades have finished. */
export async function theme(page: Page, name: string, canvas: string): Promise<void> {
  await page.evaluate(async (chosen) => {
    document.documentElement.dataset.theme = chosen;
    document.body.getBoundingClientRect();
    await Promise.all(document.getAnimations().map((animation) => animation.finished));
  }, name);
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor)).toBe(canvas);
}

export async function axe(page: Page): Promise<string[]> {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  return violations.filter((each) => each.impact === "serious" || each.impact === "critical").map((each) => `${each.id}: ${each.help}`);
}
