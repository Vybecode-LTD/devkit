// Landing on a place (`place.ts`) and the scroll memory that uses it (`ScrollMemory.tsx`).
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithKernel } from "../../testing";
import { OPENED_BY_LINK, entryKey, holdScroll, landOn, readPositions, reveal, savePositions } from "./place";
import { ScrollMemory, placeNamed } from "./ScrollMemory";

let scrollY = 0;
const scrollTo = vi.fn((options: ScrollToOptions) => {
  scrollY = options.top ?? 0;
});

beforeEach(() => {
  scrollY = 0;
  vi.stubGlobal("scrollTo", scrollTo);
  vi.spyOn(window, "scrollY", "get").mockImplementation(() => scrollY);
  scrollTo.mockClear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("reveal", () => {
  it("opens every shut section around the place, outermost first, and marks them as opened by a link", async () => {
    render(
      <details data-testid="outer">
        <summary>Outer</summary>
        <details data-testid="inner">
          <summary>Inner</summary>
          <p id="place">Here</p>
        </details>
      </details>,
    );
    const opened: string[] = [];
    for (const id of ["outer", "inner"]) {
      screen.getByTestId(id).addEventListener("toggle", () => opened.push(id));
    }
    reveal(screen.getByText("Here"));
    expect(screen.getByTestId<HTMLDetailsElement>("outer").open).toBe(true);
    expect(screen.getByTestId<HTMLDetailsElement>("inner").open).toBe(true);
    await waitFor(() => {
      expect(opened).toEqual(["outer", "inner"]);
    });
    expect(screen.getByTestId("outer")).toHaveAttribute(OPENED_BY_LINK);
  });
});

describe("landOn", () => {
  it("waits for the place, scrolls to it and focuses it when it can take focus, until the reader acts", async () => {
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    const stop = landOn("late");
    const late = document.createElement("h2");
    late.id = "late";
    late.tabIndex = -1;
    await act(async () => {
      document.body.append(late);
      await Promise.resolve();
    });
    expect(scrolled.mock.contexts).toContain(late);
    expect(late).toHaveFocus();
    window.dispatchEvent(new KeyboardEvent("keydown"));
    scrolled.mockClear();
    await act(async () => {
      document.body.append(document.createElement("p"));
      await Promise.resolve();
    });
    expect(scrolled).not.toHaveBeenCalled();
    stop();
    late.remove();
  });

  it("only opens the sections around it when the scroll is restored instead", () => {
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    render(
      <details data-testid="shut">
        <summary>Shut</summary>
        <p id="inside">Inside</p>
      </details>,
    );
    const stop = landOn("inside", { scroll: false });
    expect(screen.getByTestId<HTMLDetailsElement>("shut").open).toBe(true);
    expect(scrolled).not.toHaveBeenCalled();
    stop();
  });

  it("gives up after its patience", () => {
    vi.useFakeTimers();
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    landOn("never", { patienceMs: 100 });
    vi.advanceTimersByTime(100);
    const never = document.createElement("p");
    never.id = "never";
    document.body.append(never);
    expect(scrolled).not.toHaveBeenCalled();
    never.remove();
  });
});

describe("holdScroll", () => {
  it("scrolls back to where the reader was, and says when it's there", () => {
    const done = vi.fn();
    holdScroll(300, { onDone: done });
    expect(scrollTo).toHaveBeenCalledWith({ top: 300, left: 0, behavior: "instant" });
    expect(done).toHaveBeenCalledOnce();
  });
});

describe("the positions kept", () => {
  it("names an entry by its key, or by its address for one the browser made", () => {
    expect(entryKey({ key: "abc", pathname: "/a", search: "", hash: "" })).toBe("abc");
    expect(entryKey({ key: "default", pathname: "/a", search: "?q", hash: "#h" })).toBe("default:/a?q#h");
  });

  it("are kept through a reload, the newest fifty, and none when storage refuses", () => {
    savePositions(new Map(Array.from({ length: 60 }, (_, at) => [`k${String(at)}`, at])));
    const read = readPositions();
    expect(read.size).toBe(50);
    expect(read.get("k59")).toBe(59);
    window.sessionStorage.setItem("mf_scroll_positions", "not json");
    expect(readPositions().size).toBe(0);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => {
      savePositions(new Map([["a", 1]]));
    }).not.toThrow();
  });

  it("reads the place an address names, and a malformed one as written", () => {
    expect(placeNamed("#caf%C3%A9")).toBe("café");
    expect(placeNamed("#100%")).toBe("100%");
    expect(placeNamed("")).toBe("");
  });
});

describe("ScrollMemory", () => {
  it("starts a new page at the top, returns to where the reader was on Back, and lands on a #place", async () => {
    const { router } = renderWithKernel(<ScrollMemory />, { path: "/one" });
    expect(window.history.scrollRestoration).toBe("manual");
    scrollY = 480;
    window.dispatchEvent(new Event("scroll"));
    await act(() => router.navigate("/two"));
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 0, left: 0, behavior: "instant" });
    await act(() => router.navigate(-1));
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 480, left: 0, behavior: "instant" });

    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    const place = document.createElement("h2");
    place.id = "billing";
    document.body.append(place);
    await act(() => router.navigate("/three#billing"));
    expect(scrolled.mock.contexts).toContain(place);
    place.remove();
  });

  it("lands on a new #place on the same page, opening its sections, and leaves the scroll alone otherwise (Codex on #82)", async () => {
    const { router } = renderWithKernel(<ScrollMemory />, { path: "/account" });
    const section = document.createElement("details");
    const place = document.createElement("h2");
    place.id = "passkeys";
    section.append(place);
    document.body.append(section);
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    scrollTo.mockClear();
    await act(() => router.navigate("/account#passkeys"));
    expect(scrolled.mock.contexts).toContain(place);
    expect(section.open).toBe(true);
    await act(() => router.navigate("/account?tab=two#passkeys"));
    await act(() => router.navigate("/account"));
    expect(scrollTo).not.toHaveBeenCalled();
    section.remove();
  });

  it("stops the last landing when the entry changes with the same place, and doesn't land again (CodeRabbit on #82)", async () => {
    const { router } = renderWithKernel(<ScrollMemory />, { path: "/one" });
    const place = document.createElement("h2");
    place.id = "billing";
    document.body.append(place);
    await act(() => router.navigate("/one#billing"));
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    await act(() => router.navigate("/one?tab=two#billing"));
    await act(async () => {
      document.body.append(document.createElement("p"));
      await Promise.resolve();
    });
    expect(scrolled).not.toHaveBeenCalled();
    place.remove();
  });

  it("keeps the positions when the page is hidden, and gives the browser its restoration back", () => {
    const before = window.history.scrollRestoration;
    const { unmount } = renderWithKernel(<ScrollMemory />, { path: "/one" });
    scrollY = 120;
    window.dispatchEvent(new Event("scroll"));
    window.dispatchEvent(new Event("pagehide"));
    expect(window.sessionStorage.getItem("mf_scroll_positions")).toContain("120");
    unmount();
    expect(window.history.scrollRestoration).toBe(before);
  });
});

describe("cubic on #82", () => {
  it("focuses a place that couldn't take the focus, so Tab starts there", () => {
    const place = document.createElement("h2");
    place.id = "plain";
    document.body.append(place);
    const stop = landOn("plain");
    expect(place).toHaveFocus();
    expect(place).toHaveAttribute("tabindex", "-1");
    stop();
    place.remove();
  });

  it("focuses the place on a restore too, without scrolling", () => {
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    const place = document.createElement("h2");
    place.id = "restored";
    document.body.append(place);
    const stop = landOn("restored", { scroll: false });
    expect(place).toHaveFocus();
    expect(scrolled).not.toHaveBeenCalled();
    stop();
    place.remove();
  });

  it("tries again when the page grows without a node added, as an image loading does", () => {
    let grew: () => void = () => undefined;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          grew = callback;
        }
        observe() {
          // Watched.
        }
        disconnect() {
          grew = () => undefined;
        }
      },
    );
    scrollTo.mockImplementation(() => {
      // Too short yet: the scroll stops at 100.
      scrollY = 100;
    });
    const done = vi.fn();
    holdScroll(300, { onDone: done });
    expect(done).not.toHaveBeenCalled();
    scrollTo.mockImplementation((options: ScrollToOptions) => {
      scrollY = options.top ?? 0;
    });
    grew();
    expect(done).toHaveBeenCalledOnce();
  });
});
