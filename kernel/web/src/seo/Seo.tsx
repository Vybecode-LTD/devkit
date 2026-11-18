/**
 * `<Seo>` (K4 contract §2): keeps the head tags the server wrote current as
 * the person moves between pages, changing them in place and never adding a
 * second of any. The first page's JSON-LD is the server's word for that page
 * alone, so it's dropped once the person has gone elsewhere.
 *
 * The tags are the ones `kernel.server_copy.head` writes: title, description,
 * robots, canonical, Open Graph and the Twitter card.
 */
import { useEffect } from "react";
import { useLocation } from "react-router";

import { useSite } from "../site/site";

export type SeoProps = {
  /** The whole title, as the tab shows it. */
  title: string;
  description?: string;
  /** The page's own address, for the canonical; the current one by default. */
  path?: string;
  /** The picture it's shared with; the site's card by default. */
  image?: string;
  /** Open Graph's type: website, article and the like. */
  type?: string;
  noindex?: boolean;
};

/** The address the document was first loaded at: its JSON-LD is that page's. */
const FIRST = typeof location === "undefined" ? "" : location.pathname;

type Tag = { tag: "meta" | "link"; key: "name" | "property" | "rel"; id: string; attribute: "content" | "href" };

const TAGS = {
  description: { tag: "meta", key: "name", id: "description", attribute: "content" },
  robots: { tag: "meta", key: "name", id: "robots", attribute: "content" },
  canonical: { tag: "link", key: "rel", id: "canonical", attribute: "href" },
  ogTitle: { tag: "meta", key: "property", id: "og:title", attribute: "content" },
  ogDescription: { tag: "meta", key: "property", id: "og:description", attribute: "content" },
  ogUrl: { tag: "meta", key: "property", id: "og:url", attribute: "content" },
  ogType: { tag: "meta", key: "property", id: "og:type", attribute: "content" },
  ogImage: { tag: "meta", key: "property", id: "og:image", attribute: "content" },
  ogSiteName: { tag: "meta", key: "property", id: "og:site_name", attribute: "content" },
  twitterCard: { tag: "meta", key: "name", id: "twitter:card", attribute: "content" },
} as const satisfies Record<string, Tag>;

/** Sets the one tag `which` names to `value`, or removes it for `undefined`. */
function put(which: Tag, value: string | undefined): void {
  const found = [...document.head.querySelectorAll(`${which.tag}[${which.key}="${which.id}"]`)];
  const [first, ...extra] = found;
  for (const each of extra) each.remove();
  if (value === undefined) {
    first?.remove();
    return;
  }
  const element = first ?? document.head.appendChild(document.createElement(which.tag));
  element.setAttribute(which.key, which.id);
  element.setAttribute(which.attribute, value);
}

function absolute(url: string): string {
  return new URL(url, location.origin).href;
}

export function Seo({ title, description, path, image, type = "website", noindex = false }: SeoProps) {
  const site = useSite();
  const here = useLocation().pathname;
  useEffect(() => {
    document.title = title;
    const url = absolute(path ?? here);
    const picture = image || site?.card_image || undefined;
    const text = description || undefined;
    put(TAGS.description, text);
    put(TAGS.robots, noindex ? "noindex" : undefined);
    put(TAGS.canonical, url);
    put(TAGS.ogTitle, title);
    put(TAGS.ogDescription, text);
    put(TAGS.ogUrl, url);
    put(TAGS.ogType, type);
    put(TAGS.ogImage, picture === undefined ? undefined : absolute(picture));
    if (site) put(TAGS.ogSiteName, site.name);
    put(TAGS.twitterCard, picture === undefined ? "summary" : "summary_large_image");
    if (here !== FIRST) {
      for (const data of document.head.querySelectorAll('script[type="application/ld+json"]')) data.remove();
    }
  }, [title, description, path, image, type, noindex, site, here]);
  return null;
}
