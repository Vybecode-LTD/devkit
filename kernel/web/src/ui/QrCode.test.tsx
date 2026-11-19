import { render, screen } from "@testing-library/react";
import jsQR from "jsqr";
import { describe, expect, it } from "vitest";

import { QrCode, qrPath } from "./QrCode";

/** The drawn path's dark modules, back on a grid: each `M x y h n v1 h-n z` is a run of n. */
function gridOf(path: string, size: number): boolean[][] {
  const grid = Array.from({ length: size }, () => Array<boolean>(size).fill(false));
  for (const [, x, y, run] of path.matchAll(/M(\d+) (\d+)h(\d+)v1h-\3z/g)) {
    for (let at = 0; at < Number(run); at += 1) {
      const row = grid[Number(y)];
      if (row) row[Number(x) + at] = true;
    }
  }
  return grid;
}

/** What a camera would read: the grid at `scale` pixels a module, black on white, through jsQR. */
function scan(grid: boolean[][], scale = 4): string | undefined {
  const size = grid.length * scale;
  const pixels = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const dark = grid[Math.floor(y / scale)]?.[Math.floor(x / scale)] ?? false;
      const at = (y * size + x) * 4;
      pixels.set([dark ? 0 : 255, dark ? 0 : 255, dark ? 0 : 255, 255], at);
    }
  }
  return jsQR(pixels, size, size)?.data;
}

const URI = "otpauth://totp/MechFrame%20test%20site:ann%40mechframe.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=MechFrame%20test%20site";

describe("QrCode", () => {
  it("draws a code a camera reads as the value it was given", () => {
    render(<QrCode value={URI} label="A QR code for your authenticator app" />);
    const code = screen.getByRole("img", { name: "A QR code for your authenticator app" });
    const [, , width] = (code.getAttribute("viewBox") ?? "").split(" ").map(Number);
    const path = code.querySelector("path")?.getAttribute("d") ?? "";
    expect(width).toBeGreaterThan(21 + 8); // past version 1, with its quiet zone
    expect(scan(gridOf(path, width ?? 0))).toBe(URI);
    expect(code).toHaveAttribute("width", "200");
    expect(code.querySelector("path")).toHaveAttribute("fill", "currentColor");
  });

  it("keeps the standard's quiet zone of 4 light modules all round", () => {
    render(<QrCode value="hello" label="A code" size={120} />);
    const code = screen.getByRole("img", { name: "A code" });
    const [, , width = 0] = (code.getAttribute("viewBox") ?? "").split(" ").map(Number);
    const grid = gridOf(code.querySelector("path")?.getAttribute("d") ?? "", width);
    const edge = [...grid.slice(0, 4), ...grid.slice(-4), ...grid.map((row) => [...row.slice(0, 4), ...row.slice(-4)])];
    expect(edge.flat().some(Boolean)).toBe(false);
    expect(code).toHaveAttribute("width", "120");
  });

  it("draws each run of dark modules in a row as one rectangle", () => {
    expect(
      qrPath([
        [false, true, true, false, true],
        [true, false, false, false, false],
      ]),
    ).toBe("M1 0h2v1h-2zM4 0h1v1h-1zM0 1h1v1h-1z");
    expect(qrPath([[false, false]])).toBe("");
  });

  it("isn't read when it's drawn wrong: the check above can fail", () => {
    render(<QrCode value={URI} label="A code" />);
    const code = screen.getByRole("img", { name: "A code" });
    const [, , width = 0] = (code.getAttribute("viewBox") ?? "").split(" ").map(Number);
    const grid = gridOf(code.querySelector("path")?.getAttribute("d") ?? "", width);
    expect(scan(grid)).toBe(URI); // the control: whole, it reads
    // Without its top-left finder pattern (7 modules square, inside the quiet zone), nothing does.
    const blanked = grid.map((row, y) => row.map((dark, x) => (y >= 4 && y < 11 && x >= 4 && x < 11 ? false : dark)));
    expect(scan(blanked)).toBeUndefined();
  });
});
