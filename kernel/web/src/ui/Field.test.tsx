import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Field, Input, Select, Switch, TextArea } from "./Field";

describe("Field", () => {
  it("names its control by its label, and describes it by its hint and what's wrong", () => {
    render(
      <Field label="Site name" hint="Shown in the title bar." error={["It can't be blank.", "Or too long."]}>
        <Input name="name" />
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: "Site name" });
    expect(input).toHaveAccessibleDescription("Shown in the title bar. It can't be blank. Or too long.");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("is valid and described by its hint alone when nothing is wrong", () => {
    render(
      <Field label="Tagline" hint="A line under the name.">
        <TextArea />
      </Field>,
    );
    const area = screen.getByRole("textbox", { name: "Tagline" });
    expect(area).not.toHaveAttribute("aria-invalid");
    expect(area).toHaveAccessibleDescription("A line under the name.");
  });

  it("gives the control the field's id, over one the control was given, so the label always names it (cubic on #82)", () => {
    render(
      <Field label="Email" id="email">
        <Input id="mine" />
      </Field>,
    );
    expect(screen.getByRole("textbox", { name: "Email" })).toHaveAttribute("id", "email");
  });

  it("keeps what the control was given itself: its own description", () => {
    render(
      <>
        <p id="extra">Counts toward the limit.</p>
        <Field label="Words" error="Too many." id="words">
          <Input aria-describedby="extra" aria-invalid={false} />
        </Field>
      </>,
    );
    const input = screen.getByRole("textbox", { name: "Words" });
    expect(input).toHaveAttribute("id", "words");
    expect(input).toHaveAccessibleDescription("Too many. Counts toward the limit.");
    expect(input).toHaveAttribute("aria-invalid", "false");
  });

  it("wires a select too, and a control outside a field is left as it is", () => {
    render(
      <>
        <Field label="Time zone">
          <Select defaultValue="b">
            <option value="a">A</option>
            <option value="b">B</option>
          </Select>
        </Field>
        <Input aria-label="Search" className="wide" />
      </>,
    );
    expect(screen.getByRole("combobox", { name: "Time zone" })).toHaveClass("mf-input", "mf-select");
    const search = screen.getByRole("textbox", { name: "Search" });
    expect(search).toHaveClass("mf-input", "wide");
    expect(search).not.toHaveAttribute("id");
  });
});

describe("Switch", () => {
  function Setting({ onChange }: { onChange: (on: boolean) => void }) {
    const [on, setOn] = useState(false);
    return (
      <Switch
        label="Open sign-up"
        hint="Anyone can make an account."
        checked={on}
        onChange={(next) => {
          setOn(next);
          onChange(next);
        }}
      />
    );
  }

  it("is a switch named by its label and described by its hint, on and off with a click", async () => {
    const changed = vi.fn();
    render(<Setting onChange={changed} />);
    const toggle = screen.getByRole("switch", { name: "Open sign-up" });
    expect(toggle).toHaveAccessibleDescription("Anyone can make an account.");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(changed).toHaveBeenLastCalledWith(true);
    await userEvent.keyboard(" ");
    expect(changed).toHaveBeenLastCalledWith(false);
  });

  it("can be shown and not changed", async () => {
    const changed = vi.fn();
    render(<Switch label="Locked" checked disabled onChange={changed} />);
    await userEvent.click(screen.getByRole("switch", { name: "Locked" }));
    expect(changed).not.toHaveBeenCalled();
  });
});

describe("cubic on #82", () => {
  it("shows a hint of 0, in a field and beside a switch", () => {
    render(
      <>
        <Field label="Limit" hint={0}>
          <Input />
        </Field>
        <Switch label="Zero" hint={0} checked={false} onChange={vi.fn()} />
      </>,
    );
    expect(screen.getByRole("textbox", { name: "Limit" })).toHaveAccessibleDescription("0");
    expect(screen.getByRole("switch", { name: "Zero" })).toHaveAccessibleDescription("0");
  });
});
