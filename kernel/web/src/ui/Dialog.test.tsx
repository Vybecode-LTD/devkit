import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Dialog } from "./Dialog";

function Opener() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        New role
      </button>
      {open ? (
        <Dialog
          title="New role"
          onClose={() => {
            setOpen(false);
          }}
        >
          <p>Body</p>
        </Dialog>
      ) : null}
    </>
  );
}

describe("Dialog", () => {
  it("opens modal, named by its heading, which has the focus", async () => {
    render(<Opener />);
    await userEvent.click(screen.getByRole("button", { name: "New role" }));
    const dialog = screen.getByRole("dialog", { name: "New role" });
    expect(dialog).toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "New role" })).toHaveFocus();
  });

  it("closes on Escape and gives the focus back to what opened it", async () => {
    render(<Opener />);
    const opener = screen.getByRole("button", { name: "New role" });
    await userEvent.click(opener);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("closes when the browser cancels it", async () => {
    const closed = vi.fn();
    render(
      <Dialog title="Cancel me" onClose={closed}>
        <p>Body</p>
      </Dialog>,
    );
    await act(async () => {
      screen.getByRole("dialog").dispatchEvent(new Event("cancel", { cancelable: true }));
      await Promise.resolve();
    });
    expect(closed).toHaveBeenCalledOnce();
  });

  it("sends the focus to returnTo when what opened it has gone, and uses a heading it's given", () => {
    const back = createRef<HTMLButtonElement>();
    const heading = createRef<HTMLHeadingElement>();
    function Page({ open }: { open: boolean }) {
      return (
        <>
          <button type="button" ref={back}>
            Roles
          </button>
          {open ? (
            <Dialog title="Delete" onClose={vi.fn()} returnTo={back} heading={heading} wide>
              <p>Body</p>
            </Dialog>
          ) : null}
        </>
      );
    }
    const gone = document.createElement("button");
    document.body.append(gone);
    gone.focus();
    const { rerender } = render(<Page open />);
    expect(heading.current).toHaveFocus();
    expect(screen.getByRole("dialog")).toHaveClass("mf-dialog--wide");
    gone.remove();
    rerender(<Page open={false} />);
    expect(back.current).toHaveFocus();
  });
});
