import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SAVE_BAR_ROOM, SaveBar } from "./SaveBar";

const room = () => document.documentElement.style.getPropertyValue(SAVE_BAR_ROOM);

describe("SaveBar", () => {
  it("shows nothing, and takes no room, while nothing has changed", () => {
    render(<SaveBar changes={0} onSave={vi.fn()} onDiscard={vi.fn()} />);
    expect(screen.queryByRole("region")).toBeNull();
    expect(room()).toBe("");
  });

  it("says how many changes aren't saved, and offers Discard and Save", async () => {
    const save = vi.fn();
    const discard = vi.fn();
    const { rerender } = render(<SaveBar changes={1} onSave={save} onDiscard={discard} saveLabel="Save and go live" />);
    expect(screen.getByRole("region", { name: "Changes not saved" })).toHaveTextContent("1 change not saved");
    await userEvent.click(screen.getByRole("button", { name: "Save and go live" }));
    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(save).toHaveBeenCalledOnce();
    expect(discard).toHaveBeenCalledOnce();
    rerender(<SaveBar changes={3} onSave={save} onDiscard={discard} saving />);
    expect(screen.getByRole("region")).toHaveTextContent("3 changes not saved");
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
  });

  it("keeps room below what scrolls while it shows, so focus is never under it (WCAG 2.4.11)", () => {
    const { rerender, unmount } = render(<SaveBar changes={2} onSave={vi.fn()} onDiscard={vi.fn()} />);
    // jsdom lays nothing out: the bar is 0px, plus its gap and a ring's room.
    expect(room()).toBe("24px");
    rerender(<SaveBar changes={0} onSave={vi.fn()} onDiscard={vi.fn()} />);
    expect(room()).toBe("");
    rerender(<SaveBar changes={1} onSave={vi.fn()} onDiscard={vi.fn()} />);
    expect(room()).toBe("24px");
    unmount();
    expect(room()).toBe("");
  });

  it("measures again as the bar resizes", () => {
    const watched: Element[] = [];
    let resized: () => void = () => undefined;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          resized = callback;
        }
        observe(element: Element) {
          watched.push(element);
        }
        disconnect() {
          watched.length = 0;
        }
      },
    );
    const { unmount } = render(<SaveBar changes={2} onSave={vi.fn()} onDiscard={vi.fn()} />);
    const bar = screen.getByRole("region");
    expect(watched).toEqual([bar]);
    vi.spyOn(bar, "getBoundingClientRect").mockReturnValue({ height: 61.2 } as DOMRect);
    resized();
    expect(room()).toBe("86px");
    unmount();
    expect(watched).toEqual([]);
  });
});

describe("cubic on #82", () => {
  it("keeps the room while another bar still shows, when one of two goes", () => {
    const { rerender } = render(
      <>
        <SaveBar changes={1} onSave={vi.fn()} onDiscard={vi.fn()} />
        <SaveBar changes={1} onSave={vi.fn()} onDiscard={vi.fn()} />
      </>,
    );
    expect(room()).toBe("24px");
    rerender(
      <>
        <SaveBar changes={0} onSave={vi.fn()} onDiscard={vi.fn()} />
        <SaveBar changes={1} onSave={vi.fn()} onDiscard={vi.fn()} />
      </>,
    );
    expect(room()).toBe("24px");
    rerender(
      <>
        <SaveBar changes={0} onSave={vi.fn()} onDiscard={vi.fn()} />
        <SaveBar changes={0} onSave={vi.fn()} onDiscard={vi.fn()} />
      </>,
    );
    expect(room()).toBe("");
  });
});
