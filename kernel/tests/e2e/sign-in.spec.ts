// Signing in, up and back, and the account's factors and devices, as Chromium does them
// (K4 contract §7, K4.5): every sign-in method (a password; a password then the app's code,
// a recovery code or a passkey; a passkey alone, on a virtual authenticator; a code by
// email; a link by email), sign-up and its link, a reset, the authenticator app set up and
// removed, a passkey added, and a device signed out from another. Mail is read through the
// harness's test support. axe checks the account's pages, a dialog open on them, in both
// themes; the sign-in pages are in parity.spec.ts's run.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import jsQR from "jsqr";
import { createHmac, randomBytes } from "node:crypto";

const PASSWORD = "quiet orbit lantern 4471 marsh";
const NEW_PASSWORD = "copper heron valley 2093 tide";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

type Made = { email: string; totp: string };

function address(name: string): string {
  return `${name}-${randomBytes(5).toString("hex")}@mechframe.test`;
}

/** An account, made through the harness's test support: verified, with a password, and a confirmed TOTP when asked. */
async function makeUser(request: APIRequestContext, name: string, fields: { totp?: boolean; roles?: string[] } = {}): Promise<Made> {
  const email = address(name);
  const answer = await request.post("/api/_test/users", { data: { email, password: PASSWORD, verified: true, ...fields } });
  expect(answer.status(), await answer.text()).toBe(201);
  const body = (await answer.json()) as { totp_secret?: string };
  return { email, totp: body.totp_secret ?? "" };
}

/** The newest message to `to` whose text matches `pattern`, waiting for it to be sent. */
async function mailed(request: APIRequestContext, to: string, pattern: RegExp): Promise<RegExpMatchArray> {
  let found = null as RegExpMatchArray | null;
  await expect
    .poll(
      async () => {
        const answer = await request.get(`/api/_test/mail?to=${encodeURIComponent(to)}`);
        const { messages } = (await answer.json()) as { messages: { text: string }[] };
        found = messages.map((message) => pattern.exec(message.text)).filter(Boolean).at(-1) ?? null;
        return found !== null;
      },
      { timeout: 10_000 },
    )
    .toBe(true);
  if (!found) throw new Error(`No mail to ${to} matching ${String(pattern)}.`);
  return found;
}

/** A link's path and query, from a mail that names the site's address. */
function pathOf(link: string): string {
  const url = new URL(link, "http://localhost");
  return url.pathname + url.search;
}

function base32(text: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const letter of text.replace(/[\s=]/g, "").toUpperCase()) bits += alphabet.indexOf(letter).toString(2).padStart(5, "0");
  const bytes: number[] = [];
  for (let at = 0; at + 8 <= bits.length; at += 8) bytes.push(Number.parseInt(bits.slice(at, at + 8), 2));
  return Buffer.from(bytes);
}

/** RFC 6238's code for `secret` at `when` (30-second steps, six digits, SHA-1). */
function totp(secret: string, when = Date.now()): string {
  const step = Buffer.alloc(8);
  step.writeBigUInt64BE(BigInt(Math.floor(when / 30_000)));
  const mac = createHmac("sha1", base32(secret)).update(step).digest();
  const offset = (mac[mac.length - 1] ?? 0) & 0xf;
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

/**
 * What a phone's camera reads from the QR code as Chromium draws it: its path filled with its
 * computed colours on its computed ground, 4 px a module, read back from a canvas and decoded
 * dark-on-light only, as many authenticator apps' scanners need it.
 */
async function scanQr(page: Page): Promise<string | undefined> {
  const drawn = await page.getByRole("img", { name: "A QR code for your authenticator app" }).evaluate((svg) => {
    const style = getComputedStyle(svg);
    const modules = Number((svg.getAttribute("viewBox") ?? "").split(" ")[2]);
    const scale = 4;
    const size = modules * scale;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("No 2D canvas.");
    context.fillStyle = style.backgroundColor;
    context.fillRect(0, 0, size, size);
    context.scale(scale, scale);
    context.fillStyle = style.color;
    context.fill(new Path2D(svg.querySelector("path")?.getAttribute("d") ?? ""));
    return { size, pixels: Array.from(context.getImageData(0, 0, size, size).data) };
  });
  return jsQR(Uint8ClampedArray.from(drawn.pixels), drawn.size, drawn.size, { inversionAttempts: "dontInvert" })?.data;
}

async function signInWithPassword(page: Page, email: string, password = PASSWORD, path = "/sign-in?next=%2Faccount"): Promise<void> {
  await page.goto(path);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

async function onAccount(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("heading", { level: 1, name: "Sign-in and security" })).toBeVisible();
}

async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
}

/** Chromium's virtual authenticator on this page: a platform one that keeps passkeys and verifies the person. */
async function virtualAuthenticator(page: Page): Promise<void> {
  const client = await page.context().newCDPSession(page);
  await client.send("WebAuthn.enable");
  await client.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
}

async function addPasskey(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Add a passkey" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a passkey" });
  await dialog.getByLabel("Name").fill("This laptop");
  await dialog.getByRole("button", { name: "Add passkey" }).click();
  await expect(page.getByRole("region", { name: "Passkeys" }).getByText("This laptop")).toBeVisible();
}

test.describe("signing in", () => {
  test("with a password, back to the page asked for", async ({ page }) => {
    const user = await makeUser(page.request, "password");
    await signInWithPassword(page, user.email);
    await onAccount(page);
    await expect(page.getByText(`Signed in as ${user.email}`)).toBeVisible();
  });

  test("a wrong password says so and signs nobody in", async ({ page }) => {
    const user = await makeUser(page.request, "wrong");
    await signInWithPassword(page, user.email, "not the one at all");
    await expect(page.getByRole("alert")).toHaveText("That email and password don't match an account here.");
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);
  });

  test("with a password, then the authenticator app's code", async ({ page }) => {
    const user = await makeUser(page.request, "totp", { totp: true });
    await signInWithPassword(page, user.email);
    await expect(page.getByRole("heading", { level: 1, name: "One more step" })).toBeFocused();
    await page.getByLabel("Code from your app").fill(totp(user.totp));
    await page.getByRole("button", { name: "Continue" }).click();
    await onAccount(page);
  });

  test("with a password, then a recovery code made on the account page", async ({ page, browser }) => {
    const user = await makeUser(page.request, "recovery", { totp: true });
    await signInWithPassword(page, user.email);
    await page.getByLabel("Code from your app").fill(totp(user.totp));
    await page.getByRole("button", { name: "Continue" }).click();
    await onAccount(page);
    const app = page.getByRole("region", { name: "Authenticator app" });
    await expect(app.getByText("On", { exact: true })).toBeVisible();
    await app.getByRole("button", { name: "Make new codes" }).click();
    await page.getByRole("dialog", { name: "Make new recovery codes?" }).getByRole("button", { name: "Make new codes" }).click();
    const shown = page.getByRole("list", { name: "Your recovery codes" }).getByRole("listitem");
    await expect(shown).toHaveCount(10);
    const codes = await shown.allInnerTexts();
    await page.getByRole("button", { name: "I've saved them" }).click();
    await expect(app.getByText("10 of 10 left.", { exact: false })).toBeVisible();

    const other = await browser.newPage();
    await signInWithPassword(other, user.email);
    await other.getByText("Can't use either?").click();
    await other.getByLabel("Recovery code").fill(codes[0] ?? "");
    await other.getByRole("button", { name: "Use recovery code" }).click();
    await onAccount(other);
    await expect(other.getByRole("region", { name: "Authenticator app" }).getByText("9 of 10 left.", { exact: false })).toBeVisible();
    await other.close();
  });

  test("with a passkey alone, or a password then the passkey, once one is added", async ({ page }) => {
    await virtualAuthenticator(page);
    const user = await makeUser(page.request, "passkey");
    await signInWithPassword(page, user.email);
    await onAccount(page);
    await addPasskey(page);
    await signOut(page);

    await page.goto("/sign-in?next=%2Faccount");
    await page.getByRole("button", { name: "Sign in with a passkey" }).click();
    await onAccount(page); // never a second step after a passkey alone
    await signOut(page);

    await signInWithPassword(page, user.email);
    await expect(page.getByRole("heading", { level: 1, name: "One more step" })).toBeVisible();
    await page.getByRole("button", { name: "Use a passkey" }).click();
    await onAccount(page);
  });

  test("with a code by email", async ({ page }) => {
    const user = await makeUser(page.request, "code");
    await page.goto("/sign-in?next=%2Faccount");
    await page.getByLabel("Email").fill(user.email);
    await page.getByRole("button", { name: "Email me a code instead" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();
    const [, code] = await mailed(page.request, user.email, /(?<![\w-])(\d{6})(?![\w-])/);
    await page.getByLabel("Code").fill(code ?? "");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await onAccount(page);
  });

  test("with a link by email, only once it's confirmed", async ({ page }) => {
    const user = await makeUser(page.request, "link");
    await page.goto("/sign-in");
    await page.getByLabel("Email").fill(user.email);
    await page.getByRole("button", { name: "Email me a code instead" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();
    const [link] = await mailed(page.request, user.email, /\S*\/auth\/link\?token=\S+/);
    await page.goto(pathOf(link));
    await expect(page.getByRole("heading", { level: 1, name: "Sign in here?" })).toBeVisible();
    await expect(page).toHaveURL(/\/auth\/link$/); // the token is out of the address bar
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in/); // opening the link signed nobody in
    await page.goto(pathOf(link));
    await page.getByRole("button", { name: "Sign me in" }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.goto("/account");
    await onAccount(page);
  });
});

test("Sign out on the account page signs out, then goes home", async ({ page }) => {
  // The frame signs out once the move home is drawn. React Router draws a move in a transition,
  // after its navigate() has settled, so the frame went home and stayed signed in (found in K4.5).
  const user = await makeUser(page.request, "sign-out");
  await signInWithPassword(page, user.email);
  await onAccount(page);
  await page.getByRole("banner").getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("banner").getByRole("link", { name: "Sign in" })).toBeVisible();
  await page.goto("/account");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);
});

test("signing up, then confirming the address from its mail", async ({ page }) => {
  const email = address("new");
  await page.goto("/sign-up");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();
  const [link] = await mailed(page.request, email, /\S*\/auth\/verify\?token=\S+/);
  await page.goto(pathOf(link));
  await page.getByRole("button", { name: "Confirm my email" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Email confirmed" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in now" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/account");
  await expect(page.getByRole("region", { name: "Email" }).getByText("Confirmed", { exact: true })).toBeVisible();
});

test("resetting a forgotten password, which signs every device out", async ({ page, browser }) => {
  const user = await makeUser(page.request, "reset");
  const before = await browser.newPage();
  await signInWithPassword(before, user.email);
  await onAccount(before);

  await page.goto("/sign-in");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Reset password" })).toBeVisible();
  await page.getByLabel("Email").fill(user.email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByText(`If ${user.email} belongs to an account`)).toBeVisible();
  const [link] = await mailed(page.request, user.email, /\S*\/auth\/reset\?token=\S+/);
  await page.goto(pathOf(link));
  await page.getByLabel("New password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Password saved" })).toBeVisible();

  await before.reload();
  await expect(before).toHaveURL(/\/sign-in/);
  await before.close();
  await signInWithPassword(page, user.email, NEW_PASSWORD);
  await onAccount(page);
});

test.describe("the account", () => {
  test("sets up the authenticator app with its key and a code, then removes it", async ({ page }) => {
    const user = await makeUser(page.request, "app");
    await signInWithPassword(page, user.email);
    await onAccount(page);
    const app = page.getByRole("region", { name: "Authenticator app" });
    await app.getByRole("button", { name: "Set up" }).click();
    const setting = page.getByRole("dialog", { name: "Set up an authenticator app" });
    const key = (await setting.getByLabel("Your key").innerText()).replace(/\s/g, "");
    for (const [name, canvas] of Object.entries(THEMES)) {
      await theme(page, name, canvas);
      const read = await scanQr(page); // dark on light in either theme, holding this key
      expect(read, name).toMatch(/^otpauth:\/\/totp\//);
      expect(new URL(read ?? "").searchParams.get("secret"), name).toBe(key);
    }
    await setting.getByLabel("Code from your app").fill(totp(key));
    await setting.getByRole("button", { name: "Turn it on" }).click();
    await expect(page.getByRole("list", { name: "Your recovery codes" }).getByRole("listitem")).toHaveCount(10);
    await page.getByRole("button", { name: "I've saved them" }).click();
    await expect(app.getByText("On", { exact: true })).toBeVisible();

    await app.getByRole("button", { name: "Remove the authenticator app" }).click();
    await page.getByRole("dialog", { name: "Remove your authenticator app?" }).getByRole("button", { name: "Remove app" }).click();
    await expect(app.getByText("Off", { exact: true })).toBeVisible();
  });

  test("signs another device out, and every other", async ({ page, browser }) => {
    const user = await makeUser(page.request, "devices");
    const phoneContext = await browser.newContext({ userAgent: IPHONE });
    const phone = await phoneContext.newPage();
    await signInWithPassword(phone, user.email);
    await onAccount(phone);
    await signInWithPassword(page, user.email);
    await onAccount(page);

    const devices = page.getByRole("region", { name: "Signed-in devices" });
    await expect(devices.getByText("This device")).toBeVisible();
    await devices.getByRole("button", { name: "Sign out Safari on iPhone" }).click();
    await expect(page.getByText("Safari on iPhone is signed out.")).toBeVisible();
    await phone.reload();
    await expect(phone).toHaveURL(/\/sign-in/);

    await signInWithPassword(phone, user.email);
    await onAccount(phone);
    await page.reload();
    await devices.getByRole("button", { name: "Sign out everywhere else" }).click();
    await expect(page.getByText("Every other device is signed out.")).toBeVisible();
    await phone.reload();
    await expect(phone).toHaveURL(/\/sign-in/);
    await page.reload();
    await onAccount(page);
    await phoneContext.close();
  });
});

const THEMES = {
  "machined-light": "rgb(236, 236, 234)",
  "vibrant-mindz": "rgb(7, 10, 22)",
} as const;

async function axe(page: Page): Promise<string[]> {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  return violations.filter((each) => each.impact === "serious" || each.impact === "critical").map((each) => `${each.id}: ${each.help}`);
}

async function theme(page: Page, name: string, canvas: string): Promise<void> {
  await page.evaluate(async (chosen) => {
    document.documentElement.dataset.theme = chosen;
    document.body.getBoundingClientRect();
    await Promise.all(document.getAnimations().map((animation) => animation.finished));
  }, name);
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor)).toBe(canvas);
}

for (const [name, canvas] of Object.entries(THEMES)) {
  test(`axe finds no serious or critical problem on the account's pages in ${name}, a dialog open or shut`, async ({ page }) => {
    const user = await makeUser(page.request, "axe", { totp: true });
    await signInWithPassword(page, user.email);
    await page.getByLabel("Code from your app").fill(totp(user.totp));
    await page.getByRole("button", { name: "Continue" }).click();
    await onAccount(page);
    for (const path of ["/account", "/account/notifications", "/account/activity"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await theme(page, name, canvas);
      expect(await axe(page), path).toEqual([]);
    }
    await page.goto("/account");
    await page.getByRole("region", { name: "Email" }).getByRole("button", { name: "Change email" }).click();
    await expect(page.getByRole("dialog", { name: "Change your email" })).toBeVisible();
    await theme(page, name, canvas);
    expect(await axe(page)).toEqual([]);
  });

  test(`axe finds no serious or critical problem on the second step and a sign-in's refusal in ${name}`, async ({ page }) => {
    const user = await makeUser(page.request, "axe-step", { totp: true });
    await signInWithPassword(page, user.email, "not the one at all");
    await expect(page.getByRole("alert")).toBeVisible();
    await theme(page, name, canvas);
    expect(await axe(page)).toEqual([]);
    await signInWithPassword(page, user.email);
    await expect(page.getByRole("heading", { level: 1, name: "One more step" })).toBeVisible();
    await theme(page, name, canvas);
    expect(await axe(page)).toEqual([]);
  });
}
