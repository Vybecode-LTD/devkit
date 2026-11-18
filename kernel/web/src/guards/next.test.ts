import { describe, expect, it } from "vitest";

import { safeNext, signInFor } from "./next";

describe("where a sign-in may send the person back to", () => {
  it.each(["/", "/account", "/blog/hello?page=2#top", "/a/b-c"])("keeps a path on this site: %s", (next) => {
    expect(safeNext(next)).toBe(next);
  });

  it.each([
    null,
    undefined,
    "",
    "account",
    "//evil.test",
    "/\\evil.test",
    "/a//b",
    "https://evil.test/",
    "/a\u0000b",
    "/a\nb",
    "javascript:alert(1)",
  ])("refuses anything else: %j", (next) => {
    expect(safeNext(next)).toBeNull();
  });

  it("names the page to come back to, and nothing for the home page or a bad path", () => {
    expect(signInFor("/account?needs=x")).toBe("/sign-in?next=%2Faccount%3Fneeds%3Dx");
    expect(signInFor("/")).toBe("/sign-in");
    expect(signInFor("//evil.test")).toBe("/sign-in");
  });
});
