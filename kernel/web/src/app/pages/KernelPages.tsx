/**
 * The kernel's pages that every site has from the start: the home page (until
 * a module owns `/`), the 404 page, the no-access page, the problem shown
 * while the site can't be reached, and, until the screens that fill them are
 * built (K4.5 to K4.8), each kernel page's plain heading.
 *
 * The home page says what the server's copy says, word for word, so a
 * crawler and a person read the same page (the parity test).
 */
import { Link } from "react-router";

import type { ApiProblem } from "../../api/problem";
import { Seo } from "../../seo/Seo";
import { useSite, useSiteRead } from "../../site/site";
import type { KernelPage } from "../pages";

/** "{title} · {name}", as the server titles a page it doesn't index. */
export function useTitle(title: string): string {
  const site = useSite();
  return site ? `${title} · ${site.name}` : title;
}

export function Home() {
  const found = useSiteRead();
  if (found.status === "failed") return <Unreachable problem={found.problem} retry={found.retry} />;
  if (found.status === "loading") return null;
  const site = found.value;
  return (
    <>
      <Seo title={site.name} description={site.description} path="/" type="website" />
      <h1>{site.name}</h1>
      {site.description ? <p>{site.description}</p> : null}
    </>
  );
}

export function NotFound() {
  return (
    <>
      <Seo title={useTitle("Page not found")} noindex />
      <h1>Page not found</h1>
      <p>There's no page at this address. It may have moved, or the link may be wrong.</p>
      <p>
        <Link to="/">Go to the home page</Link>
      </p>
    </>
  );
}

export function NoAccess() {
  return (
    <>
      <Seo title={useTitle("No access")} noindex />
      <h1>You can't open this page</h1>
      <p>Your account doesn't have access to it. If you think it should, ask the person who runs this site.</p>
      <p>
        <Link to="/">Go to the home page</Link>
      </p>
    </>
  );
}

export function Unreachable({ problem, retry }: { problem: ApiProblem; retry: () => void }) {
  return (
    <div role="alert">
      <h1>The site can't be reached</h1>
      <p>{problem.status === 0 ? "Check your connection, then try again." : "Something went wrong on our side. Try again in a moment."}</p>
      <button type="button" onClick={retry}>
        Try again
      </button>
    </div>
  );
}

/** A kernel page whose screen isn't built yet: its heading, and nothing to act on. */
export function Pending({ page }: { page: KernelPage }) {
  return (
    <>
      <Seo title={useTitle(page.title)} noindex />
      <h1>{page.title}</h1>
      <p>This page isn't ready yet.</p>
    </>
  );
}
