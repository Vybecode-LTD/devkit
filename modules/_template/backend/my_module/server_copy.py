"""my-module: its public pages, readable by crawlers that run no JavaScript
(kernel.server_copy, SPEC.md section 9, decision 0041).

Only a module with public pages has this file. It lists their patterns in
module.json's `routes.public` (`/my-module`, `/my-module/:slug`) and sets
`PAGES` to a `server_copy.Pages`; the start refuses one without the other.
For each address one of its patterns matches, the kernel asks `page` and
writes what it answers into the app's shell: the head tags, the words as
plain HTML and the JSON-LD. React's first render replaces the words.

`page` reads the same rows the module's API reads (its `service.py`), so the
two never say different things, and answers in one call:

- a `server_copy.Page` with its title, description, words and JSON-LD;
- a `server_copy.Moved` for an old address, a 301 to a path on this site;
- None for an address it doesn't have: a real 404, never a 200 shell.

A database error is left to the kernel, which answers 503 ("try later").
Build the words with the kernel's builders, which escape every value: one
`h1`, an `h2` per section, `p`, `ul`, `link` and `time`. HTML made elsewhere,
such as a post's Markdown, goes through `server_copy.cleaned`.

`sitemap` lists every public page for sitemap.xml; an entry with a title is
also a link in llms.txt. For example:

    from kernel import server_copy
    from my_module import service

    class MyPages(server_copy.Pages):
        async def page(self, db, path, params):
            if path == "/my-module":
                items = await service.listed(db)
                return server_copy.Page(
                    "Items", "Every item we have.",
                    [server_copy.h1("Items"),
                     server_copy.ul(*(server_copy.link(i.title, f"/my-module/{i.slug}") for i in items))],
                )
            item = await service.by_slug(db, params["slug"])
            if item is None:
                old = await service.renamed_from(db, params["slug"])
                return server_copy.Moved(f"/my-module/{old.slug}") if old else None
            return server_copy.Page(
                item.title, item.summary,
                server_copy.article(server_copy.h1(item.title), server_copy.p(item.summary)),
                data=({"@context": "https://schema.org", "@type": "Thing", "name": item.title},),
                modified=item.updated_at,
            )

        async def sitemap(self, db):
            return [
                server_copy.Entry("/my-module", title="Items"),
                *(server_copy.Entry(f"/my-module/{i.slug}", modified=i.updated_at, title=i.title,
                                    description=i.summary)
                  for i in await service.listed(db)),
            ]

    PAGES = MyPages()

This module has no public pages (its `routes.public` is empty), so it has none.
"""

from __future__ import annotations

from kernel import server_copy

PAGES: server_copy.Pages | None = None
