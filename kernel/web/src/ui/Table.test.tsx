import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Table, type Column } from "./Table";

type Person = { id: string; email: string; roles: number };

const COLUMNS: Column<Person>[] = [
  { key: "email", header: "Email", cell: (person) => person.email },
  { key: "roles", header: "Roles", cell: (person) => person.roles, align: "end" },
  { key: "edit", header: "Actions", cell: (person) => <button type="button">Edit {person.email}</button> },
];

const PEOPLE: Person[] = [
  { id: "1", email: "ann@example.test", roles: 2 },
  { id: "2", email: "bo@example.test", roles: 1 },
];

describe("Table", () => {
  it("is a table named by its caption, a header per column and a row per record", () => {
    render(<Table caption="People" columns={COLUMNS} rows={PEOPLE} rowKey={(person) => person.id} />);
    const table = screen.getByRole("table", { name: "People" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Email", "Roles", "Actions"]);
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1] as HTMLElement).getByRole("cell", { name: "2" })).toHaveClass("mf-cell-end");
  });

  it("can keep its caption for screen readers only", () => {
    render(<Table caption="People" captionHidden columns={COLUMNS} rows={PEOPLE} rowKey={(person) => person.id} />);
    expect(screen.getByText("People", { selector: "caption" })).toHaveClass("mf-visually-hidden");
  });

  it("shows what's given for no rows, or says there's nothing yet", () => {
    const { unmount } = render(<Table caption="People" columns={COLUMNS} rows={[]} rowKey={(person) => person.id} />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
    unmount();
    render(<Table caption="People" columns={COLUMNS} rows={[]} rowKey={(person) => person.id} empty={<p>No people</p>} />);
    expect(screen.getByText("No people")).toBeInTheDocument();
  });

  it("scrolls a control that takes the focus into view, and not for the scroller's own focus (the owner, 2026-11-18)", () => {
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    const { container } = render(<Table caption="People" columns={COLUMNS} rows={PEOPLE} rowKey={(person) => person.id} />);
    const button = screen.getByRole("button", { name: "Edit bo@example.test" });
    fireEvent.focus(button);
    expect(scrolled).toHaveBeenCalledOnce();
    expect(scrolled.mock.contexts[0]).toBe(button);
    expect(scrolled).toHaveBeenCalledWith({ block: "nearest", inline: "nearest" });
    const scroller = container.querySelector(".mf-table-scroll") as HTMLElement;
    fireEvent.focus(scroller);
    expect(scrolled).toHaveBeenCalledOnce();
  });
});

describe("cubic on #82", () => {
  it("keeps its caption over the empty state, so two empty tables are told apart", () => {
    render(<Table caption="Sign-ins" columns={COLUMNS} rows={[]} rowKey={(person) => person.id} />);
    expect(screen.getByRole("group", { name: "Sign-ins" })).toHaveTextContent("Nothing here yet");
  });

  it("is a tab stop named by its caption while it scrolls sideways, and none while it fits", () => {
    const wide = vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(900);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(300);
    const { unmount } = render(<Table caption="People" columns={COLUMNS} rows={PEOPLE} rowKey={(person) => person.id} />);
    const scroller = screen.getByRole("region", { name: "People" });
    expect(scroller).toHaveAttribute("tabindex", "0");
    unmount();
    wide.mockReturnValue(300);
    render(<Table caption="People" columns={COLUMNS} rows={PEOPLE} rowKey={(person) => person.id} />);
    expect(screen.queryByRole("region")).toBeNull();
  });
});
