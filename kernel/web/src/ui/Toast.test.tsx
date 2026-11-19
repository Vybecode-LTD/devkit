import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithKernel } from "../../testing";
import { TOAST_MS, ToastProvider, useToast, type ToastNote } from "./Toast";

function Sender({ note }: { note: ToastNote }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => {
        toast(note);
      }}
    >
      Send
    </button>
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe("toasts", () => {
  it("is on every page: a note says itself in the polite region", () => {
    renderWithKernel(<Sender note={{ tone: "success", text: "Role saved" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const note = screen.getByText("Role saved");
    expect(note.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
    expect(note.closest(".mf-toast")).toHaveClass("mf-toast--success");
  });

  it("says a failure in the assertive region", () => {
    render(
      <ToastProvider>
        <Sender note={{ tone: "danger", text: "It couldn't be saved" }} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByText("It couldn't be saved").closest("[aria-live]")).toHaveAttribute("aria-live", "assertive");
  });

  it("goes after a while, but stays while the pointer or the keyboard is in it", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Sender note={{ text: "Saved" }} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const note = screen.getByText("Saved").closest(".mf-toast") as HTMLElement;
    expect(note).toHaveClass("mf-toast--neutral");
    fireEvent.pointerEnter(note);
    act(() => {
      vi.advanceTimersByTime(TOAST_MS * 2);
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    fireEvent.pointerLeave(note);
    fireEvent.focus(screen.getByRole("button", { name: "Close" }));
    act(() => {
      vi.advanceTimersByTime(TOAST_MS * 2);
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    fireEvent.blur(screen.getByRole("button", { name: "Close" }));
    act(() => {
      vi.advanceTimersByTime(TOAST_MS);
    });
    expect(screen.queryByText("Saved")).toBeNull();
  });

  it("stays while the keyboard is in it after the pointer leaves, and while the pointer is on it after the keyboard leaves (Codex on #82)", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Sender note={{ text: "Saved" }} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const note = screen.getByText("Saved").closest(".mf-toast") as HTMLElement;
    const close = screen.getByRole("button", { name: "Close" });
    fireEvent.focus(close);
    fireEvent.pointerEnter(note);
    fireEvent.pointerLeave(note);
    act(() => {
      vi.advanceTimersByTime(TOAST_MS * 2);
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    fireEvent.pointerEnter(note);
    fireEvent.blur(close);
    act(() => {
      vi.advanceTimersByTime(TOAST_MS * 2);
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();
    fireEvent.pointerLeave(note);
    act(() => {
      vi.advanceTimersByTime(TOAST_MS);
    });
    expect(screen.queryByText("Saved")).toBeNull();
  });

  it("closes with its own button", () => {
    render(
      <ToastProvider>
        <Sender note={{ text: "Saved" }} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("Saved")).toBeNull();
  });

  it("does nothing outside a provider", () => {
    const { result } = renderHook(() => useToast());
    expect(() => {
      result.current({ text: "Nowhere" });
    }).not.toThrow();
  });
});
