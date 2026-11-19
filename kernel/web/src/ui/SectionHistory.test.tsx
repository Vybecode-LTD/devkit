import { act, screen } from "@testing-library/react";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SectionHistory, type HistoryVersion } from "./SectionHistory";

const VERSIONS: HistoryVersion[] = [
  { number: 2, changed: ["name", "tagline"], via: "form", saved_at: "2026-11-18T21:40:00Z", saved_by_id: "u1" },
  { number: 1, changed: [], via: "setup", saved_at: "2026-11-17T10:00:00Z", saved_by_id: null },
];
const LABELS = { name: "Site name" };

describe("SectionHistory", () => {
  it("draws nothing until the form's version is known", () => {
    const { container } = render(<SectionHistory version={null} labels={LABELS} load={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is shut, says how many saves, and reads nothing until it's opened", () => {
    const load = vi.fn();
    const { rerender } = render(<SectionHistory version={0} labels={LABELS} load={load} />);
    expect(screen.getByRole("heading", { name: "History · no saves yet" })).toBeInTheDocument();
    rerender(<SectionHistory version={1} labels={LABELS} load={load} />);
    expect(screen.getByRole("heading", { name: "History · 1 save" })).toBeInTheDocument();
    expect(load).not.toHaveBeenCalled();
  });

  it("lists each save on opening, newest first: who, how, when, what by label", async () => {
    render(<SectionHistory version={2} labels={LABELS} load={() => Promise.resolve(VERSIONS)} names={{ u1: "Ann" }} />);
    await userEvent.click(screen.getByRole("heading", { name: "History · 2 saves" }));
    const [newest, older] = await screen.findAllByRole("listitem");
    expect(newest).toHaveTextContent(/^Version 2Ann, in the form, .+\. Changed “Site name” and “tagline”\.What's saved now\.$/);
    expect(older).toHaveTextContent(/^Version 1Someone, by setup, .+\.$/);
    expect(newest?.querySelector("time")).toHaveAttribute("dateTime", "2026-11-18T21:40:00Z");
  });

  it("counts the newest save the history knows, past the form's own", async () => {
    render(<SectionHistory version={1} labels={LABELS} load={() => Promise.resolve(VERSIONS)} />);
    await userEvent.click(screen.getByRole("heading", { name: "History · 1 save" }));
    expect(await screen.findByRole("heading", { name: "History · 2 saves" })).toBeInTheDocument();
  });

  it("says when there's nothing yet", async () => {
    render(<SectionHistory version={0} labels={LABELS} load={() => Promise.resolve([])} />);
    await userEvent.click(screen.getByRole("heading", { name: "History · no saves yet" }));
    expect(await screen.findByText("No saves yet: each save from now on is kept here.")).toBeInTheDocument();
  });

  it("says a failed read as a failure, and reads again on Try again", async () => {
    const load = vi.fn<() => Promise<HistoryVersion[]>>().mockRejectedValueOnce(new Error("Down")).mockResolvedValueOnce(VERSIONS);
    render(<SectionHistory version={2} labels={LABELS} load={load} />);
    await userEvent.click(screen.getByRole("heading", { name: "History · 2 saves" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The history couldn't be loaded.Down");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByRole("listitem")).toHaveLength(2);
  });

  it("reads again when a save moves the form on while it's open, keeping only the newest answer", async () => {
    const answers: ((versions: HistoryVersion[]) => void)[] = [];
    const load = vi.fn(() => new Promise<HistoryVersion[]>((resolve) => answers.push(resolve)));
    const { rerender } = render(<SectionHistory version={1} labels={LABELS} load={load} />);
    await userEvent.click(screen.getByRole("heading", { name: "History · 1 save" }));
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    rerender(<SectionHistory version={2} labels={LABELS} load={load} />);
    expect(load).toHaveBeenCalledTimes(2);
    await act(async () => {
      answers[1]?.(VERSIONS);
      await Promise.resolve();
    });
    await act(async () => {
      answers[0]?.([]);
      await Promise.resolve();
    });
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("says a failure for a refusal that's falsy itself (cubic on #82)", async () => {
    // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors -- the case under test
    render(<SectionHistory version={1} labels={LABELS} load={() => Promise.reject(0)} />);
    await userEvent.click(screen.getByRole("heading", { name: "History · 1 save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The history couldn't be loaded.");
  });
});

describe("CodeRabbit and cubic on #82", () => {
  it("doesn't call a version what's saved now once the form has moved past it", async () => {
    const answers: ((versions: HistoryVersion[]) => void)[] = [];
    const load = vi.fn(() => new Promise<HistoryVersion[]>((resolve) => answers.push(resolve)));
    const { rerender } = render(<SectionHistory version={1} labels={LABELS} load={load} />);
    await userEvent.click(screen.getByRole("heading", { name: "History · 1 save" }));
    await act(async () => {
      answers[0]?.([VERSIONS[1] as HistoryVersion]);
      await Promise.resolve();
    });
    expect(screen.getByText("What's saved now.")).toBeInTheDocument();
    rerender(<SectionHistory version={2} labels={LABELS} load={load} />);
    expect(screen.queryByText("What's saved now.")).toBeNull();
  });
});
