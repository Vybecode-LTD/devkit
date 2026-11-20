import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderApp, renderWithKernel } from "@/kernel/testing";

import Home from "./Home";
import { site } from "./site";

describe("the home page", () => {
  it("says the site's name and description", async () => {
    renderWithKernel(<Home />, { site: { name: "Corner Shop", description: "Bread every morning." } });
    expect(await screen.findByRole("heading", { level: 1, name: "Corner Shop" })).toBeInTheDocument();
    expect(screen.getByText("Bread every morning.")).toBeInTheDocument();
  });

  it("leaves out the paragraph when there's no description", async () => {
    renderWithKernel(<Home />, { site: { name: "Corner Shop", description: "" } });
    await screen.findByRole("heading", { level: 1, name: "Corner Shop" });
    expect(document.querySelector("p")).toBeNull();
  });

  it("is what the site's app draws at /", async () => {
    renderApp({ sitePages: site, site: { name: "Corner Shop" } });
    expect(await screen.findByRole("heading", { level: 1, name: "Corner Shop" })).toBeInTheDocument();
  });
});
