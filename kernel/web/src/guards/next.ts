/**
 * Where a sign-in may send the person back to (K4 contract §2): only a path
 * on this site. Its path part has one leading slash and never `//` or a
 * backslash (either could name another host); its query and fragment are
 * data, so a `//` there is fine (cubic on #79). No control character anywhere.
 */
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f]/;

/** The part before any query or fragment. */
export function pathPart(path: string): string {
  return path.split(/[?#]/, 1)[0] ?? "";
}

/** `next` if it's a path on this site, else `null`. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next?.startsWith("/") || CONTROL.test(next)) return null;
  const path = pathPart(next);
  if (path.includes("//") || path.includes("\\")) return null;
  return next;
}

/** The sign-in page's address that brings the person back to `path`. */
export function signInFor(path: string): string {
  const next = safeNext(path);
  return next === null || next === "/" ? "/sign-in" : `/sign-in?next=${encodeURIComponent(next)}`;
}
