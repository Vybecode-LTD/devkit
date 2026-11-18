import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { renderWithKernel } from "../../testing";
import { Seo } from "./Seo";

function tag(selector: string, attribute = "content"): (string | null)[] {
  return [...document.head.querySelectorAll(selector)].map((each) => each.getAttribute(attribute));
}

/** The head as the server wrote it for the first page. */
function serversHead() {
  document.head.innerHTML = [
    "<title>Hello</title>",
    '<meta name="description" content="The first post." />',
    '<link rel="canonical" href="https://site.test/blog/hello" />',
    '<meta property="og:title" content="Hello" />',
    '<meta property="og:title" content="A stray second one" />',
    '<meta property="og:type" content="article" />',
    '<meta name="twitter:card" content="summary" />',
    '<script type="application/ld+json">{"@type":"BlogPosting"}</script>',
  ].join("");
}

beforeEach(serversHead);
afterEach(() => {
  document.head.innerHTML = "";
});

describe("<Seo>", () => {
  it("changes the server's tags in place, never a second of any", () => {
    renderWithKernel(<Seo title="Posts · Test Site" description="Every post." path="/blog" />, {
      site: { name: "Test Site", card_image: "/card.png" },
    });
    expect(document.title).toBe("Posts · Test Site");
    expect(tag('meta[name="description"]')).toEqual(["Every post."]);
    expect(tag('meta[property="og:title"]')).toEqual(["Posts · Test Site"]);
    expect(tag('link[rel="canonical"]', "href")).toEqual([`${location.origin}/blog`]);
    expect(tag('meta[property="og:url"]')).toEqual([`${location.origin}/blog`]);
    expect(tag('meta[property="og:type"]')).toEqual(["website"]);
    expect(tag('meta[property="og:image"]')).toEqual([`${location.origin}/card.png`]);
    expect(tag('meta[property="og:site_name"]')).toEqual(["Test Site"]);
    expect(tag('meta[name="twitter:card"]')).toEqual(["summary_large_image"]);
    expect(tag('meta[name="robots"]')).toEqual([]);
  });

  it("removes what the page doesn't have, and marks one not to index", () => {
    renderWithKernel(<Seo title="Sign in" noindex />);
    expect(tag('meta[name="description"]')).toEqual([]);
    expect(tag('meta[property="og:description"]')).toEqual([]);
    expect(tag('meta[property="og:image"]')).toEqual([]);
    expect(tag('meta[name="twitter:card"]')).toEqual(["summary"]);
    expect(tag('meta[name="robots"]')).toEqual(["noindex"]);
  });

  it("keeps the first page's JSON-LD there, and drops it once the person moves on", async () => {
    const { router } = renderWithKernel(<Seo title="Hello" />, { path: location.pathname });
    expect(tag('script[type="application/ld+json"]', "type")).toHaveLength(1);
    await act(() => router.navigate("/elsewhere"));
    expect(tag('script[type="application/ld+json"]', "type")).toHaveLength(0);
  });

  it("takes the page's own picture over the site's card", () => {
    renderWithKernel(<Seo title="Hello" image="https://cdn.test/hello.png" type="article" />, {
      site: { card_image: "/card.png" },
    });
    expect(tag('meta[property="og:image"]')).toEqual(["https://cdn.test/hello.png"]);
    expect(tag('meta[property="og:type"]')).toEqual(["article"]);
  });
});
