/**
 * What a page shows when it fails to load or draw (the router's error
 * element). A page whose code can't be fetched usually means a new build
 * replaced it, so the person is offered a reload.
 */
import { isRouteErrorResponse, useRouteError } from "react-router";

import { NotFound } from "./pages/KernelPages";

/** Whether `error` is a page's code that didn't arrive (a new build, a dropped connection). */
export function isMissingCode(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return /dynamically imported module|Importing a module script failed|error loading dynamically|ChunkLoadError/i.test(
    `${error.name} ${error.message}`,
  );
}

function reload(): void {
  location.reload();
}

function Failed({ heading, words }: { heading: string; words: string }) {
  return (
    <main id="main">
      <h1>{heading}</h1>
      <p>{words}</p>
      <button type="button" onClick={reload}>
        Reload
      </button>
    </main>
  );
}

export function RouteError() {
  const error = useRouteError();
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFound />;
  if (isMissingCode(error)) {
    return <Failed heading="This page has changed" words="A newer version of the site is out. Reload to get it." />;
  }
  console.error("A page failed to show.", error);
  return <Failed heading="Something went wrong" words="This page couldn't be shown. Reload to try again." />;
}
