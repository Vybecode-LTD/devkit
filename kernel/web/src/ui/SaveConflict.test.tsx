import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiProblem } from "../api/problem";
import { SaveConflict, resolveConflict, settingsConflict, type SettingsConflict } from "./SaveConflict";

/** The 409 the kernel answers (`kernel.settings`), as the client throws it. */
function refused(extra: Record<string, unknown>, code = "kernel.settings_conflict"): ApiProblem {
  return new ApiProblem({
    type: "urn:mechframe:problem:kernel.settings_conflict",
    title: "Conflict",
    status: 409,
    detail: "Someone else saved these settings since you opened them, and changed name too.",
    code,
    ...extra,
  });
}

const CONFLICT: SettingsConflict = {
  detail: "Someone else saved these settings since you opened them.",
  version: 4,
  at: "2026-11-18T21:40:00+00:00",
  conflicts: [
    { field: "name", yours: "Mine", theirs: "Theirs" },
    { field: "smtp_password", secret: true },
  ],
};

const LABELS = { name: "Site name", smtp_password: "SMTP password" };

describe("settingsConflict", () => {
  it("reads the conflict out of the kernel's 409", () => {
    const conflicts = [{ field: "name", yours: "a", theirs: "b" }];
    expect(settingsConflict(refused({ version: 3, conflicts, by: null, at: "2026-11-18T20:00:00+00:00" }))).toEqual({
      detail: "Someone else saved these settings since you opened them, and changed name too.",
      version: 3,
      conflicts,
      at: "2026-11-18T20:00:00+00:00",
    });
    expect(settingsConflict(refused({ version: 3, conflicts, at: null }))?.at).toBeNull();
  });

  it("is null for any other refusal, or a conflict without its fields", () => {
    expect(settingsConflict(refused({ version: 3, conflicts: [] }, "kernel.settings_version_unknown"))).toBeNull();
    expect(settingsConflict(refused({ conflicts: [] }))).toBeNull();
    expect(settingsConflict(refused({ version: 3 }))).toBeNull();
    expect(settingsConflict(new Error("Dropped"))).toBeNull();
  });
});

describe("resolveConflict", () => {
  it("saves at the newest version, dropping each field where theirs was chosen", () => {
    const changes = { name: "Mine", smtp_password: "secret", tagline: "Only mine" };
    expect(resolveConflict(changes, CONFLICT, { name: "theirs", smtp_password: "mine" })).toEqual({
      version: 4,
      changes: { smtp_password: "secret", tagline: "Only mine" },
    });
  });
});

describe("SaveConflict", () => {
  it("puts the focus on its heading, says the server's words, then each field's two sides", () => {
    render(<SaveConflict conflict={CONFLICT} labels={LABELS} saving={false} onResolve={vi.fn()} onCancel={vi.fn()} />);
    const heading = screen.getByRole("heading", { name: "Saved by someone else since you opened it" });
    expect(heading).toHaveFocus();
    expect(heading).toHaveAccessibleDescription(CONFLICT.detail);
    const name = screen.getByRole("group", { name: "Site name" });
    expect(name).toHaveTextContent("Theirs");
    expect(name).toHaveTextContent("Mine");
    const secret = screen.getByRole("group", { name: "SMTP password" });
    expect(secret).toHaveTextContent("A new one they typed");
    expect(secret).toHaveTextContent("The one you typed");
  });

  it("saves only once each field has a choice, with the choices made", async () => {
    const resolve = vi.fn();
    render(<SaveConflict conflict={CONFLICT} labels={LABELS} saving={false} onResolve={resolve} onCancel={vi.fn()} />);
    const save = screen.getByRole("button", { name: "Save with these choices" });
    expect(save).toBeDisabled();
    expect(save).toHaveAccessibleDescription("Choose theirs or yours for each field to save.");
    const [theirs] = screen.getAllByRole("radio", { name: "Use theirs" });
    const [, mine] = screen.getAllByRole("radio", { name: "Keep mine" });
    await userEvent.click(theirs as HTMLElement);
    await userEvent.click(mine as HTMLElement);
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(resolve).toHaveBeenCalledWith({ name: "theirs", smtp_password: "mine" });
  });

  it("says each kind of value as a form shows it, or as the page formats it", () => {
    const values: SettingsConflict = {
      ...CONFLICT,
      at: null,
      conflicts: [
        { field: "on", yours: true, theirs: false },
        { field: "blank", yours: "", theirs: null },
        { field: "list", yours: ["a", { b: 1 }], theirs: [] },
        { field: "count", yours: 3, theirs: { n: 2 } },
        { field: "named", yours: "u1", theirs: "u2" },
      ],
    };
    render(
      <SaveConflict
        conflict={values}
        labels={{}}
        saving
        onResolve={vi.fn()}
        onCancel={vi.fn()}
        format={(field, value) => (field === "named" ? `Person ${value as string}` : JSON.stringify(value))}
      />,
    );
    expect(screen.getByRole("group", { name: "on" })).toHaveTextContent(/^on.*Theirsfalse.*Yourstrue$/s);
    render(<SaveConflict conflict={values} labels={{}} saving onResolve={vi.fn()} onCancel={vi.fn()} />);
    const [, on] = screen.getAllByRole("group", { name: "on" });
    expect(on).toHaveTextContent("On");
    expect(on).toHaveTextContent("Off");
    const [, blank] = screen.getAllByRole("group", { name: "blank" });
    expect(blank).toHaveTextContent("Blank");
    expect(blank).toHaveTextContent("None");
    const [, list] = screen.getAllByRole("group", { name: "list" });
    expect(list).toHaveTextContent('a{"b":1}');
    const [, count] = screen.getAllByRole("group", { name: "count" });
    expect(count).toHaveTextContent("3");
    expect(count).toHaveTextContent('{"n":2}');
    expect(screen.getAllByRole("button", { name: "Saving…" })[0]).toBeDisabled();
  });

  it("starts the choice afresh for a new conflict", async () => {
    function Page() {
      const [conflict, setConflict] = useState(CONFLICT);
      return (
        <>
          <SaveConflict conflict={conflict} labels={LABELS} saving={false} onResolve={vi.fn()} onCancel={vi.fn()} />
          <button
            type="button"
            onClick={() => {
              setConflict({ ...CONFLICT, version: 5 });
            }}
          >
            Again
          </button>
        </>
      );
    }
    render(<Page />);
    const [theirs] = screen.getAllByRole("radio", { name: "Use theirs" });
    await userEvent.click(theirs as HTMLElement);
    expect(theirs).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Again" }));
    expect(screen.getAllByRole("radio", { name: "Use theirs" })[0]).not.toBeChecked();
  });

  it("goes back to the form, handing the focus to its Save", async () => {
    function Form() {
      const [open, setOpen] = useState(true);
      return (
        <form>
          {open ? (
            <SaveConflict
              conflict={CONFLICT}
              labels={LABELS}
              saving={false}
              onResolve={vi.fn()}
              onCancel={() => {
                setOpen(false);
              }}
            />
          ) : null}
          <button type="submit">Save</button>
        </form>
      );
    }
    render(<Form />);
    await userEvent.click(screen.getByRole("button", { name: "Back to the form" }));
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toHaveFocus();
  });
});
