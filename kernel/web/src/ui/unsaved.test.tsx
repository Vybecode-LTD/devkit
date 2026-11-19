import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { renderWithKernel } from "../../testing";
import { UnsavedDialog } from "./UnsavedDialog";
import { useLeaveGuard, useUnsavedGuard } from "./unsaved";

function Editor({ save, startDirty = true }: { save: () => Promise<string | null>; startDirty?: boolean }) {
  const [dirty, setDirty] = useState(startDirty);
  const guard = useUnsavedGuard(dirty, save);
  const { pathname } = useLocation();
  return (
    <>
      <p>At {pathname}</p>
      <button
        type="button"
        onClick={() => {
          setDirty(!dirty);
        }}
      >
        Toggle
      </button>
      <UnsavedDialog guard={guard} what="This role" />
    </>
  );
}

describe("useUnsavedGuard and UnsavedDialog", () => {
  it("asks before a move to another page loses the changes, and Stay keeps the page", async () => {
    const { router } = renderWithKernel(<Editor save={vi.fn()} />, { path: "/admin/roles/new" });
    await act(() => router.navigate("/admin"));
    expect(screen.getByRole("dialog", { name: "You have changes that aren't saved" })).toBeInTheDocument();
    expect(screen.getByText("This role has changes that aren't saved. If you leave now, they're lost.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("At /admin/roles/new")).toBeInTheDocument();
  });

  it("goes on without saving when asked", async () => {
    const save = vi.fn();
    const { router } = renderWithKernel(<Editor save={save} />, { path: "/admin/roles/new" });
    await act(() => router.navigate("/admin"));
    await userEvent.click(screen.getByRole("button", { name: "Leave without saving" }));
    expect(await screen.findByText("At /admin")).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });

  it("saves and goes on, or stays and says why it couldn't save", async () => {
    const save = vi.fn<() => Promise<string | null>>().mockResolvedValueOnce("The name is taken.").mockResolvedValueOnce(null);
    const { router } = renderWithKernel(<Editor save={save} />, { path: "/admin/roles/new" });
    await act(() => router.navigate("/admin"));
    await userEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The name is taken.");
    expect(screen.getByText("At /admin/roles/new")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(await screen.findByText("At /admin")).toBeInTheDocument();
  });

  it("says a thrown failure in its own words, and a blank one as it is", async () => {
    const save = vi
      .fn<() => Promise<string | null>>()
      .mockRejectedValueOnce(new Error("The server is down."))
      .mockRejectedValueOnce("not an error");
    const { router } = renderWithKernel(<Editor save={save} />, { path: "/a" });
    await act(() => router.navigate("/b"));
    await userEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The server is down.");
    await userEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("It couldn't be saved.");
  });

  it("says a save that throws at once as any other failure, and can be tried again (cubic on #82)", async () => {
    const save = vi
      .fn<() => Promise<string | null>>()
      .mockImplementationOnce(() => {
        throw new Error("No form to save.");
      })
      .mockResolvedValueOnce(null);
    const { router } = renderWithKernel(<Editor save={save} />, { path: "/a" });
    await act(() => router.navigate("/b"));
    await userEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No form to save.");
    // And the next try saves and goes on (CodeRabbit on #82).
    await userEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(await screen.findByText("At /b")).toBeInTheDocument();
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("changes nothing when a save answers after the person chose to stay", async () => {
    let finish: (why: string | null) => void = () => undefined;
    const save = vi.fn(() => new Promise<string | null>((resolve) => (finish = resolve)));
    const { router } = renderWithKernel(<Editor save={save} />, { path: "/a" });
    await act(() => router.navigate("/b"));
    await userEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Stay" }));
    await act(async () => {
      finish(null);
      await Promise.resolve();
    });
    expect(screen.getByText("At /a")).toBeInTheDocument();
  });

  it("lets a move within the page through, and any move once nothing's changed", async () => {
    const { router } = renderWithKernel(<Editor save={vi.fn()} />, { path: "/a" });
    await act(() => router.navigate("/a?tab=two"));
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Toggle" }));
    await act(() => router.navigate("/b"));
    expect(screen.getByText("At /b")).toBeInTheDocument();
  });

  it("asks the browser's question on a reload only while there are changes", async () => {
    renderWithKernel(<Editor save={vi.fn()} />, { path: "/a" });
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Toggle" }));
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
  });
});

describe("useLeaveGuard", () => {
  it("lets the editor's own next move through once released", async () => {
    function Saved() {
      const { blocker, release } = useLeaveGuard(true);
      const { pathname } = useLocation();
      return (
        <>
          <p>
            At {pathname}, {blocker.state}
          </p>
          <button type="button" onClick={release}>
            Release
          </button>
        </>
      );
    }
    const { router } = renderWithKernel(<Saved />, { path: "/a" });
    await userEvent.click(screen.getByRole("button", { name: "Release" }));
    await act(() => router.navigate("/b"));
    await waitFor(() => {
      expect(screen.getByText("At /b, unblocked")).toBeInTheDocument();
    });
  });
});
