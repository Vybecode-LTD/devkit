import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("the harness app", () => {
  it("renders one heading and the kernel's version", () => {
    render(<App />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText(/Kernel 0\.1\.0-dev\.0/)).toBeInTheDocument();
  });
});
