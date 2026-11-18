/**
 * Where a sign-in may send the person back to (K4 contract §2): only a path
 * on this site. One leading slash, never `//` or a backslash anywhere (either
 * could name another host), and no control character.
 */
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f]/;

/** `next` if it's a path on this site, else `null`. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next?.startsWith("/")) return null;
  if (next.includes("//") || next.includes("\\") || CONTROL.test(next)) return null;
  return next;
}

/** The sign-in page's address that brings the person back to `path`. */
export function signInFor(path: string): string {
  const next = safeNext(path);
  return next === null || next === "/" ? "/sign-in" : `/sign-in?next=${encodeURIComponent(next)}`;
}
