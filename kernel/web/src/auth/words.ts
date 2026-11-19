/**
 * What the sign-in and account screens say when a call is refused for a
 * reason any of them can meet: no connection, too many tries, a busy or
 * broken server. Each screen says its own refusals itself.
 */
import type { ApiProblem } from "../api/problem";

/** "2 minutes", "a minute", "30 seconds": how long a 429 asks to wait. */
export function waitFor(problem: ApiProblem): string {
  const given = problem.extra.retry_after;
  const seconds = typeof given === "number" && Number.isFinite(given) ? Math.max(1, Math.ceil(given)) : 60;
  if (seconds < 60) return seconds === 1 ? "a second" : `${String(seconds)} seconds`;
  const minutes = Math.ceil(seconds / 60);
  return minutes === 1 ? "a minute" : `${String(minutes)} minutes`;
}

/** The words for a refusal every screen meets the same way, or null for one the screen says itself. */
export function commonProblem(problem: ApiProblem): string | null {
  if (problem.status === 0) return "Check your connection, then try again.";
  if (problem.code === "kernel.rate_limited") return `Too many tries. Wait ${waitFor(problem)}, then try again.`;
  if (problem.code === "kernel.busy") return "The site is busy. Try again in a moment.";
  if (problem.status >= 500) return "Something went wrong on our side. Try again in a moment.";
  return null;
}

/** A refusal's words: the screen's own for its codes, else the common ones, else the server's. */
export function said(problem: ApiProblem, own: Readonly<Record<string, string>> = {}): string {
  return own[problem.code] ?? commonProblem(problem) ?? (problem.detail || "That didn't work. Try again.");
}
