"""The built web app, served from the site's own origin, and what every
address outside the API answers (SPEC.md section 9, decision 0041).

Ported from VybeSite's `spa.py`: the behavior, not the code.

**WEB_DIST** is the built web app's folder. Its `index.html` is the shell:
read once at start, and refused at start without the `page-head` and
`page-body` markers (`<!-- page-head -->...<!-- /page-head -->` in its head,
`<!-- page-body --><!-- /page-body -->` inside the app's root). Unset, the
kernel's own minimal shell is used: no scripts, the same markers.

**What an address answers**, in this order (`answer`):

1. An address that could leave the site (`//host`, a backslash, a control
   character): 404.
2. A real file in WEB_DIST: the file. `/assets/*` is sent
   `public, max-age=31536000, immutable` (a build names new files). **Only a
   file inside the folder is ever served:** the path is resolved first, so
   `..`, an encoded `..` or `/`, an absolute path or a symlink can't reach
   outside it, and `index.html` is only ever an answer, never a file.
3. A trailing slash (not `/`): 301 without it, the query kept.
4. `/admin` and below: the shell, noindex, "Admin · {name}". The app decides
   who sees what there.
5. A module's page (`kernel.server_copy`): its head, words and JSON-LD; a
   `Moved` is a 301 or 302; None, or the module off, is a 404. A member
   page is the shell, noindex, titled by the site's name, with no words.
   `/` with no module on owning it is the kernel's home page.
6. Anything else: 404, the shell, noindex, "Page not found · {name}", so the
   app renders its own 404 page.

A page whose rows can't be read answers **503 with Retry-After** ("try
later"), never a 404 for a page that may exist. The shell is sent
`Cache-Control: no-cache`, so a browser checks for a new build each visit.

**`/api/...` that no route answers** never reaches here: the catch-all
doesn't match it, so it stays a 404 `kernel.not_found` as problem JSON, and a
route asked with the wrong method stays a 405.

**HEAD** is answered as GET, without the body (`HeadAsGet`), outside the
API, whose routes say for themselves whether they answer it: FastAPI routes
take only the methods they name.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.convertors import Convertor, register_url_convertor
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kernel import server_copy
from kernel.access import public
from kernel.db import get_db
from kernel.modules import ModuleRegistry

log = logging.getLogger(__name__)

#: The comments the head tags and the page's words go between.
HEAD_START = "<!-- page-head -->"
HEAD_END = "<!-- /page-head -->"
BODY_START = "<!-- page-body -->"
BODY_END = "<!-- /page-body -->"

#: For the build's hashed files. A new build names new files, so a file under
#: /assets never changes and a browser may keep it a year without asking.
IMMUTABLE = "public, max-age=31536000, immutable"
#: How long a 503 asks a crawler to wait, in seconds.
RETRY_AFTER = "60"

#: The shell while WEB_DIST is unset: no scripts, the same markers.
MINIMAL = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    {HEAD_START}
    {HEAD_END}
  </head>
  <body>
    <div id="root">{BODY_START}{BODY_END}</div>
  </body>
</html>
"""

#: Types sent for the build's files, whatever the system's own table says
#: (Windows' can call JavaScript text/plain, which nosniff then refuses).
_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
}


class Shell:
    """The app's shell, with its markers checked."""

    def __init__(self, text: str, root: Path | None = None) -> None:
        for start, end in ((HEAD_START, HEAD_END), (BODY_START, BODY_END)):
            first = text.find(start)
            if first < 0 or text.find(end, first + len(start)) < 0:
                raise ValueError(f"WEB_DIST's index.html has no {start} ... {end} markers.")
        self.text = text
        #: The built app's folder, resolved; None for the minimal shell.
        self.root = root

    @classmethod
    def load(cls, web_dist: str) -> Shell:
        """WEB_DIST's index.html, or the minimal shell when it's unset.
        Raises ValueError for a folder that isn't one, or a shell without
        its markers."""
        if not web_dist.strip():
            return cls(MINIMAL)
        root = Path(web_dist.strip()).resolve()
        if not root.is_dir():
            raise ValueError(f"WEB_DIST ({web_dist}) isn't a folder.")
        index = root / "index.html"
        if not index.is_file():
            raise ValueError(f"WEB_DIST ({web_dist}) has no index.html.")
        return cls(index.read_text("utf-8"), root)

    def render(self, head: str, words: str) -> str:
        """The shell with `head` between its head markers and `words`, in a
        `<div data-server-copy>`, between its body markers."""
        text = _between(self.text, HEAD_START, HEAD_END, f"\n    {head}\n    ")
        return _between(
            text, BODY_START, BODY_END, f"<div data-server-copy>{words}</div>" if words else ""
        )


def _between(text: str, start: str, end: str, inside: str) -> str:
    first = text.index(start) + len(start)
    return text[:first] + inside + text[text.index(end, first) :]


def app_file(root: Path, full_path: str) -> Path | None:
    """The file `full_path` names inside the built app, or None: never
    anything outside it, a folder, or the shell itself."""
    if not full_path:
        return None
    try:
        base = root.resolve()
        found = (base / full_path).resolve()
        if (
            found.is_relative_to(base)
            and found.is_file()
            and str(found).casefold() != str(base / "index.html").casefold()
        ):
            return found
    except (OSError, ValueError):  # a NUL, or a name the system can't take
        pass
    return None


class HeadAsGet:
    """Routes a HEAD request outside the API as a GET and drops the body from
    the answer, so a page, a file or a kernel file answers HEAD with exactly
    the headers GET gets."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "HEAD" or _is_api(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def headers_only(message: Message) -> None:
            if message["type"] == "http.response.body":
                message = {**message, "body": b""}
            await send(message)

        inner = {**scope, "method": "GET"}
        await self.app(inner, receive, headers_only)
        if "route" in inner:  # so the access log names the route a HEAD took
            scope["route"] = inner["route"]


def _is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class _Page(Convertor[str]):
    """Any path but /api and below, which stay the API's 404 and 405."""

    regex = "(?!api(?:/|$)).*"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("mechframe_page", _Page())


# --- the answers --------------------------------------------------------------------------------


def _html(text: str, status: int, headers: dict[str, str] | None = None) -> HTMLResponse:
    return HTMLResponse(
        text, status_code=status, headers={"Cache-Control": "no-cache", **(headers or {})}
    )


def _plain(
    built: Shell, title: str, status: int, headers: dict[str, str] | None = None
) -> HTMLResponse:
    site = server_copy.named()
    return _html(built.render(server_copy.plain_head(title, site), ""), status, headers)


def _unavailable(built: Shell) -> HTMLResponse:
    return _plain(built, server_copy.named().name, 503, {"Retry-After": RETRY_AFTER})


def _busy() -> Response:
    """A kernel file whose rows can't be read: "try later"."""
    return PlainTextResponse(
        "", status_code=503, headers={"Retry-After": RETRY_AFTER, "Cache-Control": "no-cache"}
    )


def _page(
    built: Shell, page: server_copy.Page, path: str, site: server_copy.Identity
) -> HTMLResponse:
    return _html(built.render(server_copy.head(page, path, site), server_copy.words(page)), 200)


def _file(found: Path, full_path: str) -> FileResponse:
    headers = {"Cache-Control": IMMUTABLE} if full_path.startswith("assets/") else None
    return FileResponse(found, media_type=_TYPES.get(found.suffix.lower()), headers=headers)


def _leaves(path: str) -> bool:
    """Whether a path could name another host or break a header: `//`, a
    backslash or a control character."""
    trimmed = path.rstrip("/") or "/"
    return "//" in trimmed or "\\" in path or any(ord(c) < 32 or ord(c) == 127 for c in path)


async def _on(request: Request, db: AsyncSession) -> frozenset[str]:
    """The modules on; unread, the last set this process read."""
    registry: ModuleRegistry = request.app.state.modules
    try:
        return await registry.on(db)
    except (SQLAlchemyError, OSError) as error:
        log.warning(
            "Couldn't read which modules are switched off (%s); answering with the last set read.",
            type(error).__name__,
        )
        # A failed statement leaves PostgreSQL's transaction aborted, and the page's own
        # read comes next on this session. Nothing else has been read on it yet, so
        # rolling back loses nothing (CodeRabbit on #73).
        try:
            await db.rollback()
        except (SQLAlchemyError, OSError):
            log.warning("Couldn't roll back after the failed read; the page read may fail too.")
        return registry.on_cached()


async def _identity(db: AsyncSession) -> server_copy.Identity:
    """The site's identity; unread, its name and address alone, so a page
    whose own rows were read still answers."""
    try:
        return await server_copy.identity(db)
    except (SQLAlchemyError, OSError) as error:
        log.warning("Couldn't read the site's identity (%s).", type(error).__name__)
        return server_copy.named()


async def answer(request: Request, full_path: str, db: AsyncSession = Depends(get_db)) -> Response:
    """What an address outside the API answers (the module docstring's list)."""
    built: Shell = request.app.state.shell
    routes: server_copy.Routes = request.app.state.public_routes
    path = "/" + full_path
    query = request.url.query
    name = server_copy.named().name
    if _leaves(path):
        return _plain(built, f"Page not found · {name}", 404)
    if built.root is not None and (found := app_file(built.root, full_path)) is not None:
        return _file(found, full_path)
    if path != "/" and path.endswith("/"):
        target = quote(path.rstrip("/"))
        return RedirectResponse(f"{target}?{query}" if query else target, status_code=301)
    if path == "/admin" or path.startswith("/admin/"):
        return _plain(built, f"Admin · {name}", 200)
    on = await _on(request, db)
    match = routes.resolve(path, on)  # among the modules on: one that's off steps aside
    if match is None:
        if path == "/":
            return await _home(built, db)
        return _plain(built, f"Page not found · {name}", 404)
    if match.member:
        return _plain(built, name, 200)
    try:
        found_page = await routes.pages_of(match.module).page(db, path, match.params)
    except (SQLAlchemyError, OSError):
        log.exception("Couldn't read the page at %s.", path)
        return _unavailable(built)
    if found_page is None:
        return _plain(built, f"Page not found · {name}", 404)
    if isinstance(found_page, server_copy.Moved):
        location = found_page.path
        # The request's query goes before any fragment, and only where the
        # path itself has none: a ? inside the fragment isn't a query (Codex on #73).
        before, hash_mark, fragment = location.partition("#")
        if query and "?" not in before:
            location = f"{before}?{query}{hash_mark}{fragment}"
        return RedirectResponse(location, status_code=301 if found_page.permanent else 302)
    return _page(built, found_page, path, await _identity(db))


async def _home(built: Shell, db: AsyncSession) -> Response:
    """The kernel's home page, which is the site's identity: unread, 503."""
    try:
        site = await server_copy.identity(db)
    except (SQLAlchemyError, OSError):
        log.exception("Couldn't read the site's identity for the home page.")
        return _unavailable(built)
    return _page(built, server_copy.home(site), "/", site)


# --- the kernel's files -------------------------------------------------------------------------


async def sitemap(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    routes: server_copy.Routes = request.app.state.public_routes
    on = await _on(request, db)
    try:
        found = await server_copy.entries(db, routes, on)
    except (SQLAlchemyError, OSError):
        log.exception("Couldn't read the pages for sitemap.xml.")
        return _busy()
    return Response(
        server_copy.sitemap_xml(found, server_copy.named().url), media_type="application/xml"
    )


async def robots(db: AsyncSession = Depends(get_db)) -> Response:
    try:
        site = await server_copy.identity(db)
    except (SQLAlchemyError, OSError):
        # Unread, the site may be refusing the AI crawlers: a 5xx robots.txt
        # keeps every crawler out until it reads again.
        log.exception("Couldn't read the site's identity for robots.txt.")
        return _busy()
    return PlainTextResponse(server_copy.robots_txt(site))


async def llms(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    routes: server_copy.Routes = request.app.state.public_routes
    on = await _on(request, db)
    try:
        site = await server_copy.identity(db)
        found = await server_copy.entries(db, routes, on)
    except (SQLAlchemyError, OSError):
        log.exception("Couldn't read the pages for llms.txt.")
        return _busy()
    return PlainTextResponse(server_copy.llms_txt(found, routes, site))


def install(app: FastAPI, routes: server_copy.Routes, built: Shell) -> None:
    """The kernel's files and the catch-all, which `create_app` registers
    after every other route, so each of those still takes precedence."""
    app.state.public_routes = routes
    app.state.shell = built
    router = APIRouter()
    marks = [Depends(public)]
    router.add_api_route(
        "/sitemap.xml", sitemap, methods=["GET"], dependencies=marks, include_in_schema=False
    )
    router.add_api_route(
        "/robots.txt", robots, methods=["GET"], dependencies=marks, include_in_schema=False
    )
    router.add_api_route(
        "/llms.txt", llms, methods=["GET"], dependencies=marks, include_in_schema=False
    )
    router.add_api_route(
        "/{full_path:mechframe_page}",
        answer,
        methods=["GET"],
        dependencies=marks,
        include_in_schema=False,
    )
    app.include_router(router)
