"""This site's own pages, as crawlers read them (SPEC.md section 9, decision 0048).

Every public page the web app draws from `web/src/site/site.ts` has its
server copy here: the same title, words and JSON-LD, read from the same rows,
so a crawler that runs no script reads what a person sees. `SITE_PAGES` lists
the patterns and answers them; `app/main.py` gives it to `create_app(site=...)`.
The site's pages are always on, and at the same rank win over a module's.

To add a page: its pattern in `PUBLIC` (or `MEMBER`, which the server answers
with the shell and noindex), its answer in `SitePages.page`, its entry in
`sitemap`, and its React page in `web/src/site/` with the same words.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from kernel import server_copy

PUBLIC = ("/",)
MEMBER: tuple[str, ...] = ()


class SitePages(server_copy.Pages):
    async def page(
        self, db: AsyncSession, path: str, params: Mapping[str, str]
    ) -> server_copy.Page | server_copy.Moved | None:
        if path == "/":
            # The home page: the site's name and description (Admin, Settings, Site),
            # as web/src/site/Home.tsx draws them.
            return server_copy.home(await server_copy.identity(db))
        return None

    async def sitemap(self, db: AsyncSession) -> Iterable[server_copy.Entry]:
        return [server_copy.Entry("/")]


SITE_PAGES = server_copy.SitePages(public=PUBLIC, member=MEMBER, pages=SitePages())
