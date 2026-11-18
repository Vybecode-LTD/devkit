import { QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { api } from "../api/client";
import { KernelProviders } from "../app/mount";
import { problem, routedFetch } from "../test-fetch";
import { SESSION_KEY, setSessionUser, useSession, useSignOut, type SessionUser } from "./session";

const member: SessionUser = {
  id: "6f1c2b9e-0a43-4c55-9d0c-6a7e2f1b3c4d",
  email: "a@mechframe.test",
  roles: ["member"],
  permissions: [],
  verified: true,
  second_factor: false,
};

const editor: SessionUser = { ...member, roles: ["member", "editor"], permissions: ["blog.post.write"] };

function setUp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <KernelProviders queryClient={queryClient} setup={{ modules: [], adminSections: [] }}>
      {children}
    </KernelProviders>
  );
  return { queryClient, wrapper };
}

describe("useSession", () => {
  it("is loading, then the person signed in, staff by any role but member, with what they may do", async () => {
    routedFetch({ "GET /api/auth/session": { status: 200, body: { user: editor } } });
    const { wrapper } = setUp();
    const { result } = renderHook(() => useSession(), { wrapper });
    expect(result.current.status).toBe("loading");
    await waitFor(() => {
      expect(result.current.status).toBe("signed-in");
    });
    const session = result.current;
    if (session.status !== "signed-in") throw new Error("not signed in");
    expect(session.staff).toBe(true);
    expect(session.can("blog.post.write")).toBe(true);
    expect(session.can("auth.user.manage")).toBe(false);
  });

  it("isn't staff with the member role alone", async () => {
    routedFetch({ "GET /api/auth/session": { status: 200, body: { user: member } } });
    const { result } = renderHook(() => useSession(), { wrapper: setUp().wrapper });
    await waitFor(() => {
      expect(result.current).toMatchObject({ status: "signed-in", staff: false });
    });
  });

  it("is signed out on a 401", async () => {
    routedFetch({ "GET /api/auth/session": problem(401, "kernel.not_signed_in") });
    const { result } = renderHook(() => useSession(), { wrapper: setUp().wrapper });
    await waitFor(() => {
      expect(result.current.status).toBe("signed-out");
    });
  });

  it("is unreachable when the site can't be reached, and reads again on retry", async () => {
    const { fetch } = routedFetch({});
    const { result } = renderHook(() => useSession(), { wrapper: setUp().wrapper });
    await waitFor(() => {
      expect(result.current.status).toBe("unreachable");
    });
    const session = result.current;
    if (session.status !== "unreachable") throw new Error("reached");
    expect(session.problem).toMatchObject({ status: 0, code: "kernel.unreachable" });
    routedFetch({ "GET /api/auth/session": { status: 200, body: { user: member } } });
    act(() => {
      session.retry();
    });
    await waitFor(() => {
      expect(result.current.status).toBe("signed-in");
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("is signed out when any call finds the session gone, and forgets what was the person's", async () => {
    routedFetch({
      "GET /api/auth/session": { status: 200, body: { user: member } },
      "GET /api/kernel/notifications": problem(401, "kernel.not_signed_in"),
    });
    const { queryClient, wrapper } = setUp();
    queryClient.setQueryData(["get", "/api/kernel/notifications"], { items: [], next_cursor: null, unread: 3 });
    queryClient.setQueryData(["get", "/api/kernel/site"], { name: "Kept" });
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => {
      expect(result.current.status).toBe("signed-in");
    });
    await expect(api.GET("/api/kernel/notifications")).rejects.toMatchObject({ status: 401 });
    await waitFor(() => {
      expect(result.current.status).toBe("signed-out");
    });
    expect(queryClient.getQueryData(["get", "/api/kernel/notifications"])).toBeUndefined();
    expect(queryClient.getQueryData(["get", "/api/kernel/site"])).toEqual({ name: "Kept" });
  });

  it("takes a sign-in's answer directly", async () => {
    routedFetch({ "GET /api/auth/session": problem(401, "kernel.not_signed_in") });
    const { queryClient, wrapper } = setUp();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => {
      expect(result.current.status).toBe("signed-out");
    });
    act(() => {
      setSessionUser(queryClient, member);
    });
    await waitFor(() => {
      expect(result.current.status).toBe("signed-in");
    });
  });
});

describe("useSignOut", () => {
  it("signs out on the server, then shows the person signed out", async () => {
    const { sent } = routedFetch({
      "GET /api/auth/session": { status: 200, body: { user: member } },
      "POST /api/auth/sign-out": { status: 204 },
    });
    const { queryClient, wrapper } = setUp();
    const { result } = renderHook(() => ({ session: useSession(), signOut: useSignOut() }), { wrapper });
    await waitFor(() => {
      expect(result.current.session.status).toBe("signed-in");
    });
    await act(() => result.current.signOut());
    expect(sent.map((request) => `${request.method} ${new URL(request.url).pathname}`)).toContain(
      "POST /api/auth/sign-out",
    );
    expect(queryClient.getQueryData(SESSION_KEY)).toBeNull();
    await waitFor(() => {
      expect(result.current.session.status).toBe("signed-out");
    });
  });

  it("counts an ended session as signed out", async () => {
    routedFetch({ "POST /api/auth/sign-out": problem(401, "kernel.not_signed_in") });
    const { queryClient, wrapper } = setUp();
    queryClient.setQueryData(SESSION_KEY, member);
    const { result } = renderHook(() => useSignOut(), { wrapper });
    await act(() => result.current());
    expect(queryClient.getQueryData(SESSION_KEY)).toBeNull();
  });

  it("stays signed in when the sign-out didn't reach the site", async () => {
    routedFetch({});
    const { queryClient, wrapper } = setUp();
    queryClient.setQueryData(SESSION_KEY, member);
    const { result } = renderHook(() => useSignOut(), { wrapper });
    await expect(result.current()).rejects.toMatchObject({ status: 0 });
    expect(queryClient.getQueryData(SESSION_KEY)).toEqual(member);
  });
});
