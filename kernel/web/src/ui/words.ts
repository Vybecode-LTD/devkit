/** How the kit says lists, names and times in a sentence (from VybeSite's `lib/settingsSave.ts`). */
import type { ReactNode } from "react";

/** Whether a part holds anything to draw: `0` does; nothing, `false` and `""` don't (cubic on #82). */
export function shows(node: ReactNode): boolean {
  return node !== undefined && node !== null && typeof node !== "boolean" && node !== "";
}

/** “Port”, “Host” and “Name”. */
export function and(words: readonly string[]): string {
  if (words.length <= 1) return words[0] ?? "";
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1] ?? ""}`;
}

/** A field's label inside a sentence, quoted as the server's sentences quote it. */
export function quoted(label: string): string {
  return `“${label}”`;
}

/** A moment, as the reader's own locale writes it: "18 Nov 2026, 21:40"; blank for no moment. */
export function when(iso: string | null | undefined): string {
  if (!iso) return "";
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? "" : at.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
