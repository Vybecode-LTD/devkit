import { describe, expect, it } from "vitest";

import { ApiProblem } from "../api/problem";
import { commonProblem, said, waitFor } from "./words";

function refused(status: number, code: string, extra: Record<string, unknown> = {}) {
  return new ApiProblem({ type: `urn:mechframe:problem:${code}`, title: "Refused", status, detail: "The server's words.", code, ...extra });
}

describe("the words for a refusal", () => {
  it("say how long a limit asks to wait, rounded up", () => {
    expect(waitFor(refused(429, "kernel.rate_limited", { retry_after: 1 }))).toBe("a second");
    expect(waitFor(refused(429, "kernel.rate_limited", { retry_after: 30 }))).toBe("30 seconds");
    expect(waitFor(refused(429, "kernel.rate_limited", { retry_after: 61 }))).toBe("2 minutes");
    expect(waitFor(refused(429, "kernel.rate_limited", { retry_after: 60 }))).toBe("a minute");
    expect(waitFor(refused(429, "kernel.rate_limited"))).toBe("a minute");
  });

  it("meet the common refusals the same way on every screen", () => {
    expect(commonProblem(ApiProblem.unreachable())).toMatch(/connection/);
    expect(commonProblem(refused(429, "kernel.rate_limited", { retry_after: 120 }))).toBe("Too many tries. Wait 2 minutes, then try again.");
    expect(commonProblem(refused(503, "kernel.busy"))).toMatch(/busy/);
    expect(commonProblem(refused(500, "kernel.unexpected"))).toMatch(/our side/);
    expect(commonProblem(refused(401, "auth.invalid_credentials"))).toBeNull();
  });

  it("are the screen's own first, then the common ones, then the server's", () => {
    const wrong = refused(401, "auth.invalid_credentials");
    expect(said(wrong, { "auth.invalid_credentials": "Mine." })).toBe("Mine.");
    expect(said(wrong)).toBe("The server's words.");
    expect(said(refused(503, "kernel.busy"), { "kernel.busy": "Mine." })).toBe("Mine.");
    expect(said(new ApiProblem({ type: "", title: "", status: 400, detail: "", code: "x" }))).toBe("That didn't work. Try again.");
  });
});
