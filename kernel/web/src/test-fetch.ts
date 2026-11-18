/**
 * For the kernel's own tests: a fetch that answers by method and path, put
 * in place of the page's, and the problem bodies the API answers with. A
 * path it wasn't given fails as a dropped connection does.
 */
import { vi } from "vitest";

export type Answer = { status: number; body?: unknown; type?: string };

type Answers = Record<string, Answer | ((request: Request) => Answer)>;

export function routedFetch(answers: Answers) {
  const sent: Request[] = [];
  const fetch = vi.fn((request: Request) => {
    sent.push(request);
    const found = answers[`${request.method} ${new URL(request.url).pathname}`];
    if (!found) return Promise.reject(new TypeError("Failed to fetch"));
    const answer = typeof found === "function" ? found(request) : found;
    const text = answer.body === undefined ? null : JSON.stringify(answer.body);
    return Promise.resolve(
      new Response(text, { status: answer.status, headers: { "content-type": answer.type ?? "application/json" } }),
    );
  });
  vi.stubGlobal("fetch", fetch);
  return { fetch, sent };
}

export function problem(status: number, code: string): Answer {
  return {
    status,
    type: "application/problem+json",
    body: { type: `urn:mechframe:problem:${code}`, title: "Refused", status, detail: "Refused.", code },
  };
}
