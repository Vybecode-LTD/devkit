// The UI kit as Chromium draws it (K4.4; harness/web/kit.html): axe finds no
// serious or critical problem in either theme; every control's boundary as a
// whole reaches 3:1 against what's behind it (WCAG 1.4.11, contract change
// 14), which axe doesn't check; the admin's focus rings and the site's
// outline, reached with real Tab presses; the table's scroller bringing a
// half-hidden control fully into view (the owner, 2026-11-18); and the save
// bar keeping the focus clear of itself (WCAG 2.4.11).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const THEMES = {
  "machined-light": "rgb(236, 236, 234)",
  "vibrant-mindz": "rgb(7, 10, 22)",
} as const;

async function open(page: Page, theme: string, canvas: string): Promise<void> {
  await page.goto("/kit.html");
  await expect(page.getByRole("heading", { level: 1, name: "UI kit" })).toBeVisible();
  await page.evaluate((name) => {
    document.documentElement.dataset.theme = name;
  }, theme);
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor)).toBe(canvas);
}

async function axe(page: Page): Promise<string[]> {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  return violations.filter((each) => each.impact === "serious" || each.impact === "critical").map((each) => `${each.id}: ${each.help}`);
}

/** The box-shadow a token draws, as the browser computes it. */
async function shadowOf(page: Page, token: string): Promise<string> {
  return page.evaluate((name) => {
    const probe = document.createElement("div");
    probe.style.boxShadow = `var(${name})`;
    document.body.append(probe);
    const drawn = getComputedStyle(probe).boxShadow;
    probe.remove();
    return drawn;
  }, token);
}

async function focusedShadow(page: Page): Promise<{ shadow: string; outline: string }> {
  return page.evaluate(() => {
    const at = document.activeElement;
    if (!(at instanceof HTMLElement)) throw new Error("Nothing has the focus.");
    const style = getComputedStyle(at);
    return { shadow: style.boxShadow, outline: `${style.outlineStyle} ${style.outlineColor}` };
  });
}

for (const [theme, canvas] of Object.entries(THEMES)) {
  test.describe(`the kit in ${theme}`, () => {
    test("axe finds no serious or critical problem, the dialog open or shut", async ({ page }) => {
      await open(page, theme, canvas);
      expect(await axe(page)).toEqual([]);
      await page.getByRole("button", { name: "Open a dialog" }).click();
      await expect(page.getByRole("dialog", { name: "Delete this role?" })).toBeVisible();
      expect(await axe(page)).toEqual([]);
    });

    test("every control's boundary reaches 3:1 against what's behind it, and a switch's knob against its track", async ({ page }) => {
      await open(page, theme, canvas);
      const measured = await page.evaluate(() => {
        type Colour = { r: number; g: number; b: number; a: number };
        const parse = (text: string): Colour => {
          const rgb = /^rgba?\(([^)]+)\)$/.exec(text);
          const srgb = /^color\(srgb ([^)]+)\)$/.exec(text);
          const parts = (rgb?.[1] ?? srgb?.[1])?.split(/[\s,/]+/).filter(Boolean).map(Number);
          if (!parts || parts.length < 3) throw new Error(`A colour this test can't read: ${text}`);
          const [r = 0, g = 0, b = 0, a = 1] = parts;
          return rgb ? { r: r / 255, g: g / 255, b: b / 255, a } : { r, g, b, a };
        };
        const over = (top: Colour, under: Colour): Colour => {
          const a = top.a + under.a * (1 - top.a);
          const mix = (t: number, u: number) => (t * top.a + u * under.a * (1 - top.a)) / a;
          return { r: mix(top.r, under.r), g: mix(top.g, under.g), b: mix(top.b, under.b), a };
        };
        const luminance = ({ r, g, b }: Colour) => {
          const linear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
          return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
        };
        const ratio = (one: Colour, two: Colour) => {
          const [high, low] = [luminance(one), luminance(two)].sort((x, y) => y - x) as [number, number];
          return (high + 0.05) / (low + 0.05);
        };
        const behind = (element: Element): Colour => {
          const layers: Colour[] = [];
          for (let at = element.parentElement; at; at = at.parentElement) {
            const colour = parse(getComputedStyle(at).backgroundColor);
            if (colour.a > 0) layers.push(colour);
            if (colour.a >= 1) break;
          }
          return layers.reverse().reduce((under, layer) => over(layer, under), { r: 1, g: 1, b: 1, a: 1 });
        };
        const drawn = (element: Element) => {
          const style = getComputedStyle(element);
          const back = behind(element);
          const fill = over(parse(style.backgroundColor), back);
          const edged = Number.parseFloat(style.borderTopWidth) >= 1;
          const edge = edged ? over(parse(style.borderTopColor), fill) : fill;
          return { back, fill, boundary: Math.max(ratio(edge, back), ratio(fill, back)) };
        };
        const label = (element: Element) =>
          `${element.tagName.toLowerCase()} ${element.getAttribute("aria-label") ?? element.textContent.trim().slice(0, 30)} (${element.getAttribute("data-kit-boundary") ?? "switch"})`;
        const controls = [...document.querySelectorAll("[data-kit-boundary], .mf-switch")];
        const boundaries = controls.map((element) => ({ control: label(element), ratio: drawn(element).boundary }));
        const knobs = [...document.querySelectorAll(".mf-switch")].map((track) => {
          const knob = track.querySelector(".mf-switch-knob");
          if (!knob) throw new Error("A switch without its knob.");
          const trackFill = drawn(track).fill;
          return { control: `${label(track)} knob`, ratio: ratio(over(parse(getComputedStyle(knob).backgroundColor), trackFill), trackFill) };
        });
        return [...boundaries, ...knobs];
      });
      // A filled button, five fields, a pressed chip, two switches, and their knobs.
      expect(measured).toHaveLength(11);
      const short = measured.filter((each) => each.ratio < 3).map((each) => `${each.control}: ${each.ratio.toFixed(2)}:1`);
      expect(short).toEqual([]);
    });

    test("focus is the admin's ring, with a gap on a filled or pressed control and over a selected tab's edge; the site keeps its outline", async ({ page }) => {
      await open(page, theme, canvas);
      const ring = await shadowOf(page, "--mf-shadow-focus-ring");
      const gap = await shadowOf(page, "--mf-shadow-focus-ring-gap");
      const tab = await shadowOf(page, "--mf-shadow-tab-current-focus");
      expect(ring).not.toBe("none");

      await page.getByRole("button", { name: "Discard" }).first().focus();
      await page.keyboard.press("Shift+Tab");
      await expect(page.getByRole("button", { name: "Save and go live" }).first()).toBeFocused();
      expect((await focusedShadow(page)).shadow).toBe(gap);
      await page.keyboard.press("Tab");
      const discard = await focusedShadow(page);
      expect(discard.shadow).toBe(ring);
      expect(discard.outline).toBe("solid rgba(0, 0, 0, 0)");

      await page.getByRole("button", { name: "Scheduled" }).focus();
      await page.keyboard.press("Shift+Tab");
      await expect(page.getByRole("button", { name: "Drafts" })).toBeFocused();
      expect((await focusedShadow(page)).shadow).toBe(gap);

      await page.getByRole("switch", { name: "Open sign-up" }).focus();
      await page.keyboard.press("Tab");
      await page.keyboard.press("Shift+Tab");
      expect((await focusedShadow(page)).shadow).toBe(gap);

      await page.getByRole("tab", { name: "Site" }).focus();
      await page.keyboard.press("ArrowRight");
      await page.keyboard.press("ArrowLeft");
      await expect(page.getByRole("tab", { name: "Site" })).toBeFocused();
      expect((await focusedShadow(page)).shadow).toBe(tab);

      await page.getByRole("button", { name: "Use a passkey" }).focus();
      await page.keyboard.press("Shift+Tab");
      await expect(page.getByRole("button", { name: "Sign in" })).toBeFocused();
      const site = await page.evaluate(() => {
        const style = getComputedStyle(document.activeElement as Element);
        const focus = getComputedStyle(document.documentElement).getPropertyValue("--mf-color-focus");
        const probe = document.createElement("div");
        probe.style.color = focus;
        document.body.append(probe);
        const colour = getComputedStyle(probe).color;
        probe.remove();
        return { outline: `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`, offset: style.outlineOffset, shadow: style.boxShadow, colour };
      });
      expect(site).toEqual({ outline: `solid 2px ${site.colour}`, offset: "3px", shadow: "none", colour: site.colour });
    });
  });
}

test.describe("at a phone's width", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Tab brings a half-hidden button in a table's scroller fully into view, its ring clear of the edge", async ({ page }) => {
    await open(page, "vibrant-mindz", THEMES["vibrant-mindz"]);
    const scroller = page.locator('[data-kit="people"] .mf-table-scroll');
    const first = page.getByRole("button", { name: "Edit Ann Example" });
    // 30px of the button showing at the scroller's right edge: Chrome leaves
    // it as it is when 20px or more shows, so only the kit's handler can help.
    await scroller.evaluate((element, name) => {
      const button = [...element.querySelectorAll("button")].find((each) => each.textContent === name);
      if (!button) throw new Error("No such button.");
      element.scrollLeft = 0;
      const offset = button.getBoundingClientRect().left - element.getBoundingClientRect().left;
      element.scrollLeft = offset - element.clientWidth + 30;
    }, "Edit Ann Example");
    const before = await first.evaluate((button) => {
      const box = button.getBoundingClientRect();
      const frame = (button.closest(".mf-table-scroll") as HTMLElement).getBoundingClientRect();
      return frame.right - box.left;
    });
    expect(before).toBeGreaterThan(20);
    expect(before).toBeLessThan(40);

    await page.getByRole("heading", { name: /^History/ }).locator("..").focus();
    for (const name of ["Edit Ann Example", "Edit Bo Sample", "Edit Cy Placeholder"]) {
      await page.keyboard.press("Tab");
      const button = page.getByRole("button", { name });
      await expect(button).toBeFocused();
      const room = await button.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const frame = (element.closest(".mf-table-scroll") as HTMLElement).getBoundingClientRect();
        return { left: box.left - frame.left, right: frame.right - box.right };
      });
      // Its 4px ring shows on both sides: scroll-padding-inline keeps it 10px in.
      expect(room.left).toBeGreaterThanOrEqual(4);
      expect(room.right).toBeGreaterThanOrEqual(4);
    }
  });

  test("a table's scroller that holds nothing focusable is a tab stop with its ring drawn inside", async ({ page }) => {
    await open(page, "machined-light", THEMES["machined-light"]);
    await page.getByRole("button", { name: "Edit Cy Placeholder" }).focus();
    await page.keyboard.press("Tab");
    const scroller = page.locator('[data-kit="plain"] .mf-table-scroll');
    await expect(scroller).toBeFocused();
    expect((await focusedShadow(page)).shadow).toBe(await shadowOf(page, "--mf-shadow-focus-ring-inset"));
  });
});

test("the save bar keeps its room below what scrolls, so Tab never leaves a control under it (WCAG 2.4.11)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 640 });
  await open(page, "machined-light", THEMES["machined-light"]);
  const bar = page.getByRole("region", { name: "Changes not saved" });
  await expect(bar).toBeVisible();
  const { padding, height } = await bar.evaluate((element) => ({
    padding: getComputedStyle(document.documentElement).scrollPaddingBottom,
    height: Math.ceil(element.getBoundingClientRect().height),
  }));
  expect(padding).toBe(`${String(height + 24)}px`);

  await page.evaluate(() => {
    window.scrollTo(0, 0);
  });
  await page.getByRole("textbox", { name: "Setting 1" }).focus();
  for (let at = 2; at <= 6; at += 1) {
    await page.keyboard.press("Tab");
    const field = page.getByRole("textbox", { name: `Setting ${String(at)}` });
    await expect(field).toBeFocused();
    const clear = await field.evaluate((element) => {
      const top = (document.querySelector(".mf-save-bar") as HTMLElement).getBoundingClientRect().top;
      return top - element.getBoundingClientRect().bottom;
    });
    expect(clear).toBeGreaterThanOrEqual(4);
  }
});
