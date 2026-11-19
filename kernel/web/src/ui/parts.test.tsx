// The kit's small parts: Card, Pill, Chip, Attention, StatCard, EmptyState, LoadError and the words.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithKernel } from "../../testing";
import { ApiProblem } from "../api/problem";
import { Attention } from "./Attention";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { LoadError, failureWords } from "./LoadError";
import { Chip, Pill } from "./Pill";
import { StatCard } from "./StatCard";
import { and, quoted, when } from "./words";

describe("Pill", () => {
  it("draws info in its own tone (K4.6)", () => {
    render(<Pill tone="info">Scheduled</Pill>);
    expect(screen.getByText("Scheduled")).toHaveClass("mf-pill", "mf-pill--info");
  });
});

describe("Card", () => {
  it("is a section named by its heading, with its actions beside it", () => {
    render(
      <Card title="Recent activity" actions={<a href="/admin/activity">All activity</a>}>
        <p>Body</p>
      </Card>,
    );
    const card = screen.getByRole("region", { name: "Recent activity" });
    expect(card).toHaveClass("mf-card");
    expect(screen.getByRole("heading", { level: 2, name: "Recent activity" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All activity" })).toBeInTheDocument();
  });

  it("takes a level-3 heading, drops its padding when flush, and goes unnamed without a title", () => {
    const { container } = render(
      <>
        <Card title="Inner" level={3} flush className="x">
          <p>Table</p>
        </Card>
        <Card>
          <p>Bare</p>
        </Card>
      </>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Inner" })).toBeInTheDocument();
    const [flush, bare] = container.querySelectorAll("section");
    expect(flush).toHaveClass("mf-card--flush", "x");
    expect(bare).not.toHaveAttribute("aria-labelledby");
  });
});

describe("Pill and Chip", () => {
  it("says a state in its tone's words, with a dot no screen reader reads", () => {
    const { container } = render(
      <>
        <Pill tone="success">Live</Pill>
        <Pill>Draft</Pill>
      </>,
    );
    expect(screen.getByText("Live")).toHaveClass("mf-pill--success");
    expect(screen.getByText("Draft")).toHaveClass("mf-pill--neutral");
    expect(container.querySelector(".mf-pill-dot")).toHaveAttribute("aria-hidden", "true");
  });

  it("is a pressed or unpressed filter, with a check while pressed", async () => {
    const changed = vi.fn();
    const { rerender } = render(
      <Chip pressed={false} onPressedChange={changed}>
        Drafts
      </Chip>,
    );
    const chip = screen.getByRole("button", { name: "Drafts" });
    expect(chip).toHaveAttribute("aria-pressed", "false");
    expect(chip.querySelector("svg")).toBeNull();
    await userEvent.click(chip);
    expect(changed).toHaveBeenCalledWith(true);
    rerender(
      <Chip pressed onPressedChange={changed}>
        Drafts
      </Chip>,
    );
    expect(chip).toHaveAttribute("aria-pressed", "true");
    expect(chip.querySelector("svg")).not.toBeNull();
  });
});

describe("Attention", () => {
  it("says what's wrong and why, with its tone in words, and the action that fixes it", () => {
    renderWithKernel(
      <Attention
        tone="danger"
        what="Three jobs failed"
        why="Their mail wasn't sent."
        action={{ label: "See them", to: "/admin/settings/system" }}
      />,
    );
    expect(screen.getByRole("img", { name: "Problem" })).toBeInTheDocument();
    expect(screen.getByText("Three jobs failed")).toBeInTheDocument();
    expect(screen.getByText("Their mail wasn't sent.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See them" })).toHaveAttribute("href", "/admin/settings/system");
  });

  it("is a warning without an action too", () => {
    render(<Attention tone="warning" what="No description" why="Search shows the first words instead." />);
    expect(screen.getByRole("img", { name: "Warning" })).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("says what's only worth knowing as a note, in the info tone (K4.6)", () => {
    const { container } = render(<Attention tone="info" what="The single ends in 2 days" why="The bar hides after Nov 17." />);
    expect(screen.getByRole("img", { name: "Note" })).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("mf-attention--info");
  });
});

describe("StatCard", () => {
  it("is a section named by what it counts, with its state, figure, line and link", () => {
    renderWithKernel(
      <StatCard
        label="Plays this week"
        value="1,284"
        line="Up 18% on last week"
        state={{ tone: "success", label: "Up 18%" }}
        link={{ label: "Music", to: "/admin/music" }}
      />,
    );
    const card = screen.getByRole("region", { name: "Plays this week" });
    expect(screen.getByRole("heading", { level: 2, name: "Plays this week" })).toBeInTheDocument();
    expect(card).toHaveTextContent("1,284");
    expect(card).toHaveTextContent("Up 18% on last week");
    expect(screen.getByText("Up 18%").closest(".mf-pill")).toHaveClass("mf-pill--success");
    expect(screen.getByRole("link", { name: "Music" })).toHaveAttribute("href", "/admin/music");
  });

  it("takes a level-3 label and leaves out what it isn't given", () => {
    const { container } = render(<StatCard label="System" value="All jobs running" level={3} />);
    expect(screen.getByRole("heading", { level: 3, name: "System" })).toBeInTheDocument();
    expect(container.querySelector(".mf-stat-line, .mf-pill, a")).toBeNull();
  });
});

describe("EmptyState", () => {
  it("says what would be here and how to make the first", () => {
    render(
      <EmptyState title="No roles of your own yet" action={<button type="button">New role</button>}>
        Roles you make show here.
      </EmptyState>,
    );
    expect(screen.getByText("No roles of your own yet")).toBeInTheDocument();
    expect(screen.getByText("Roles you make show here.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New role" })).toBeInTheDocument();
  });
});

describe("LoadError", () => {
  const problem = new ApiProblem({
    type: "about:blank",
    title: "Not allowed",
    status: 403,
    detail: "You need the People permission.",
    code: "auth.forbidden",
  });

  it("says the load failed, in the server's words, with Try again", async () => {
    const retry = vi.fn();
    render(
      <LoadError what="The people" error={problem} onRetry={retry}>
        <a href="/admin">Back</a>
      </LoadError>,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The people couldn't be loaded.");
    expect(alert).toHaveTextContent("You need the People permission.");
    expect(screen.getByRole("link", { name: "Back" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("drops the card inline, and says nothing more when the failure has no words", () => {
    const { container } = render(<LoadError what="The history" error={{}} onRetry={vi.fn()} inline />);
    expect(container.firstElementChild).toHaveClass("mf-load-error--inline");
    expect(container.querySelector(".mf-load-error-why")).toBeNull();
  });

  it("finds a failure's words: a problem's detail or title, an error's message, a string", () => {
    expect(failureWords(problem)).toBe("You need the People permission.");
    expect(failureWords(new ApiProblem({ type: "about:blank", title: "Gone", status: 404, detail: "", code: "x" }))).toBe(
      "Gone",
    );
    expect(failureWords(new Error("Dropped"))).toBe("Dropped");
    expect(failureWords("Plain")).toBe("Plain");
    expect(failureWords(7)).toBe("");
  });
});

describe("the kit's words", () => {
  it("lists with commas and a last “and”", () => {
    expect(and([])).toBe("");
    expect(and(["Port"])).toBe("Port");
    expect(and(["Port", "Host", "Name"])).toBe("Port, Host and Name");
    expect(quoted("Port")).toBe("“Port”");
  });

  it("writes a moment in the reader's locale, and nothing for no moment", () => {
    expect(when("2026-11-18T21:40:00Z")).toMatch(/2026/);
    expect(when(null)).toBe("");
    expect(when("not a date")).toBe("");
  });
});

describe("cubic on #82", () => {
  it("hands a chip's click on to its own onClick too", async () => {
    const clicked = vi.fn();
    const changed = vi.fn();
    render(
      <Chip pressed={false} onPressedChange={changed} onClick={clicked}>
        Drafts
      </Chip>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Drafts" }));
    expect(clicked).toHaveBeenCalledOnce();
    expect(changed).toHaveBeenCalledWith(true);
  });

  it("keeps a zero: a card titled 0 is named by it, an empty state's line of 0 shows", () => {
    render(
      <>
        <Card title={0}>
          <p>Body</p>
        </Card>
        <EmptyState title="Nothing">{0}</EmptyState>
      </>,
    );
    expect(screen.getByRole("region", { name: "0" })).toBeInTheDocument();
    expect(screen.getByText("0", { selector: ".mf-empty-line" })).toBeInTheDocument();
  });
});

describe("CodeRabbit on #82", () => {
  it("lets a chip's own onClick call the press off", async () => {
    const changed = vi.fn();
    render(
      <Chip
        pressed={false}
        onPressedChange={changed}
        onClick={(event) => {
          event.preventDefault();
        }}
      >
        Drafts
      </Chip>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Drafts" }));
    expect(changed).not.toHaveBeenCalled();
  });
});
