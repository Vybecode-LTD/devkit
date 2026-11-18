import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiProblem, createApiClient, setApiHandlers } from "./client";
import type { paths } from "./schema";

type Answer = { status: number; body?: unknown; type?: string };

/** A fetch that answers from a list, in order, and keeps every request it got. */
function fakeFetch(...answers: Answer[]) {
  const sent: Request[] = [];
  const fetch = vi.fn((request: Request) => {
    sent.push(request);
    const next = answers.shift();
    if (!next) throw new Error("No answer left for " + request.url);
    const text = next.body === undefined ? null : JSON.stringify(next.body);
    return Promise.resolve(
      new Response(text, {
        status: next.status,
        headers: { "content-type": next.type ?? "application/json" },
      }),
    );
  });
  return { fetch, sent };
}

function problem(status: number, code: string, extra: Record<string, unknown> = {}) {
  return {
    status,
    type: "application/problem+json",
    body: {
      type: `urn:mechframe:problem:${code}`,
      title: "Forbidden",
      status,
      detail: "Confirm it's you to continue.",
      code,
      ...extra,
    },
  };
}

const user = {
  id: "6f1c2b9e-0a43-4c55-9d0c-6a7e2f1b3c4d",
  email: "a@mechframe.test",
  roles: ["member"],
  permissions: [],
  verified: true,
  second_factor: false,
};

afterEach(() => {
  setApiHandlers({ signedOut: () => undefined, stepUp: () => Promise.resolve(false) });
});

describe("ApiProblem", () => {
  it("reads a problem's members, its field errors and anything more it carries", async () => {
    const response = new Response(
      JSON.stringify({
        type: "urn:mechframe:problem:kernel.rate_limited",
        title: "Too Many Requests",
        status: 429,
        detail: "Try again in a minute.",
        code: "kernel.rate_limited",
        errors: { "body.email": ["Not an address."] },
        retry_after: 60,
      }),
      { status: 429, headers: { "content-type": "application/problem+json" } },
    );
    const found = await ApiProblem.from(response);
    expect(found).toBeInstanceOf(Error);
    expect(found.code).toBe("kernel.rate_limited");
    expect(found.status).toBe(429);
    expect(found.title).toBe("Too Many Requests");
    expect(found.detail).toBe("Try again in a minute.");
    expect(found.errors).toEqual({ "body.email": ["Not an address."] });
    expect(found.extra).toEqual({ retry_after: 60 });
    expect(found.message).toBe("Try again in a minute.");
  });

  it("makes a problem of an answer that isn't one, keeping its status", async () => {
    const found = await ApiProblem.from(
      new Response("<html>Bad gateway</html>", { status: 502, statusText: "Bad Gateway" }),
    );
    expect(found.code).toBe("kernel.unexpected_answer");
    expect(found.status).toBe(502);
    expect(found.errors).toEqual({});
  });
});

describe("the client", () => {
  it("answers a 2xx with its data, sent same-origin with the cookies", async () => {
    const { fetch, sent } = fakeFetch({ status: 200, body: { on: ["blog"] } });
    const { api } = createApiClient<paths>({ fetch });
    const { data } = await api.GET("/api/kernel/modules");
    expect(data).toEqual({ on: ["blog"] });
    expect(sent[0]?.credentials).toBe("same-origin");
    expect(new URL(sent[0]?.url ?? "").pathname).toBe("/api/kernel/modules");
  });

  it("throws an ApiProblem for any other answer", async () => {
    const { fetch } = fakeFetch(problem(404, "kernel.not_found"));
    const { api } = createApiClient<paths>({ fetch });
    await expect(api.GET("/api/kernel/modules")).rejects.toMatchObject({
      code: "kernel.not_found",
      status: 404,
    });
  });

  it("throws an ApiProblem with status 0 when the site can't be reached", async () => {
    const fetch = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    const { api } = createApiClient<paths>({ fetch });
    const failed = api.GET("/api/kernel/modules");
    await expect(failed).rejects.toBeInstanceOf(ApiProblem);
    await expect(failed).rejects.toMatchObject({ code: "kernel.unreachable", status: 0 });
  });

  it("tells the session when the person is no longer signed in, and only then", async () => {
    const signedOut = vi.fn();
    setApiHandlers({ signedOut });
    const { fetch } = fakeFetch(
      problem(401, "auth.invalid_credentials"),
      problem(401, "kernel.not_signed_in"),
    );
    const { api } = createApiClient<paths>({ fetch });
    await expect(
      api.POST("/api/auth/sign-in", { body: { email: "a@mechframe.test", password: "wrong" } }),
    ).rejects.toMatchObject({ code: "auth.invalid_credentials" });
    expect(signedOut).not.toHaveBeenCalled();
    await expect(api.GET("/api/auth/session")).rejects.toMatchObject({
      code: "kernel.not_signed_in",
    });
    expect(signedOut).toHaveBeenCalledTimes(1);
  });

  it("asks for a step-up on a refused write, then sends it again once, body and all", async () => {
    const stepUp = vi.fn(() => Promise.resolve(true));
    setApiHandlers({ stepUp });
    const { fetch, sent } = fakeFetch(problem(403, "auth.step_up_required"), {
      status: 200,
      body: { status: "password_changed" },
    });
    const { api } = createApiClient<paths>({ fetch });
    const body = { current_password: "old password!", new_password: "a new long password" };
    const { data } = await api.POST("/api/auth/password/change", { body });
    expect(data).toEqual({ status: "password_changed" });
    expect(stepUp).toHaveBeenCalledTimes(1);
    expect(sent).toHaveLength(2);
    expect(await sent[1]?.json()).toEqual(body);
  });

  it("keeps the refusal when the person doesn't step up, or is refused again", async () => {
    setApiHandlers({ stepUp: () => Promise.resolve(false) });
    const declined = fakeFetch(problem(403, "auth.step_up_required"));
    const first = createApiClient<paths>({ fetch: declined.fetch }).api;
    await expect(
      first.POST("/api/auth/recovery-codes"),
    ).rejects.toMatchObject({ code: "auth.step_up_required" });
    expect(declined.sent).toHaveLength(1);

    const stepUp = vi.fn(() => Promise.resolve(true));
    setApiHandlers({ stepUp });
    const twice = fakeFetch(
      problem(403, "auth.step_up_required"),
      problem(403, "auth.step_up_required"),
    );
    const second = createApiClient<paths>({ fetch: twice.fetch }).api;
    await expect(
      second.POST("/api/auth/recovery-codes"),
    ).rejects.toMatchObject({ code: "auth.step_up_required" });
    expect(stepUp).toHaveBeenCalledTimes(1);
    expect(twice.sent).toHaveLength(2);
  });

  it("throws kernel.unreachable when the resend after a step-up can't reach the site", async () => {
    setApiHandlers({ stepUp: () => Promise.resolve(true) });
    const first = fakeFetch(problem(403, "auth.step_up_required"));
    let calls = 0;
    const fetch = vi.fn((request: Request) => {
      calls += 1;
      if (calls === 1) return first.fetch(request);
      return Promise.reject(new TypeError("Failed to fetch"));
    });
    const { api } = createApiClient<paths>({ fetch });
    const failed = api.POST("/api/auth/recovery-codes");
    await expect(failed).rejects.toBeInstanceOf(ApiProblem);
    await expect(failed).rejects.toMatchObject({ code: "kernel.unreachable", status: 0 });
    expect(calls).toBe(2);
  });

  it("never asks for a step-up on a read", async () => {
    const stepUp = vi.fn(() => Promise.resolve(true));
    setApiHandlers({ stepUp });
    const { fetch, sent } = fakeFetch(problem(403, "auth.step_up_required"));
    const { api } = createApiClient<paths>({ fetch });
    await expect(api.GET("/api/auth/passkeys")).rejects.toMatchObject({
      code: "auth.step_up_required",
    });
    expect(stepUp).not.toHaveBeenCalled();
    expect(sent).toHaveLength(1);
  });
});

describe("the hooks", () => {
  function wrapper({ children }: { children: ReactNode }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }

  it("useApiQuery gives the answer's data", async () => {
    const { fetch } = fakeFetch({ status: 200, body: { user } });
    const { useApiQuery } = createApiClient<paths>({ fetch });
    const { result } = renderHook(() => useApiQuery("get", "/api/auth/session"), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.user.email).toBe("a@mechframe.test");
  });

  it("useApiMutation gives a refusal as an ApiProblem", async () => {
    const { fetch } = fakeFetch(problem(409, "auth.already_verified"));
    const { useApiMutation } = createApiClient<paths>({ fetch });
    const { result } = renderHook(() => useApiMutation("post", "/api/auth/verify-email/resend"), {
      wrapper,
    });
    result.current.mutate({});
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(ApiProblem);
    expect(result.current.error?.code).toBe("auth.already_verified");
  });
});
