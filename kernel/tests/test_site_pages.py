"""The site's own pages (K5 contract change 5, decision 0048): `create_app(site=...)`.

A site's own pages are always on (no switch on Features), answer with their
server copy as a module's do, and win a tie with a module's pattern at the
same rank, saying so in the log; a more fixed module pattern still wins.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from kernel import server_copy
from kernel.modules import RESERVED_IDS
from kernel.server_copy import SITE, Entry, Page, SitePages

from .conftest import AppFactory, Client, FakePages, public_module

HOME = Page("Our home", "Where it starts.", [server_copy.h1("Our home"), server_copy.p("Hello.")])
ABOUT = Page("About us", "Who we are.", server_copy.h1("About us"))

INDEX = (
    '<!doctype html>\n<html lang="en">\n  <head>\n'
    "    <!-- page-head -->\n    <!-- /page-head -->\n  </head>\n  <body>\n"
    '    <div id="root"><!-- page-body --><!-- /page-body --></div>\n  </body>\n</html>\n'
)


def _site(**changes: object) -> SitePages:
    values: dict[str, object] = {
        "public": ("/", "/about"),
        "member": ("/library",),
        "pages": FakePages(
            {"/": HOME, "/about": ABOUT},
            entries=[Entry("/"), Entry("/about", title="About us", description="Who we are.")],
        ),
    }
    values.update(changes)
    return SitePages(**values)  # type: ignore[arg-type]


def _title(text: str) -> str:
    found = re.search(r"<title>(.*?)</title>", text)
    assert found is not None
    return found.group(1)


# --- which pattern answers -------------------------------------------------------------


def test_the_sites_pages_answer_whatever_modules_are_on() -> None:
    routes = server_copy.build([], site=_site())
    for on in (None, frozenset(), frozenset({"blog"})):
        found = routes.resolve("/about", on)
        assert found is not None
        assert (found.module, found.member) == (SITE, False)
    member = routes.resolve("/library", frozenset())
    assert member is not None
    assert (member.module, member.member) == (SITE, True)
    assert routes.home_owner(frozenset()) == SITE


def test_the_site_wins_a_tie_with_a_module_and_the_log_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="kernel.server_copy"):
        routes = server_copy.build(
            [public_module("pages", public=["/", "/:slug"], pages=FakePages())],
            site=_site(public=("/", "/about")),
        )
    assert getattr(routes.resolve("/"), "module", None) == SITE
    assert getattr(routes.resolve("/about"), "module", None) == SITE  # /:slug is less fixed
    assert getattr(routes.resolve("/contact"), "module", None) == "pages"
    assert [record.getMessage() for record in caplog.records] == [
        "The site's / takes the place of pages's /."
    ]


def test_the_site_wins_a_tie_of_another_kind_too() -> None:
    """The site's member page over a module's public one, as the web's router
    has it (Codex on #92)."""
    routes = server_copy.build(
        [public_module("shelf", public=["/library"], pages=FakePages())], site=_site()
    )
    found = routes.resolve("/library")
    assert found is not None
    assert (found.module, found.member) == (SITE, True)


def test_a_more_fixed_module_pattern_beats_the_sites() -> None:
    routes = server_copy.build(
        [public_module("shop", public=["/shop"], pages=FakePages())],
        site=_site(public=("/:page",)),
    )
    assert getattr(routes.resolve("/shop"), "module", None) == "shop"
    assert getattr(routes.resolve("/shop", frozenset()), "module", None) == SITE  # shop is off
    assert getattr(routes.resolve("/about"), "module", None) == SITE


def test_the_sites_own_patterns_may_not_tie() -> None:
    with pytest.raises(ValueError, match="site's /:a and site's /:b answer the same addresses"):
        server_copy.build([], site=_site(public=("/:a", "/:b")))


@pytest.mark.parametrize("pattern", ["/account/:tab", "/sign-in"])
def test_the_site_cant_take_a_kernel_page(pattern: str) -> None:
    with pytest.raises(ValueError, match=f"site's route {re.escape(pattern)} takes the kernel's"):
        server_copy.build([], site=_site(public=(pattern,)))


@pytest.mark.parametrize("pattern", ["/api/things", "/admin/things", "/sitemap.xml", "about"])
def test_the_sites_patterns_are_checked_as_a_modules_are(pattern: str) -> None:
    with pytest.raises(ValueError, match="can't be a page"):
        server_copy.build([], site=_site(public=(pattern,)))


def test_the_sites_public_pages_need_its_pages_and_the_reverse() -> None:
    with pytest.raises(ValueError, match="The site lists public pages but gives no pages"):
        server_copy.build([], site=_site(pages=None))
    with pytest.raises(ValueError, match="The site gives pages but lists no public pages"):
        server_copy.build([], site=_site(public=()))
    with pytest.raises(ValueError, match=r"The site's pages must be a server_copy.Pages"):
        server_copy.build([], site=_site(pages=object()))


def test_a_site_of_member_pages_only_needs_no_pages() -> None:
    routes = server_copy.build([], site=_site(public=(), pages=None, member=("/library",)))
    assert getattr(routes.resolve("/library"), "member", None) is True
    assert routes.with_pages() == []


def test_no_module_may_take_the_sites_id() -> None:
    assert SITE == "site"
    assert SITE in RESERVED_IDS
    with pytest.raises(ValueError, match="site names the site's own pages"):
        server_copy.build([public_module("site", public=["/x"], pages=FakePages())])


async def test_the_sites_entries_are_listed_whatever_is_on() -> None:
    routes = server_copy.build(
        [public_module("blog", public=["/blog"], pages=FakePages(entries=[Entry("/blog")]))],
        site=_site(),
    )
    found = await server_copy.entries(None, routes, frozenset())  # type: ignore[arg-type]
    assert [(owner, entry.path) for owner, entry in found] == [(SITE, "/"), (SITE, "/about")]
    assert routes.name(SITE) == "Pages"
    assert server_copy.build([], site=_site(name="Our pages")).name(SITE) == "Our pages"


# --- over HTTP ---------------------------------------------------------------------------


async def test_the_sites_pages_over_http(app_factory: AppFactory, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX, "utf-8")
    app = app_factory([], site=_site(), site_name="Test Site", web_dist=str(dist), modules="")
    async with Client(app) as client:
        home = await client.get("/")
        about = await client.get("/about")
        library = await client.get("/library")
        missing = await client.get("/nowhere")
        llms = await client.get("/llms.txt")
        sitemap = await client.get("/sitemap.xml")
    assert (home.status_code, _title(home.text)) == (200, "Our home")
    assert "<h1>Our home</h1>" in home.text
    assert (about.status_code, _title(about.text)) == (200, "About us")
    assert library.status_code == 200
    assert '<meta name="robots" content="noindex"' in library.text
    assert missing.status_code == 404
    assert "## Pages\n\n- [About us](https://mechframe.test/about): Who we are.\n" in llms.text
    assert "<loc>https://mechframe.test/about</loc>" in sitemap.text
