"""kernel.shell: what each address answers, the built web app's files and
the paths that may never reach outside it, the cache headers, HEAD, the
minimal shell, the kernel's files over HTTP, and a 503 for a page whose rows
can't be read (decision 0041)."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

from kernel import server_copy, shell
from kernel.modules import ModuleRegistry
from kernel.server_copy import Entry, Moved, Page

from .conftest import AppFactory, Client, FakePages, public_module

SECRET = "the-secret-in-the-folder-above"

INDEX = (
    '<!doctype html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n'
    "    <!-- page-head -->\n    <title>Built</title>\n    <!-- /page-head -->\n"
    '    <script type="module" src="/assets/app-1a2b.js"></script>\n'
    "  </head>\n  <body>\n"
    '    <div id="root"><!-- page-body --><!-- /page-body --></div>\n'
    "  </body>\n</html>\n"
)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A built web app, with a secret beside it that must never be served."""
    (tmp_path / "secret.txt").write_text(SECRET, "utf-8")
    built = tmp_path / "dist"
    (built / "assets").mkdir(parents=True)
    (built / "index.html").write_text(INDEX, "utf-8")
    (built / "assets" / "app-1a2b.js").write_text("console.log(1)", "utf-8")
    (built / "assets" / "app-1a2b.css").write_text("p{}", "utf-8")
    (built / "notes.txt").write_text("notes", "utf-8")
    return built


HELLO = Page(
    "Hello",
    "The first post.",
    [server_copy.h1("Hello"), server_copy.p("Words & more.")],
    data=({"@context": "https://schema.org", "@type": "BlogPosting", "headline": "</script>"},),
    kind="article",
    published=datetime(2026, 11, 1, tzinfo=UTC),
)


def _blog(**kwargs: Any) -> FakePages:
    return FakePages(
        {
            "/blog": Page("Blog", "Every post.", server_copy.h1("Blog"), query=""),
            "/blog/hello": HELLO,
            "/blog/old": Moved("/blog/hello"),
            "/blog/temp": Moved("/blog/hello", permanent=False),
            "/blog/elsewhere": Moved("/shop?from=blog"),
        },
        entries=[Entry("/blog/hello", title="Hello", description="The first post.")],
        **kwargs,
    )


def _app(
    app_factory: AppFactory, dist: Path | None, pages: FakePages | None = None, **config: Any
) -> FastAPI:
    modules = [
        public_module(
            "blog",
            public=["/blog", "/blog/:slug"],
            member=["/account/:tab"],
            pages=pages or _blog(),
            name="Blog",
        ),
        public_module("shop", public=["/shop"], pages=FakePages({"/shop": HELLO})),
    ]
    values: dict[str, Any] = {"site_name": "Test Site", "modules": "blog", **config}
    if dist is not None:
        values["web_dist"] = str(dist)
    return app_factory(modules, **values)


def _between(text: str, start: str, end: str) -> str:
    found = re.search(re.escape(start) + "(.*?)" + re.escape(end), text, re.S)
    assert found is not None, (start, text)
    return found.group(1)


def _title(text: str) -> str:
    found = re.search(r"<title>(.*?)</title>", text)
    assert found is not None
    return found.group(1)


def _noindex(text: str) -> bool:
    return '<meta name="robots" content="noindex"' in text


# --- what each address answers ------------------------------------------------------------


async def test_a_modules_page_is_the_shell_with_its_head_words_and_json_ld(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        response = await client.get("/blog/hello")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    text = response.text
    head = _between(text, shell.HEAD_START, shell.HEAD_END)
    assert "<title>Hello</title>" in head
    assert "<title>Built</title>" not in text
    assert '<link rel="canonical" href="https://devkit.test/blog/hello" />' in head
    assert '<meta property="og:type" content="article" />' in head
    (ld,) = re.findall(r'<script type="application/ld\+json">(.*?)</script>', head)
    assert json.loads(ld)["headline"] == "</script>"
    body = _between(text, shell.BODY_START, shell.BODY_END)
    assert body == "<div data-server-copy><h1>Hello</h1><p>Words &amp; more.</p></div>"
    assert text.count("<h1") == 1
    assert '<script type="module" src="/assets/app-1a2b.js"></script>' in text
    assert not _noindex(text)


async def test_the_canonical_is_the_pages_never_the_requests_query(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        response = await client.get("/blog/hello?utm_source=x")
    assert '<link rel="canonical" href="https://devkit.test/blog/hello" />' in response.text


async def test_the_module_is_asked_with_the_patterns_parameters(
    app_factory: AppFactory, dist: Path
) -> None:
    pages = _blog()
    async with Client(_app(app_factory, dist, pages)) as client:
        await client.get("/blog/hello")
        await client.get("/blog")
    assert pages.asked == [("/blog/hello", {"slug": "hello"}), ("/blog", {})]


async def test_a_trailing_slash_is_a_301_without_it(app_factory: AppFactory, dist: Path) -> None:
    async with Client(_app(app_factory, dist)) as client:
        moved = await client.get("/blog/hello/?a=1&b=2")
        deep = await client.get("/blog/hello///")
        encoded = await client.get("/caf%C3%A9/")
        home = await client.get("/")
    assert (moved.status_code, moved.headers["location"]) == (301, "/blog/hello?a=1&b=2")
    assert (deep.status_code, deep.headers["location"]) == (301, "/blog/hello")
    assert (encoded.status_code, encoded.headers["location"]) == (301, "/caf%C3%A9")
    assert home.status_code == 200


@pytest.mark.parametrize(
    "address",
    [
        "https://devkit.test//evil.test/",
        "https://devkit.test//evil.test",
        "https://devkit.test/%5Cevil.test/",
        "https://devkit.test/%2F%2Fevil.test/",
        "https://devkit.test/a%0D%0ASet-Cookie:%20x=1/",
        "https://devkit.test/a%00b",
        "https://devkit.test/blog//hello",
    ],
)
async def test_an_address_that_could_leave_the_site_is_a_404(
    app_factory: AppFactory, dist: Path, address: str
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        response = await client.get(address)
    assert response.status_code == 404
    assert "location" not in response.headers
    assert "set-cookie" not in response.headers


async def test_a_moved_page_redirects_on_this_site(app_factory: AppFactory, dist: Path) -> None:
    async with Client(_app(app_factory, dist)) as client:
        old = await client.get("/blog/old")
        kept = await client.get("/blog/old?x=1")
        temp = await client.get("/blog/temp")
        own = await client.get("/blog/elsewhere?dropped=1")
    assert (old.status_code, old.headers["location"]) == (301, "/blog/hello")
    assert kept.headers["location"] == "/blog/hello?x=1"
    assert (temp.status_code, temp.headers["location"]) == (302, "/blog/hello")
    assert own.headers["location"] == "/shop?from=blog"


async def test_a_member_page_is_the_shell_with_noindex_and_no_words(
    app_factory: AppFactory, dist: Path
) -> None:
    pages = _blog()
    async with Client(_app(app_factory, dist, pages)) as client:
        response = await client.get("/account/settings")
    assert response.status_code == 200
    assert _title(response.text) == "Test Site"
    assert _noindex(response.text)
    assert _between(response.text, shell.BODY_START, shell.BODY_END) == ""
    assert pages.asked == []


@pytest.mark.parametrize("path", ["/admin", "/admin/users/1"])
async def test_the_admin_is_the_shell_with_noindex(
    app_factory: AppFactory, dist: Path, path: str
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        response = await client.get(path)
    assert response.status_code == 200
    assert _title(response.text) == "Admin · Test Site"
    assert _noindex(response.text)
    assert _between(response.text, shell.BODY_START, shell.BODY_END) == ""


async def test_a_real_file_is_served_and_assets_are_immutable(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        script = await client.get("/assets/app-1a2b.js")
        style = await client.get("/assets/app-1a2b.css")
        notes = await client.get("/notes.txt")
        missing = await client.get("/assets/app-old.js")
        index = await client.get("/index.html")
    assert (script.status_code, script.text) == (200, "console.log(1)")
    assert script.headers["content-type"].startswith("text/javascript")
    assert (
        script.headers["cache-control"] == shell.IMMUTABLE == "public, max-age=31536000, immutable"
    )
    assert style.headers["content-type"].startswith("text/css")
    assert (notes.status_code, notes.text) == (200, "notes")
    assert "immutable" not in notes.headers.get("cache-control", "")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-cache"
    assert index.status_code == 404  # the shell is an answer, never a file


async def test_an_api_miss_is_a_problem_never_the_shell(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        answers = [
            await client.get("/api/nope"),
            await client.post("/api/nope", json={}),
            await client.get("/api"),
            await client.get("/api/blog/nope"),
        ]
        wrong_method = await client.post("/api/kernel/health")
    for response in answers:
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == "kernel.not_found"
    assert wrong_method.status_code == 405


async def test_an_address_the_site_doesnt_have_is_a_404_shell(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        nowhere = await client.get("/nowhere")
        none = await client.get("/blog/gone")
        off = await client.get("/shop")
        api_like = await client.get("/apis")
    for response in (nowhere, none, off, api_like):
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-cache"
        assert _title(response.text) == "Page not found · Test Site"
        assert _noindex(response.text)
        assert '<script type="module" src="/assets/app-1a2b.js">' in response.text


@pytest.mark.parametrize(
    "error", [OperationalError("SELECT", {}, Exception("down")), OSError("down")]
)
async def test_a_page_whose_rows_cant_be_read_is_a_503(
    app_factory: AppFactory, dist: Path, error: Exception
) -> None:
    async with Client(_app(app_factory, dist, _blog(error=error))) as client:
        response = await client.get("/blog/hello")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "60"
    assert response.headers["cache-control"] == "no-cache"
    assert _noindex(response.text)


# --- the paths that may never reach outside the folder --------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/%2e%2e/secret.txt",
        "/assets/%2e%2e/%2e%2e/secret.txt",
        "/assets%2f..%2f..%2fsecret.txt",
        "/..%5csecret.txt",
        "/assets/..%5c..%5csecret.txt",
    ],
)
async def test_no_address_reaches_outside_the_folder(
    app_factory: AppFactory, dist: Path, path: str
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        response = await client.get("https://devkit.test" + path)
    assert SECRET not in response.text
    assert response.status_code in (301, 404)


def test_app_file_refuses_anything_outside_the_folder(dist: Path) -> None:
    secret = dist.parent / "secret.txt"
    assert shell.app_file(dist, "assets/app-1a2b.js") == (dist / "assets" / "app-1a2b.js").resolve()
    for path in (
        "../secret.txt",
        "assets/../../secret.txt",
        "..\\secret.txt",
        str(secret),
        str(secret).replace("\\", "/"),
        "/" + str(secret),
        "assets",
        "",
        "index.html",
        "assets/x" + chr(0) + ".js",
        "nothing.js",
    ):
        assert shell.app_file(dist, path) is None, path


def test_app_file_refuses_a_link_out_of_the_folder(dist: Path) -> None:
    link = dist / "linked.txt"
    try:
        os.symlink(dist.parent / "secret.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("This system can't make a symlink here.")
    assert shell.app_file(dist, "linked.txt") is None


# --- HEAD ------------------------------------------------------------------------------------


async def test_head_is_answered_as_get_without_the_body(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        for path, status in (
            ("/blog/hello", 200),
            ("/nowhere", 404),
            ("/assets/app-1a2b.js", 200),
            ("/sitemap.xml", 200),
            ("/blog/old", 301),
        ):
            got = await client.get(path)
            head = await client.head(path)
            assert (head.status_code, got.status_code) == (status, status), path
            assert head.content == b"", path
            for name in ("content-type", "content-length", "cache-control", "location"):
                assert head.headers.get(name) == got.headers.get(name), (path, name)
        api = await client.head("/api/kernel/health")
    assert api.status_code == 405  # the API's routes answer HEAD for themselves


# --- the minimal shell and refusals at start -----------------------------------------------


async def test_without_a_build_the_kernels_minimal_shell_is_used(app_factory: AppFactory) -> None:
    async with Client(_app(app_factory, None)) as client:
        home = await client.get("/")
        page = await client.get("/blog/hello")
        file = await client.get("/assets/app-1a2b.js")
    assert home.status_code == 200
    assert "<h1>Test Site</h1>" in _between(home.text, shell.BODY_START, shell.BODY_END)
    for response in (home, page):
        assert re.findall(r"<script(?! type=\"application/ld\+json\")", response.text) == []
        assert shell.HEAD_START in response.text
        assert shell.BODY_START in response.text
    assert '<div id="root">' in shell.MINIMAL
    assert file.status_code == 404


def test_a_build_without_the_markers_is_refused(app_factory: AppFactory, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><head></head><body></body></html>", "utf-8")
    with pytest.raises(RuntimeError, match=r"Refusing to start: .*page-head"):
        _app(app_factory, tmp_path)
    (tmp_path / "index.html").write_text(
        f"<html><head>{shell.HEAD_START}{shell.HEAD_END}</head><body></body></html>", "utf-8"
    )
    with pytest.raises(RuntimeError, match=r"Refusing to start: .*page-body"):
        _app(app_factory, tmp_path)


def test_a_missing_build_is_refused(app_factory: AppFactory, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Refusing to start: WEB_DIST"):
        _app(app_factory, tmp_path / "nowhere")
    with pytest.raises(RuntimeError, match=r"Refusing to start: WEB_DIST .*index\.html"):
        _app(app_factory, tmp_path)


def test_the_catch_all_writes_its_own_addresses(app_factory: AppFactory, dist: Path) -> None:
    app = _app(app_factory, dist)
    assert app.url_path_for("answer", full_path="blog/hello") == "/blog/hello"


def test_the_shell_puts_head_and_words_between_the_markers() -> None:
    built = shell.Shell(shell.MINIMAL)
    text = built.render("<title>T</title>", "<p>w</p>")
    assert "<title>T</title>" in _between(text, shell.HEAD_START, shell.HEAD_END)
    assert (
        _between(text, shell.BODY_START, shell.BODY_END) == "<div data-server-copy><p>w</p></div>"
    )
    assert _between(built.render("<title>T</title>", ""), shell.BODY_START, shell.BODY_END) == ""


# --- the home page and the kernel's files over HTTP -----------------------------------------


async def test_the_default_home_page_answers_until_a_module_owns_it(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist)) as client:
        default = await client.get("/")
    assert default.status_code == 200
    assert _title(default.text) == "Test Site"
    assert '"@type": "Organization"' in default.text
    owned = app_factory(
        [public_module("site", public=["/"], pages=FakePages({"/": HELLO}))],
        site_name="Test Site",
        web_dist=str(dist),
    )
    async with Client(owned) as client:
        home = await client.get("/")
    assert _title(home.text) == "Hello"


async def test_the_kernel_files_are_served(app_factory: AppFactory, dist: Path) -> None:
    async with Client(_app(app_factory, dist)) as client:
        sitemap = await client.get("/sitemap.xml")
        robots = await client.get("/robots.txt")
        llms = await client.get("/llms.txt")
    assert sitemap.headers["content-type"] == "application/xml"
    assert "<loc>https://devkit.test/blog/hello</loc>" in sitemap.text
    assert "<loc>https://devkit.test/</loc>" in sitemap.text
    assert robots.headers["content-type"] == "text/plain; charset=utf-8"
    assert "Disallow: /account/*$" in robots.text
    assert "Sitemap: https://devkit.test/sitemap.xml" in robots.text
    assert llms.headers["content-type"] == "text/plain; charset=utf-8"
    assert "## Blog\n\n- [Hello](https://devkit.test/blog/hello): The first post.\n" in llms.text
    for response in (sitemap, robots, llms):
        assert response.status_code == 200
        assert "x-robots-tag" not in response.headers


async def test_robots_noindex_keeps_its_header_everywhere(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist, robots_noindex=True)) as client:
        for path in ("/robots.txt", "/sitemap.xml", "/blog/hello", "/nowhere"):
            response = await client.get(path)
            assert response.headers["x-robots-tag"] == "noindex", path


async def test_a_kernel_file_whose_rows_cant_be_read_is_a_503(
    app_factory: AppFactory, dist: Path
) -> None:
    async with Client(_app(app_factory, dist, _blog(error=OSError("down")))) as client:
        sitemap = await client.get("/sitemap.xml")
        llms = await client.get("/llms.txt")
    for response in (sitemap, llms):
        assert (response.status_code, response.headers["retry-after"]) == (503, "60")


async def test_an_unread_identity(
    app_factory: AppFactory, dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A module's page still answers, with the name; the default home page,
    robots.txt and llms.txt, which are the identity, answer 503."""

    async def unread(db: Any) -> server_copy.Identity:
        raise OperationalError("SELECT", {}, Exception("down"))

    monkeypatch.setattr(server_copy, "identity", unread)
    async with Client(_app(app_factory, dist), drain=False) as client:
        page = await client.get("/blog/hello")
        home = await client.get("/")
        robots = await client.get("/robots.txt")
        llms = await client.get("/llms.txt")
    assert page.status_code == 200
    assert '<meta property="og:site_name" content="Test Site" />' in page.text
    for response in (home, robots, llms):
        assert (response.status_code, response.headers["retry-after"]) == (503, "60")


async def test_an_unread_module_switch_keeps_the_last_set(
    app_factory: AppFactory, dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(app_factory, dist)
    async with Client(app, drain=False) as client:

        async def unread(self: ModuleRegistry, db: Any, *, fresh: bool = False) -> frozenset[str]:
            raise OperationalError("SELECT", {}, Exception("down"))

        monkeypatch.setattr(ModuleRegistry, "on", unread)
        page = await client.get("/blog/hello")
        shop = await client.get("/shop")
        robots = await client.get("/robots.txt")
    assert page.status_code == 200
    assert shop.status_code == 404
    assert robots.status_code == 200


async def test_head_as_get_on_its_own() -> None:
    """The middleware alone: HEAD becomes GET, its body dropped, and the
    route the GET took is the HEAD's too, for the access log."""
    seen: list[str] = []
    outer: list[dict[str, Any]] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["method"])
        if scope["path"] == "/page":
            scope["route"] = "a route"
        await send(
            {"type": "http.response.start", "status": 200, "headers": [(b"content-length", b"2")]}
        )
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = shell.HeadAsGet(inner)

    async def app(scope: Any, receive: Any, send: Any) -> None:
        outer.append(scope)
        await middleware(scope, receive, send)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://devkit.test") as client:
        head = await client.head("/page")
        other = await client.head("/other")
        api = await client.head("/api/x")
    assert (head.content, head.headers["content-length"]) == (b"", "2")
    assert (other.status_code, api.status_code) == (200, 200)
    assert seen == ["GET", "GET", "HEAD"]
    assert [scope.get("route") for scope in outer] == ["a route", None, None]


async def test_head_drops_the_body_from_the_messages_themselves() -> None:
    """Seen in the ASGI messages: httpx drops a HEAD answer's body on its own,
    so a test through it can't tell whether the middleware did."""

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": True})
        await send({"type": "http.response.body", "body": b"!"})

    sent: list[dict[str, Any]] = []

    async def send(message: Any) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "HEAD", "path": "/page", "headers": []}
    await shell.HeadAsGet(inner)(scope, receive, send)
    bodies = [message for message in sent if message["type"] == "http.response.body"]
    assert [(message["body"], message.get("more_body")) for message in bodies] == [
        (b"", True),
        (b"", None),
    ]
