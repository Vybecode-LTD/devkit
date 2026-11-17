"""kernel.server_copy: which module answers an address, each page's head,
words and JSON-LD, the builders, the default home page, sitemap.xml,
robots.txt, llms.txt and the site's identity (decision 0041)."""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import server_copy
from kernel.modules import InstalledModule, Manifest
from kernel.server_copy import Entry, Html, Identity, Moved, Page, SiteSettings
from kernel.settings import settings

from .conftest import FakePages, public_module

SITE = "https://devkit.test"

IDENT = Identity(name="Test Site", url=SITE)


def _scripts(tags: str) -> list[str]:
    return re.findall(r'<script type="application/ld\+json">(.*?)</script>', tags, re.S)


def _meta(tags: str, key: str) -> str | None:
    found = re.search(rf'<meta (?:property|name)="{re.escape(key)}" content="([^"]*)"', tags)
    return found.group(1) if found else None


def _canonical(tags: str) -> str | None:
    found = re.search(r'<link rel="canonical" href="([^"]*)"', tags)
    return found.group(1) if found else None


# --- which module answers ----------------------------------------------------------


def test_more_fixed_segments_win() -> None:
    posts, archive = FakePages(), FakePages()
    routes = server_copy.build(
        [
            public_module("blog", public=["/blog", "/blog/:slug"], pages=posts),
            public_module("archive", public=["/blog/archive"], pages=archive),
        ]
    )
    found = routes.resolve("/blog/archive")
    assert found is not None
    assert (found.module, found.params) == ("archive", {})
    found = routes.resolve("/blog/hello")
    assert found is not None
    assert (found.module, found.params) == ("blog", {"slug": "hello"})
    found = routes.resolve("/blog")
    assert found is not None
    assert (found.module, found.member) == ("blog", False)
    assert routes.pages_of("archive") is archive


def test_a_fixed_page_wins_over_a_catch_all_of_one_segment() -> None:
    routes = server_copy.build(
        [
            public_module("pages", public=["/:page"], pages=FakePages()),
            public_module("shop", public=["/shop"], pages=FakePages()),
        ]
    )
    assert getattr(routes.resolve("/shop"), "module", None) == "shop"
    found = routes.resolve("/about")
    assert found is not None
    assert (found.module, found.params) == ("pages", {"page": "about"})


def test_an_address_no_pattern_takes_is_no_ones() -> None:
    routes = server_copy.build([public_module("blog", public=["/blog/:slug"], pages=FakePages())])
    assert routes.resolve("/blog") is None
    assert routes.resolve("/blog/a/b") is None
    assert routes.resolve("/") is None
    assert not routes.owns_home


def test_a_member_page_is_matched_as_one() -> None:
    routes = server_copy.build(
        [
            public_module(
                "account", public=["/people/:name"], member=["/account/:tab"], pages=FakePages()
            )
        ]
    )
    found = routes.resolve("/account/settings")
    assert found is not None
    assert (found.module, found.member) == ("account", True)
    assert found.params == {"tab": "settings"}


def test_a_module_may_own_the_home_page() -> None:
    routes = server_copy.build([public_module("site", public=["/"], pages=FakePages())])
    assert routes.owns_home
    found = routes.resolve("/")
    assert found is not None
    assert (found.module, found.params) == ("site", {})


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (["/:a"], ["/:b"]),
        (["/a/:x"], ["/:y/b"]),
        (["/blog"], ["/blog"]),
        (["/"], ["/"]),
    ],
)
def test_two_modules_answering_the_same_address_at_one_rank_are_refused(
    first: list[str], second: list[str]
) -> None:
    with pytest.raises(ValueError, match="same addresses"):
        server_copy.build(
            [
                public_module("one", public=first, pages=FakePages()),
                public_module("two", public=second, pages=FakePages()),
            ]
        )


def test_a_member_page_and_a_public_one_at_one_address_are_refused() -> None:
    with pytest.raises(ValueError, match="same addresses"):
        server_copy.build(
            [
                public_module("one", public=["/account"], pages=FakePages()),
                public_module("two", member=["/account"]),
            ]
        )


def test_one_modules_own_patterns_may_not_tie_either() -> None:
    with pytest.raises(ValueError, match="same addresses"):
        server_copy.build([public_module("one", public=["/x/:a", "/x/:b"], pages=FakePages())])


def test_patterns_that_never_meet_may_share_a_rank() -> None:
    routes = server_copy.build(
        [
            public_module("one", public=["/a/:x"], pages=FakePages()),
            public_module("two", public=["/b/:x", "/a/:x/more"], pages=FakePages()),
        ]
    )
    assert getattr(routes.resolve("/b/1"), "module", None) == "two"
    assert getattr(routes.resolve("/a/1"), "module", None) == "one"


def test_public_routes_need_pages() -> None:
    with pytest.raises(ValueError, match="no pages"):
        server_copy.build([public_module("blog", public=["/blog"])])


def test_pages_need_public_routes() -> None:
    with pytest.raises(ValueError, match="no public routes"):
        server_copy.build([public_module("blog", pages=FakePages())])


def test_pages_must_be_pages() -> None:
    with pytest.raises(ValueError, match=r"server_copy.Pages"):
        server_copy.build([public_module("blog", public=["/blog"], pages=object())])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "pattern",
    [
        "/blog/",
        "//blog",
        "blog",
        "/a b",
        "/a/:",
        "/:1st",
        "/:a/:a",
        "/api/blog",
        "/api",
        "/admin",
        "/admin/blog",
        "/sitemap.xml",
        "/robots.txt",
        "/llms.txt",
        "/a/../b",
        "/a/./b",
    ],
)
def test_a_pattern_the_kernel_cant_take_is_refused(pattern: str) -> None:
    with pytest.raises(ValueError, match=re.escape(pattern)):
        server_copy.build([public_module("blog", public=[pattern], pages=FakePages())])


def test_a_member_pattern_is_checked_too() -> None:
    with pytest.raises(ValueError, match="/admin/me"):
        server_copy.build([public_module("blog", member=["/admin/me"])])


# --- the head ------------------------------------------------------------------------


def test_every_url_in_the_head_is_absolute() -> None:
    page = Page("Hello", "A post.", Html(""), image="/img/hello.png", query="?page=2")
    tags = server_copy.head(page, "/blog/hello", IDENT)
    assert _canonical(tags) == f"{SITE}/blog/hello?page=2"
    assert _meta(tags, "og:url") == f"{SITE}/blog/hello?page=2"
    assert _meta(tags, "og:image") == f"{SITE}/img/hello.png"
    assert "<title>Hello</title>" in tags
    assert _meta(tags, "description") == "A post."
    assert _meta(tags, "og:title") == "Hello"
    assert _meta(tags, "og:description") == "A post."
    assert _meta(tags, "og:type") == "website"
    assert _meta(tags, "og:site_name") == "Test Site"
    assert _meta(tags, "twitter:card") == "summary_large_image"
    assert _meta(tags, "robots") is None


def test_an_absolute_image_is_kept() -> None:
    page = Page("Hello", "", Html(""), image="https://cdn.test/a.png")
    assert _meta(server_copy.head(page, "/", IDENT), "og:image") == "https://cdn.test/a.png"


def test_the_image_falls_back_to_the_sites_card() -> None:
    page = Page("Hello", "", Html(""))
    ident = Identity(name="Test Site", url=SITE, card_image="/card.png")
    assert _meta(server_copy.head(page, "/x", ident), "og:image") == f"{SITE}/card.png"
    ident = Identity(name="Test Site", url=SITE, card_image="https://cdn.test/card.png")
    assert _meta(server_copy.head(page, "/x", ident), "og:image") == "https://cdn.test/card.png"


def test_with_no_image_at_all_the_card_is_a_summary() -> None:
    tags = server_copy.head(Page("Hello", "", Html("")), "/x", IDENT)
    assert _meta(tags, "og:image") is None
    assert _meta(tags, "twitter:card") == "summary"


def test_an_article_says_when() -> None:
    published = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
    modified = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    page = Page("Post", "", Html(""), kind="article", published=published, modified=modified)
    tags = server_copy.head(page, "/blog/post", IDENT)
    assert _meta(tags, "og:type") == "article"
    assert _meta(tags, "article:published_time") == "2026-11-01T09:30:00+00:00"
    assert _meta(tags, "article:modified_time") == "2026-11-02T10:00:00+00:00"
    assert (
        _meta(server_copy.head(Page("P", "", Html("")), "/", IDENT), "article:published_time")
        is None
    )


def test_a_noindex_page_says_so() -> None:
    tags = server_copy.head(Page("Draft", "", Html(""), noindex=True), "/d", IDENT)
    assert _meta(tags, "robots") == "noindex"


def test_every_tag_is_escaped() -> None:
    evil = '"><script>alert(1)</script>&'
    page = Page(evil, evil, Html(""), image="/a.png?x=" + evil)
    ident = Identity(name=evil, url=SITE)
    tags = server_copy.head(page, "/p", ident)
    assert "<script>" not in tags
    assert '"><' not in tags
    assert "<title>&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;</title>" in tags
    assert _meta(tags, "og:site_name") == "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;&amp;"


def test_the_plain_head_is_a_title_noindex_and_the_name() -> None:
    tags = server_copy.plain_head("Page not found · <Test>", IDENT)
    assert "<title>Page not found · &lt;Test&gt;</title>" in tags
    assert _meta(tags, "robots") == "noindex"
    assert _meta(tags, "og:site_name") == "Test Site"
    assert _canonical(tags) is None


@pytest.mark.parametrize(
    "value",
    [
        "</script><script>alert(1)</script>",
        "</SCRIPT >",
        "<!-- <script>",
        "x & y > z",
    ],
)
def test_json_ld_cant_close_its_tag(value: str) -> None:
    data = {"@context": "https://schema.org", "@type": "Thing", "name": value}
    page = Page("T", "", Html(""), data=(data,))
    tags = server_copy.head(page, "/t", IDENT)
    (found,) = _scripts(tags)
    assert "<" not in found
    assert ">" not in found
    assert "&" not in found
    assert json.loads(found) == data


def test_each_json_ld_object_is_a_block_of_its_own() -> None:
    first = {"@type": "Thing", "name": "one"}
    second = {"@type": "Thing", "name": "two"}
    tags = server_copy.head(Page("T", "", Html(""), data=(first, second)), "/t", IDENT)
    assert [json.loads(found) for found in _scripts(tags)] == [first, second]


# --- what a page may hold ------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "Website"},
        {"kind": "web site"},
        {"kind": ""},
        {"query": "page=2"},
        {"query": "?a#b"},
        {"query": "?a\nb"},
        {"image": "javascript:alert(1)"},
        {"image": "//evil.test/a.png"},
        {"image": "data:image/png;base64,AA"},
        {"image": "/a\nb.png"},
        {"data": ("not a dict",)},
    ],
)
def test_a_page_refuses_what_it_cant_be(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"isn't|JSON-LD"):
        Page("T", "", Html(""), **kwargs)


@pytest.mark.parametrize(
    "path",
    ["//evil.test", "https://evil.test/", "evil", "/a\r\nSet-Cookie: x=1", "/\\evil.test", ""],
)
def test_a_move_is_only_ever_to_a_path_on_this_site(path: str) -> None:
    with pytest.raises(ValueError, match="isn't a path on this site"):
        Moved(path)


@pytest.mark.parametrize("path", ["", "blog", "//x", "/a?b", "/a#b", "/a\nb"])
def test_an_entry_is_a_path_on_this_site(path: str) -> None:
    with pytest.raises(ValueError, match="isn't a path on this site"):
        Entry(path)


# --- the builders ---------------------------------------------------------------------


def test_the_builders_escape_every_value() -> None:
    evil = '<b onclick="x">&</b>'
    escaped = "&lt;b onclick=&quot;x&quot;&gt;&amp;&lt;/b&gt;"
    assert server_copy.h1(evil) == f"<h1>{escaped}</h1>"
    assert server_copy.h2(evil) == f"<h2>{escaped}</h2>"
    assert server_copy.h3(evil) == f"<h3>{escaped}</h3>"
    assert server_copy.p(evil) == f"<p>{escaped}</p>"
    assert server_copy.ul(evil, "b") == f"<ul><li>{escaped}</li><li>b</li></ul>"
    assert server_copy.section(evil) == f"<section>{escaped}</section>"
    assert server_copy.article(evil) == f"<article>{escaped}</article>"
    assert server_copy.link(evil, '/x?y="z"') == f'<a href="/x?y=&quot;z&quot;">{escaped}</a>'


def test_the_builders_nest_without_escaping_twice() -> None:
    words = server_copy.section(
        server_copy.h2("Hours"),
        server_copy.p("Open ", server_copy.time(date(2026, 11, 17), "today"), "."),
        server_copy.ul(server_copy.link("Menu", "/menu"), None, "Bar & grill"),
    )
    assert words == (
        '<section><h2>Hours</h2><p>Open <time datetime="2026-11-17">today</time>.</p>'
        '<ul><li><a href="/menu">Menu</a></li><li>Bar &amp; grill</li></ul></section>'
    )


def test_a_number_in_words_is_text() -> None:
    assert server_copy.p("Open ", 7, " days") == "<p>Open 7 days</p>"


def test_a_time_says_itself_when_given_no_words() -> None:
    when = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)
    assert server_copy.time(when) == (
        '<time datetime="2026-11-17T18:00:00+00:00">2026-11-17T18:00:00+00:00</time>'
    )


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        " javascript:alert(1)",
        "JAVASCRIPT:x",
        "data:text/html,x",
        "//evil.test",
        "/\\evil.test",
        "vbscript:x",
        "",
    ],
)
def test_a_link_somewhere_unsafe_keeps_only_its_words(href: str) -> None:
    assert server_copy.link("Click", href) == "Click"


@pytest.mark.parametrize(
    "href",
    [
        "/menu",
        "https://social.test/us",
        "http://old.test",
        "mailto:hi@devkit.test",
        "tel:+15550100",
        "#top",
    ],
)
def test_a_link_to_a_page_an_address_or_a_number_is_kept(href: str) -> None:
    assert server_copy.link("x", href) == f'<a href="{href}">x</a>'


def test_text_in_words_is_text() -> None:
    page = Page("T", "", "<b>bold</b> & <script>x()</script>")
    assert (
        server_copy.words(page) == "&lt;b&gt;bold&lt;/b&gt; &amp; &lt;script&gt;x()&lt;/script&gt;"
    )


def test_words_may_be_a_list() -> None:
    page = Page("T", "", [server_copy.h1("A"), "b & c", None, server_copy.p("d")])
    assert server_copy.words(page) == "<h1>A</h1>b &amp; c<p>d</p>"


def test_words_never_hold_style_or_script() -> None:
    made_by_hand = Html(
        '<h1 style="color:red" onclick="x()">A</h1><script>evil()</script>'
        '<style>p{}</style><p onmouseover="y()">b</p><iframe src="/x"></iframe>'
        '<a href="javascript:z()">c</a><img src="/a.png" onerror="w()">'
    )
    found = server_copy.words(Page("T", "", made_by_hand))
    for banned in ("style", "script", "onclick", "onmouseover", "onerror", "iframe", "javascript"):
        assert banned not in found.lower(), banned
    assert "<h1>A</h1>" in found
    assert "<p>b</p>" in found


def test_cleaned_keeps_a_posts_markup_but_not_its_h1() -> None:
    post = (
        '<h1>Title</h1><h2 id="x">Part</h2><p>Some <strong>bold</strong> and '
        '<a href="https://ref.test" target="_blank">a link</a>.</p>'
        "<pre><code>x = 1</code></pre><blockquote>q</blockquote>"
        '<img src="/pic.png" alt="A pic" style="width:9px"><table><tr><td>1</td></tr></table>'
        '<p style="x">s</p><script>bad()</script>'
    )
    found = server_copy.cleaned(post)
    assert "<h1>" not in found
    assert "Title" in found
    assert "<h2>Part</h2>" in found
    assert '<a href="https://ref.test">a link</a>' in found
    assert "<pre><code>x = 1</code></pre>" in found
    assert '<img src="/pic.png" alt="A pic">' in found
    assert "<td>1</td>" in found
    assert "style" not in found
    assert "script" not in found
    assert "target" not in found
    assert server_copy.words(Page("T", "", found)) == found


# --- the default home page ----------------------------------------------------------


def test_the_default_home_page_names_the_site() -> None:
    ident = Identity(
        name="Test & Co",
        url=SITE,
        description="We make <things>.",
        kind="MusicGroup",
        logo="/logo.png",
        same_as=("https://social.test/us",),
    )
    home = server_copy.home(ident)
    assert (home.title, home.description) == ("Test & Co", "We make <things>.")
    assert server_copy.words(home) == "<h1>Test &amp; Co</h1><p>We make &lt;things&gt;.</p>"
    assert home.data == (
        {
            "@context": "https://schema.org",
            "@type": "MusicGroup",
            "name": "Test & Co",
            "url": f"{SITE}/",
            "description": "We make <things>.",
            "logo": f"{SITE}/logo.png",
            "sameAs": ["https://social.test/us"],
        },
    )


def test_a_person_has_an_image_not_a_logo_and_an_empty_identity_says_little() -> None:
    person = server_copy.home(Identity(name="Ada", url=SITE, kind="Person", logo="/ada.png"))
    assert person.data[0]["image"] == f"{SITE}/ada.png"
    assert "logo" not in person.data[0]
    bare = server_copy.home(IDENT)
    assert server_copy.words(bare) == "<h1>Test Site</h1>"
    assert bare.data == (
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Test Site",
            "url": f"{SITE}/",
        },
    )


# --- sitemap.xml -------------------------------------------------------------------------


async def test_the_sitemap_lists_only_the_modules_on_and_never_noindex() -> None:
    when = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    blog = FakePages(
        entries=[
            Entry("/blog"),
            Entry("/blog/hello", modified=when),
            Entry("/blog/draft", noindex=True),
            Entry("/somewhere/else"),
            Entry("/account/me"),
        ]
    )
    shop = FakePages(entries=[Entry("/shop")])
    routes = server_copy.build(
        [
            public_module(
                "blog", public=["/blog", "/blog/:slug"], member=["/account/:tab"], pages=blog
            ),
            public_module("shop", public=["/shop"], pages=shop),
        ]
    )
    found = await server_copy.entries(None, routes, frozenset({"blog"}))  # type: ignore[arg-type]
    assert [(module, entry.path) for module, entry in found] == [
        ("kernel", "/"),
        ("blog", "/blog"),
        ("blog", "/blog/hello"),
    ]
    xml = server_copy.sitemap_xml(found, SITE)
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<urlset')
    assert f"<url><loc>{SITE}/</loc></url>" in xml
    assert (
        f"<url><loc>{SITE}/blog/hello</loc><lastmod>2026-11-01T12:00:00+00:00</lastmod></url>"
        in xml
    )
    assert "/shop" not in xml
    assert "draft" not in xml
    assert "account" not in xml


async def test_a_module_owning_home_lists_it_itself() -> None:
    site = FakePages(entries=[Entry("/", modified=date(2026, 11, 3))])
    routes = server_copy.build([public_module("site", public=["/"], pages=site)])
    found = await server_copy.entries(None, routes, frozenset({"site"}))  # type: ignore[arg-type]
    assert [(module, entry.path) for module, entry in found] == [("site", "/")]
    assert "<lastmod>2026-11-03</lastmod>" in server_copy.sitemap_xml(found, SITE)


async def test_a_module_with_no_sitemap_lists_nothing() -> None:
    class Bare(server_copy.Pages):
        async def page(self, db: Any, path: str, params: Any) -> None:
            return None

    routes = server_copy.build([public_module("bare", public=["/bare"], pages=Bare())])
    found = await server_copy.entries(None, routes, frozenset({"bare"}))  # type: ignore[arg-type]
    assert found == [("kernel", Entry("/"))]


def test_a_time_with_no_zone_is_taken_as_utc() -> None:
    xml = server_copy.sitemap_xml([("x", Entry("/a", modified=datetime(2026, 11, 1, 8, 0)))], SITE)
    assert "<lastmod>2026-11-01T08:00:00+00:00</lastmod>" in xml


def test_the_sitemap_escapes_and_encodes() -> None:
    xml = server_copy.sitemap_xml([("x", Entry("/x&y/café"))], SITE)
    assert f"<loc>{SITE}/x&amp;y/caf%C3%A9</loc>" in xml


def test_the_sitemap_stops_at_fifty_thousand(caplog: pytest.LogCaptureFixture) -> None:
    many = [("x", Entry(f"/p{number}")) for number in range(50_001)]
    with caplog.at_level(logging.WARNING, logger="kernel.server_copy"):
        xml = server_copy.sitemap_xml(many, SITE)
    assert xml.count("<url>") == 50_000
    assert "/p49999<" in xml
    assert "/p50000<" not in xml
    assert "50,001" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="kernel.server_copy"):
        server_copy.sitemap_xml(many[:50_000], SITE)
    assert caplog.text == ""


# --- robots.txt -----------------------------------------------------------------------------


def _robots(ai: str = "allow") -> str:
    routes = server_copy.build(
        [
            public_module(
                "account",
                public=["/people/:name"],
                member=["/account", "/account/:tab/edit"],
                pages=FakePages(),
            ),
            public_module("shop", public=["/shop"], member=["/orders"], pages=FakePages()),
        ]
    )
    ident = Identity(name="Test Site", url=SITE, ai_crawlers=ai)  # type: ignore[arg-type]
    return server_copy.robots_txt(routes, frozenset({"account"}), ident)


def _groups(text: str) -> list[tuple[list[str], list[str]]]:
    """robots.txt as (user agents, rules) groups."""
    groups: list[tuple[list[str], list[str]]] = []
    for block in text.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if line and not line.startswith("#")]
        agents = [line.split(": ", 1)[1] for line in lines if line.startswith("User-agent: ")]
        rules = [line for line in lines if not line.startswith("User-agent: ")]
        if agents:
            groups.append((agents, rules))
    return groups


def test_robots_lets_every_crawler_read_the_site_but_not_admin_api_or_members() -> None:
    text = _robots()
    everyone, ai = _groups(text)
    disallowed = [
        "Disallow: /admin",
        "Disallow: /api/",
        "Disallow: /account$",
        "Disallow: /account/*/edit$",
    ]
    assert everyone == (["*"], ["Allow: /", *disallowed])
    assert ai[0] == list(server_copy.AI_CRAWLERS)
    assert ai[1] == ["Allow: /", *disallowed]
    assert "/orders" not in text  # shop is off
    assert text.rstrip().endswith(f"Sitemap: {SITE}/sitemap.xml")


def test_the_ai_crawlers_are_each_named() -> None:
    assert set(server_copy.AI_CRAWLERS) == {
        "GPTBot",
        "ChatGPT-User",
        "OAI-SearchBot",
        "ClaudeBot",
        "Claude-User",
        "anthropic-ai",
        "PerplexityBot",
        "Google-Extended",
        "Applebot-Extended",
        "CCBot",
    }


def test_a_site_refusing_the_ai_crawlers_turns_them_all_away() -> None:
    everyone, ai = _groups(_robots("refuse"))
    assert everyone[1][0] == "Allow: /"
    assert ai == (list(server_copy.AI_CRAWLERS), ["Disallow: /"])


# --- llms.txt ------------------------------------------------------------------------------


def test_llms_txt_follows_its_format() -> None:
    routes = server_copy.build(
        [
            public_module("blog", public=["/blog/:slug"], pages=FakePages(), name="Blog"),
            public_module("shop", public=["/shop/:item"], pages=FakePages(), name="Shop"),
        ]
    )
    found = [
        ("kernel", Entry("/")),
        ("blog", Entry("/blog/a", title="First [post]", description="About\nthings")),
        ("blog", Entry("/blog/b")),
        ("blog", Entry("/blog/c (2)", title="Third")),
        ("shop", Entry("/shop/x")),
    ]
    ident = Identity(
        name="Test Site", url=SITE, description="We make things.", llms_summary="Long summary."
    )
    assert server_copy.llms_txt(found, routes, ident) == (
        "# Test Site\n\n"
        "> We make things.\n\n"
        "Long summary.\n\n"
        "## Blog\n\n"
        f"- [First \\[post\\]]({SITE}/blog/a): About things\n"
        f"- [Third]({SITE}/blog/c%20%282%29)\n"
    )


def test_llms_txt_says_only_what_it_has_and_stops_at_five_hundred_links() -> None:
    routes = server_copy.build([public_module("blog", public=["/blog/:slug"], pages=FakePages())])
    found = [("blog", Entry(f"/blog/{number}", title=f"Post {number}")) for number in range(501)]
    text = server_copy.llms_txt(found, routes, IDENT)
    assert text.startswith("# Test Site\n\n## Blog\n\n")
    assert text.count("\n- [") == 500
    assert "Post 499]" in text
    assert "Post 500]" not in text


# --- the site's identity -----------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"description": "x" * 301},
        {"description": "a" + chr(0) + "b"},
        {"kind": "Bakery"},
        {"logo": "javascript:alert(1)"},
        {"logo": "http://insecure.test/logo.png"},
        {"logo": "//evil.test/logo.png"},
        {"card_image": "card.png"},
        {"card_image": "/a\nb.png"},
        {"same_as": ["https://a.test"] * 21},
        {"same_as": ["ftp://a.test"]},
        {"same_as": ["/ours"]},
        {"llms_summary": "x" * 2001},
        {"llms_summary": chr(0)},
        {"ai_crawlers": "maybe"},
        {"unknown": True},
    ],
)
def test_the_identity_settings_refuse_bad_values(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SiteSettings.model_validate(values)


def test_the_identity_settings_take_good_values() -> None:
    taken = SiteSettings.model_validate(
        {
            "description": "x" * 300,
            "kind": "LocalBusiness",
            "logo": "https://cdn.test/logo.png",
            "card_image": "/card.png",
            "same_as": ["https://social.test/us", "http://old.test/us"],
            "llms_summary": "y" * 2000,
            "ai_crawlers": "refuse",
        }
    )
    assert taken.kind == "LocalBusiness"
    assert taken.ai_crawlers == "refuse"
    assert SiteSettings().ai_crawlers == "allow"


async def test_identity_reads_the_saved_section(app_factory: Any, db: AsyncSession) -> None:
    app_factory([], site_name="Saved Site")  # installs the name and registers the section
    form = await settings.form(db, server_copy.SECTION)
    await settings.save(
        db,
        server_copy.SECTION,
        {"description": "Saved.", "same_as": ["https://social.test/us"], "ai_crawlers": "refuse"},
        version=form["version"],
    )
    try:
        ident = await server_copy.identity(db)
        assert (ident.name, ident.url, ident.description) == ("Saved Site", SITE, "Saved.")
        assert (ident.same_as, ident.ai_crawlers) == (("https://social.test/us",), "refuse")
    finally:
        form = await settings.form(db, server_copy.SECTION)
        defaults = SiteSettings().model_dump(mode="json")
        await settings.save(db, server_copy.SECTION, defaults, version=form["version"])


def test_the_module_templates_pages_agree_with_its_module_json() -> None:
    folder = Path(__file__).resolve().parents[2] / "modules" / "_template"
    listed = Manifest.from_file(folder / "module.json")
    spec = importlib.util.spec_from_file_location(
        f"template_pages_{uuid.uuid4().hex[:8]}",
        folder / "backend" / "my_module" / "server_copy.py",
    )
    assert spec is not None
    assert spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    server_copy.build([InstalledModule(listed, pages=loaded.PAGES)])  # the start would take it
