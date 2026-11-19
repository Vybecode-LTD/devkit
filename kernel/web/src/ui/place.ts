/**
 * Landing on a place in a page (ported from VybeSite's `lib/landOn.ts` and
 * `lib/scrollMemory.ts`): the element an address's `#id` names, and the
 * scroll position Back and Forward return to. Both wait for the page to grow:
 * a page that loads its data after it draws is too short at first, and the
 * part a link names isn't there yet. Both stop the moment the reader scrolls,
 * taps or presses a key, so they never fight them.
 */

/** Set on a `<details>` a link opened, so an `Accordion` doesn't remember it as the reader's choice. */
export const OPENED_BY_LINK = "data-opened-by-link";

/** What the reader does that stops a landing: theirs is the page now. */
const INTENTS = ["wheel", "touchstart", "keydown", "pointerdown"] as const;

/**
 * Opens every shut `<details>` the element sits in, and the element itself if
 * it is one, outermost first: a shut section's content isn't drawn, so there
 * would be nothing to scroll to.
 */
export function reveal(target: HTMLElement): void {
  const shut: HTMLDetailsElement[] = [];
  for (let at: HTMLElement | null = target; at; at = at.parentElement) {
    if (at instanceof HTMLDetailsElement && !at.open) shut.unshift(at);
  }
  for (const section of shut) {
    section.setAttribute(OPENED_BY_LINK, "");
    section.open = true;
  }
}

/** Watches the page until `done` says so, the reader acts, or `patienceMs` passes. Returns the stop. */
function watch(step: () => boolean, patienceMs: number, onStop?: () => void): () => void {
  let finished = false;
  const observer = new MutationObserver(() => {
    again();
  });
  const giveUp = window.setTimeout(stop, patienceMs);
  function stop(): void {
    if (finished) return;
    finished = true;
    observer.disconnect();
    grows?.disconnect();
    window.clearTimeout(giveUp);
    for (const intent of INTENTS) window.removeEventListener(intent, stop, true);
    onStop?.();
  }
  // The page growing with no node added (an image loading, words changed)
  // is followed too (cubic on #82).
  const grows = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(again);
  function again(): void {
    if (step()) stop();
  }
  for (const intent of INTENTS) window.addEventListener(intent, stop, true);
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  grows?.observe(document.body);
  if (step()) stop();
  return stop;
}

/**
 * Brings the element with this id into view once it exists, opening the
 * sections around it, and keeps it there while the page finishes loading
 * around it. Focused, made focusable if it isn't, so the next Tab starts
 * there and a screen reader reads it: `RouteFocus` leaves a page with a
 * place to this (cubic on #82).
 * `scroll: false` only opens the sections, for a page whose scroll position
 * is restored instead (Back, Forward, a reload).
 */
export function landOn(id: string, { patienceMs = 5000, scroll = true }: { patienceMs?: number; scroll?: boolean } = {}): () => void {
  let landed: HTMLElement | null = null;
  return watch(() => {
    const target = document.getElementById(id);
    if (!target) return false;
    if (landed !== target) {
      reveal(target);
      if (!target.hasAttribute("tabindex") && target.tabIndex < 0) target.setAttribute("tabindex", "-1");
      target.focus({ preventScroll: true });
    }
    if (scroll) target.scrollIntoView({ block: "start", behavior: "instant" });
    landed = target;
    // Keep watching: the page can still grow above it.
    return false;
  }, patienceMs);
}

/**
 * Scrolls to `y` and holds it there while the page grows to fit, stopping
 * once it gets there. Returns the stop, for an effect's cleanup.
 */
export function holdScroll(y: number, { patienceMs = 3000, onDone }: { patienceMs?: number; onDone?: () => void } = {}): () => void {
  return watch(
    () => {
      window.scrollTo({ top: y, left: 0, behavior: "instant" });
      return Math.abs(window.scrollY - y) < 2;
    },
    patienceMs,
    onDone,
  );
}

type Entry = { key: string; pathname: string; search: string; hash: string };

/**
 * A history entry's name: React Router's key for an entry it pushed, its
 * address for one the browser made (the first page of a visit is "default").
 */
export function entryKey({ key, pathname, search, hash }: Entry): string {
  return key && key !== "default" ? key : `default:${pathname}${search}${hash}`;
}

const STORE = "mf_scroll_positions";
/** A tab's history rarely matters further back than this. */
const KEEP = 50;

/** The positions this tab kept through a reload; none if storage refuses. */
export function readPositions(): Map<string, number> {
  try {
    const kept = JSON.parse(window.sessionStorage.getItem(STORE) ?? "{}") as Record<string, unknown>;
    return new Map(Object.entries(kept).filter((entry): entry is [string, number] => typeof entry[1] === "number"));
  } catch {
    return new Map();
  }
}

export function savePositions(positions: Map<string, number>): void {
  try {
    window.sessionStorage.setItem(STORE, JSON.stringify(Object.fromEntries([...positions].slice(-KEEP))));
  } catch {
    // Nowhere to keep them: a reload starts at the top.
  }
}
