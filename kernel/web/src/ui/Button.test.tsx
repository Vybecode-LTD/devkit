import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { renderWithKernel } from "../../testing";
import { Button, LinkButton, buttonClass } from "./Button";
import { Icon } from "./Icon";
import { ICONS, ICON_NAMES } from "./icons";

describe("Button", () => {
  it("is a plain button unless it says otherwise, so a form never sends by accident", () => {
    render(
      <form>
        <Button>Discard</Button>
        <Button type="submit">Save</Button>
      </form>,
    );
    expect(screen.getByRole("button", { name: "Discard" })).toHaveAttribute("type", "button");
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "submit");
  });

  it("is secondary by default, primary when asked, and small when asked", () => {
    render(
      <>
        <Button>Cancel</Button>
        <Button variant="primary" size="small" className="extra">
          Publish
        </Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass("mf-button", "mf-button--secondary");
    expect(screen.getByRole("button", { name: "Publish" })).toHaveClass("mf-button--primary", "mf-button--small", "extra");
    expect(buttonClass({})).toBe("mf-button mf-button--secondary");
  });

  it("takes a ref as a prop (React 19) and hands the click on", async () => {
    const ref = createRef<HTMLButtonElement>();
    const clicked = vi.fn();
    render(
      <Button ref={ref} onClick={clicked}>
        Go
      </Button>,
    );
    expect(ref.current).toBe(screen.getByRole("button", { name: "Go" }));
    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(clicked).toHaveBeenCalledOnce();
  });

  it("puts an icon after its words, hidden from a screen reader", () => {
    render(<Button icon="external">View site</Button>);
    const button = screen.getByRole("button", { name: "View site" });
    expect(button.lastElementChild).toHaveAttribute("aria-hidden", "true");
  });
});

describe("LinkButton", () => {
  it("is a link to a page, drawn as a button", () => {
    renderWithKernel(
      <LinkButton to="/admin/settings" variant="primary" icon="settings">
        Fix it
      </LinkButton>,
    );
    const link = screen.getByRole("link", { name: "Fix it" });
    expect(link).toHaveAttribute("href", "/admin/settings");
    expect(link).toHaveClass("mf-button", "mf-button--primary");
  });
});

describe("Icon", () => {
  it("is hidden from a screen reader unless it's given a label", () => {
    const { container } = render(
      <>
        <Icon name="bell" />
        <Icon name="warning" label="Warning" />
      </>,
    );
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("img", { name: "Warning" })).toBeInTheDocument();
  });

  it("draws every icon of the set, at its own size or the one asked for", () => {
    const { container } = render(
      <>
        {ICON_NAMES.map((name) => (
          <Icon key={name} name={name} />
        ))}
        <Icon name="plus" size={32} className="big" />
      </>,
    );
    const drawn = container.querySelectorAll("svg");
    expect(drawn).toHaveLength(ICON_NAMES.length + 1);
    for (const [at, name] of ICON_NAMES.entries()) {
      const svg = drawn[at];
      expect(svg?.childElementCount).toBeGreaterThan(0);
      expect(svg).toHaveAttribute("width", String(ICONS[name].size));
      expect(svg).toHaveAttribute("height", String(ICONS[name].size));
    }
    expect(container.querySelector(".big")).toHaveAttribute("width", "32");
  });

  it("fills the play triangle rather than stroking it", () => {
    const { container } = render(<Icon name="play" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("fill", "currentColor");
    expect(svg).toHaveAttribute("viewBox", "0 0 16 16");
  });
});
