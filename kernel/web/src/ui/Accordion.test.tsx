import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Accordion } from "./Accordion";
import { OPENED_BY_LINK } from "./place";

const KEY = "mf_open_sections";

function details(name: string): HTMLDetailsElement {
  const heading = screen.getByRole("heading", { name });
  const found = heading.closest("details");
  if (!found) throw new Error("No details around the heading.");
  return found;
}

afterEach(() => {
  window.localStorage.clear();
});

describe("Accordion", () => {
  it("is shut by default, a group named by its title, its meta showing only while shut", async () => {
    render(
      <Accordion id="mail" title="Mail" meta="SMTP, set">
        <p>The body</p>
      </Accordion>,
    );
    const section = details("Mail");
    expect(section.open).toBe(false);
    expect(screen.getByRole("group", { name: "Mail" })).toBe(section);
    expect(screen.getByText("SMTP, set")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("heading", { name: "Mail" }));
    expect(section.open).toBe(true);
    expect(screen.queryByText("SMTP, set")).toBeNull();
  });

  it("opens by itself for a first state that needs attention, and shows the state as a pill", () => {
    render(
      <Accordion id="storage" title="Storage" level={3} state={{ tone: "danger", label: "Not set up" }}>
        <p>Set it up</p>
      </Accordion>,
    );
    expect(details("Storage").open).toBe(true);
    expect(screen.getByRole("heading", { level: 3, name: "Storage" })).toBeInTheDocument();
    expect(screen.getByText("Not set up")).toHaveClass("mf-pill--danger");
  });

  it("opens when a state needing attention arrives with the page's data, but not for one that turns later", () => {
    const { rerender } = render(
      <Accordion id="a" title="A">
        <p>A</p>
      </Accordion>,
    );
    rerender(
      <Accordion id="a" title="A" state={{ tone: "warning", label: "Check" }}>
        <p>A</p>
      </Accordion>,
    );
    expect(details("A").open).toBe(true);

    render(
      <Accordion id="b" title="B" state={{ tone: "success", label: "Set" }}>
        <p>B</p>
      </Accordion>,
    );
    expect(details("B").open).toBe(false);
  });

  it("remembers the reader's own opening and shutting, and only theirs", async () => {
    const { unmount } = render(
      <Accordion id="mail" title="Mail">
        <p>Body</p>
      </Accordion>,
    );
    await userEvent.click(screen.getByRole("heading", { name: "Mail" }));
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? "{}")).toEqual({ mail: true });
    unmount();
    render(
      <Accordion id="mail" title="Mail">
        <p>Body</p>
      </Accordion>,
    );
    expect(details("Mail").open).toBe(true);
  });

  it("doesn't remember a section a link opened", () => {
    render(
      <Accordion id="linked" title="Linked">
        <p>Body</p>
      </Accordion>,
    );
    const section = details("Linked");
    section.setAttribute(OPENED_BY_LINK, "");
    section.open = true;
    fireEvent(section, new Event("toggle"));
    expect(section.hasAttribute(OPENED_BY_LINK)).toBe(false);
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it("falls back to its default when storage refuses", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(
      <Accordion id="x" title="X" defaultOpen>
        <p>Body</p>
      </Accordion>,
    );
    const section = details("X");
    expect(section.open).toBe(true);
    section.open = false;
    expect(() => fireEvent(section, new Event("toggle"))).not.toThrow();
  });

  it("says news that arrives while it's shut, and empties the line once it's opened", async () => {
    const { rerender } = render(
      <Accordion id="import" title="Import" said="">
        <p>Body</p>
      </Accordion>,
    );
    const line = screen.getByRole("status");
    expect(line).toHaveTextContent("");
    rerender(
      <Accordion id="import" title="Import" said="The import stopped.">
        <p>Body</p>
      </Accordion>,
    );
    expect(line).toHaveTextContent("The import stopped.");
    await userEvent.click(screen.getByRole("heading", { name: "Import" }));
    expect(line).toHaveTextContent("");
  });

  it("ignores a toggle that only bubbles up from a section inside it", () => {
    render(
      <Accordion id="outer" title="Outer">
        <details data-testid="inner">
          <summary>Inner</summary>
        </details>
      </Accordion>,
    );
    fireEvent(screen.getByTestId("inner"), new Event("toggle", { bubbles: true }));
    expect(details("Outer").open).toBe(false);
  });

  it("shows a meta of 0 while shut (cubic on #82)", () => {
    render(
      <Accordion id="count" title="Count" meta={0}>
        <p>Body</p>
      </Accordion>,
    );
    expect(screen.getByText("0", { selector: ".mf-accordion-meta" })).toBeInTheDocument();
  });

  it("stays shut when a state that arrived fine turns to a warning later (cubic on #82)", () => {
    const { rerender } = render(
      <Accordion id="later" title="Later" state={{ tone: "success", label: "Set" }}>
        <p>Body</p>
      </Accordion>,
    );
    rerender(
      <Accordion id="later" title="Later" state={{ tone: "warning", label: "Check" }}>
        <p>Body</p>
      </Accordion>,
    );
    expect(details("Later").open).toBe(false);
  });

  it("remembers the reader shutting it, too (cubic on #82)", async () => {
    const { unmount } = render(
      <Accordion id="shut" title="Shut" defaultOpen>
        <p>Body</p>
      </Accordion>,
    );
    await userEvent.click(screen.getByRole("heading", { name: "Shut" }));
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? "{}")).toEqual({ shut: false });
    unmount();
    render(
      <Accordion id="shut" title="Shut" defaultOpen>
        <p>Body</p>
      </Accordion>,
    );
    expect(details("Shut").open).toBe(false);
  });
});
