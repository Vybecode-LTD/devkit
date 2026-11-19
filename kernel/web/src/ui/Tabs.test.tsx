import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Tabs, type TabItem } from "./Tabs";

const TABS: TabItem[] = [
  { id: "site", label: "Site", panel: <input aria-label="Name" /> },
  { id: "features", label: "Features", panel: <p>Features</p> },
  { id: "system", label: "System", panel: <p>System</p> },
];

describe("Tabs", () => {
  it("is a named tab list, the first chosen, one tab stop, every panel drawn and the others hidden", () => {
    render(<Tabs label="Settings" tabs={TABS} />);
    expect(screen.getByRole("tablist", { name: "Settings" })).toBeInTheDocument();
    const [site, features] = screen.getAllByRole("tab");
    expect(site).toHaveAttribute("aria-selected", "true");
    expect(site).toHaveAttribute("tabindex", "0");
    expect(features).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tabpanel", { name: "Site" })).toBeVisible();
    expect(screen.getByText("Features", { selector: "p" })).not.toBeVisible();
  });

  it("moves and chooses with the arrow keys, wrapping, and goes to the ends with Home and End", async () => {
    render(<Tabs label="Settings" tabs={TABS} />);
    const [site, features, system] = screen.getAllByRole("tab") as [HTMLElement, HTMLElement, HTMLElement];
    site.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(features).toHaveFocus();
    expect(features).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(system).toHaveFocus();
    await userEvent.keyboard("{ArrowRight}");
    expect(site).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(system).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Home}");
    expect(site).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("a");
    expect(site).toHaveFocus();
  });

  it("keeps what was typed in a panel while another is looked at", async () => {
    render(<Tabs label="Settings" tabs={TABS} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "Haas");
    await userEvent.click(screen.getByRole("tab", { name: "System" }));
    await userEvent.click(screen.getByRole("tab", { name: "Site" }));
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Haas");
  });

  it("can be kept by its page, and falls back to the first for a choice it doesn't have", async () => {
    const chosen = vi.fn();
    function Kept() {
      const [at, setAt] = useState("system");
      return (
        <Tabs
          label="Settings"
          tabs={TABS}
          selected={at}
          onSelect={(id) => {
            setAt(id);
            chosen(id);
          }}
        />
      );
    }
    const { unmount } = render(<Kept />);
    expect(screen.getByRole("tab", { name: "System" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("tab", { name: "Features" }));
    expect(chosen).toHaveBeenCalledWith("features");
    expect(screen.getByRole("tab", { name: "Features" })).toHaveAttribute("aria-selected", "true");
    unmount();
    render(<Tabs label="Settings" tabs={TABS} selected="nowhere" />);
    expect(screen.getByRole("tab", { name: "Site" })).toHaveAttribute("aria-selected", "true");
  });
});
