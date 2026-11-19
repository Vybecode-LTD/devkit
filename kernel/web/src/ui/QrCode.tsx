/**
 * A QR code, for a phone's camera: the authenticator app's key at setup.
 * uqr makes the module grid (error correction M, the standard's 4-module
 * quiet zone); it's drawn here as one SVG path, a run of dark modules in a
 * row at a time, with no markup injected.
 *
 * A camera reads dark modules on a light ground, whatever the page's theme,
 * so the code takes the system's own light canvas and text colours
 * (`color-scheme: light`, kit.css), never a theme's, and forced colours leave
 * it alone. Its label names it; the key it holds is shown beside it as words.
 */
import { useMemo } from "react";
import { encode } from "uqr";

/** The path of a grid's dark modules: each run in a row is one rectangle. */
export function qrPath(grid: readonly (readonly boolean[])[]): string {
  const parts: string[] = [];
  grid.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      if (!row[x]) {
        x += 1;
        continue;
      }
      let end = x;
      while (end < row.length && row[end]) end += 1;
      parts.push(`M${String(x)} ${String(y)}h${String(end - x)}v1h-${String(end - x)}z`);
      x = end;
    }
  });
  return parts.join("");
}

export type QrCodeProps = {
  /** What the code holds. */
  value: string;
  /** What it is, for a screen reader: "A QR code for your authenticator app". */
  label: string;
  /** Its width and height in CSS pixels. */
  size?: number;
};

export function QrCode({ value, label, size = 200 }: QrCodeProps) {
  const { grid, modules } = useMemo(() => {
    const made = encode(value, { ecc: "M", border: 4 });
    return { grid: made.data, modules: made.size };
  }, [value]);
  return (
    <svg
      className="mf-qr"
      role="img"
      aria-label={label}
      viewBox={`0 0 ${String(modules)} ${String(modules)}`}
      width={size}
      height={size}
      shapeRendering="crispEdges"
    >
      <path d={qrPath(grid)} fill="currentColor" />
    </svg>
  );
}
