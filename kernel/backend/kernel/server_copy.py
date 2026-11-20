"""Public pages that crawlers can read (SPEC.md section 9, decision 0041).

AI crawlers (GPTBot, ClaudeBot, PerplexityBot) and link previews fetch a page
and run none of its scripts, so a single-page app's shell tells them nothing.
Python can't render React, so the server writes each public page's head
tags, its words as plain HTML and its JSON-LD into the app's shell
(`kernel.shell` serves it). React's first render replaces the words.
Ported from VybeSite's `site_routes.py`, `site_html.py` and
`routers/sitemap.py`: the behavior, not the code.

**A module with public pages** lists their patterns in module.json's
`routes.public` (`/blog`, `/blog/:slug`) and gives
`InstalledModule(pages=...)` a `Pages` from its `server_copy.py` (`PAGES`).
The start refuses a module with one and not the other.

    class BlogPages(server_copy.Pages):
        async def page(self, db, path, params):
            post = await service.published(db, params["slug"])  # the API's own read
            if post is None:
                return None                                       # a real 404
            return server_copy.Page(
                post.title, post.excerpt,
                server_copy.article(server_copy.h1(post.title), server_copy.cleaned(post.html)),
                data=({"@context": "https://schema.org", "@type": "BlogPosting", ...},),
                kind="article", published=post.published_at,
            )

        async def sitemap(self, db):
            return [server_copy.Entry(f"/blog/{p.slug}", modified=p.updated_at, title=p.title)
                    for p in await service.all_published(db)]

**Which module answers an address:** its pattern with the most fixed
segments; the start refuses two patterns that would answer the same address
at the same rank, in one module or two, member pages included. `/` is the
kernel's default home page (the site's name, description and Organization
JSON-LD) until a module on declares it. The kernel's own pages
(`KERNEL_PAGES`: sign-in, the email landings, the account's, the admin's)
always answer as the kernel's, and the start refuses a pattern that takes
one under its first segment (`/account/:tab`); `/:slug` may, and never gets them.

**The site's own pages** (`create_app(site=SitePages(...))`, decision 0048)
are checked as a module's and answer the same way, under the owner `SITE`.
They're always on, whatever the modules' switches, and at the same rank the
site's pattern takes an address from a module's (the start logs which); a
module's more fixed pattern still wins.

**The words** come from the builders (`h1`, `h2`, `h3`, `p`, `ul`, `link`,
`time`, `section`, `article`), which escape every value: anything that isn't
their `Html` is text. `cleaned` passes HTML made elsewhere, such as a post's
Markdown, through nh3 with no `h1` (the page has its own). Whatever the
words hold, the finished words are cleaned again against a tight allowlist:
no `style`, no `script`, no event attributes, no `javascript:` link.

**The head** carries the title, description, an absolute canonical (the
page's own `query`, never the request's), Open Graph and Twitter tags with an
absolute `og:image` (the page's, else the site's card), and each JSON-LD
object in a `<script type="application/ld+json">` with `<`, `>` and `&` as
JSON escapes, so no value can close the tag. The CSP is unchanged: a data
block never runs.

**The kernel's files**, generated per request from the modules on:
`sitemap.xml` (at most 50,000 addresses), `robots.txt` (every crawler
welcome but in the admin and the API; the AI crawlers in a
group of their own, turned away while the site refuses them) and `llms.txt`
(llmstxt.org; at most 500 links).

**The site's identity** is the settings section `kernel.site`
(`SiteSettings`): its description, kind, logo, social card, profiles, the
summary for `llms.txt` and the AI crawlers' switch. The name is SITE_NAME.
`identity(db)` reads it all for a module's page.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import nh3
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.settings import settings

if TYPE_CHECKING:  # kernel.modules names Pages for InstalledModule
    from kernel.modules import InstalledModule

log = logging.getLogger(__name__)

#: The settings section that holds the site's identity.
SECTION = "kernel.site"
#: The kernel's own entries in the sitemap (its default home page).
KERNEL = "kernel"
#: The owner of the site's own pages (`create_app(site=...)`, decision 0048):
#: always on, and an id no module may take (`kernel.modules.RESERVED_IDS`).
SITE = "site"
#: The most addresses sitemap.xml lists (sitemaps.org), and links llms.txt.
MAX_SITEMAP = 50_000
MAX_LLMS_LINKS = 500

#: The AI crawlers robots.txt names in a group of their own.
AI_CRAWLERS = (
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
)

#: The kernel's own addresses, which no module's pattern may take.
KERNEL_FILES = frozenset({"/sitemap.xml", "/robots.txt", "/llms.txt"})
_RESERVED = frozenset({"api", "admin"})


@dataclass(frozen=True)
class KernelPage:
    """One of the kernel's own pages: its address, its title and who sees it."""

    path: str
    title: str
    access: Literal["public", "member", "admin"]


#: The kernel's own pages (K4 contract §2), kept equal to `kernel/kernel.json`'s
#: `pages` by a test: a site never receives the manifest (change 8). Each is the
#: shell, `noindex`, titled "{title} · {name}"; the web app's router keeps the
#: same list (`kernel/web/src/app/pages.ts`).
KERNEL_PAGES: tuple[KernelPage, ...] = (
    KernelPage("/sign-in", "Sign in", "public"),
    KernelPage("/sign-up", "Sign up", "public"),
    KernelPage("/forgot-password", "Forgot password", "public"),
    KernelPage("/auth/verify", "Verify your email", "public"),
    KernelPage("/auth/link", "Sign in with a link", "public"),
    KernelPage("/auth/reset", "Choose a new password", "public"),
    KernelPage("/auth/email", "Confirm your new email", "public"),
    KernelPage("/auth/email/undo", "Undo the email change", "public"),
    KernelPage("/auth/second-factor/undo", "Remove the new sign-in step", "public"),
    KernelPage("/notifications/unsubscribe", "Unsubscribe", "public"),
    KernelPage("/account", "Your account", "member"),
    KernelPage("/account/notifications", "Notifications", "member"),
    KernelPage("/account/activity", "Your activity", "member"),
    KernelPage("/admin", "Dashboard", "admin"),
    KernelPage("/admin/people", "People", "admin"),
    KernelPage("/admin/roles", "Roles", "admin"),
    KernelPage("/admin/activity", "Activity", "admin"),
    KernelPage("/admin/settings", "Settings", "admin"),
    KernelPage("/admin/settings/features", "Features", "admin"),
    KernelPage("/admin/settings/system", "System", "admin"),
)

#: Each kernel page's title, by its address.
KERNEL_PAGE_TITLES = {page.path: page.title for page in KERNEL_PAGES}

_CONTROL = re.compile("[" + chr(0) + "-" + chr(31) + chr(127) + "]")


def _has_control(text: str) -> bool:
    return _CONTROL.search(text) is not None


# --- the words --------------------------------------------------------------------------


class Html(str):
    """HTML the builders made, every value in it escaped. Anything else that
    joins a page's words is text, and is escaped there."""

    __slots__ = ()


def _join(children: Iterable[Any]) -> str:
    out = []
    for child in children:
        if child is None:
            continue
        if isinstance(child, Html):
            out.append(str(child))
        elif isinstance(child, str):
            out.append(html.escape(child))
        elif isinstance(child, Iterable):
            out.append(_join(child))
        else:
            out.append(html.escape(str(child)))
    return "".join(out)


def _element(tag: str, children: Iterable[Any]) -> Html:
    return Html(f"<{tag}>{_join(children)}</{tag}>")


def h1(*children: Any) -> Html:
    """The page's one heading."""
    return _element("h1", children)


def h2(*children: Any) -> Html:
    return _element("h2", children)


def h3(*children: Any) -> Html:
    return _element("h3", children)


def p(*children: Any) -> Html:
    return _element("p", children)


def section(*children: Any) -> Html:
    return _element("section", children)


def article(*children: Any) -> Html:
    return _element("article", children)


def ul(*items: Any) -> Html:
    """A list, an `li` for each item that isn't None."""
    return Html(
        "<ul>"
        + "".join(f"<li>{_join([item])}</li>" for item in items if item is not None)
        + "</ul>"
    )


#: Where a link may go: a page of this site (never `//host` or `/\host`), a
#: fragment, an http or https address, an email address or a phone number.
_HREF = re.compile(r"(?:/(?![/\\])|#|https?://[^/\\]|mailto:|tel:)", re.IGNORECASE)


def link(text: Any, href: str) -> Html:
    """A link, or only its words when `href` could go anywhere unsafe."""
    if not _HREF.match(href) or _has_control(href) or href != href.strip():
        return Html(_join([text]))
    return Html(f'<a href="{html.escape(href)}">{_join([text])}</a>')


def time(when: date | datetime, text: Any = None) -> Html:
    """A date or a moment, read by machines from `datetime`; its words are
    `text`, or the date itself."""
    stamp = when.isoformat()
    return Html(
        f'<time datetime="{html.escape(stamp)}">{_join([stamp if text is None else text])}</time>'
    )


_SCHEMES = {"http", "https", "mailto", "tel"}
_ATTRIBUTES = {"a": {"href"}, "img": {"src", "alt", "width", "height"}, "time": {"datetime"}}
#: What `cleaned` keeps of HTML made elsewhere: no h1, the page has its own.
_POST_TAGS = {
    "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li", "a", "em", "strong",
    "b", "i", "code", "pre", "blockquote", "img", "figure", "figcaption", "table", "thead",
    "tbody", "tr", "th", "td", "time", "section", "article",
}  # fmt: skip
_POSTS = nh3.Cleaner(tags=_POST_TAGS, attributes=_ATTRIBUTES, url_schemes=_SCHEMES, link_rel=None)
#: What the finished words may hold: the same, with the page's h1.
_WORDS = nh3.Cleaner(
    tags=_POST_TAGS | {"h1"}, attributes=_ATTRIBUTES, url_schemes=_SCHEMES, link_rel=None
)


def cleaned(markup: str) -> Html:
    """HTML made elsewhere (a post's Markdown, rendered) cleaned to an
    allowlist: headings from h2, paragraphs, lists, links, emphasis, code,
    quotes, images and tables, with no style, script, event attribute or
    unsafe link."""
    return Html(_POSTS.clean(markup))


# --- what a module answers -----------------------------------------------------------------


def _site_path(path: str) -> bool:
    """A path on this site: one leading slash, never `//host` or a backslash,
    no control characters or spaces at either end."""
    return (
        path.startswith("/")
        and not path.startswith("//")
        and "\\" not in path
        and not _has_control(path)
        and path == path.strip()
    )


#: An absolute http(s) address: a host (and port), then anything but spaces
#: and backslashes.
_ABSOLUTE = re.compile(r"(https?)://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:[/?#][^\s\\]*)?")


def _absolute(url: str, *, https_only: bool = False) -> bool:
    found = _ABSOLUTE.fullmatch(url)
    return (
        found is not None
        and not _has_control(url)
        and (not https_only or found.group(1) == "https")
    )


def _picture(url: str, *, https_only: bool = False) -> bool:
    """An absolute address or a path on this site."""
    return _absolute(url, https_only=https_only) or _site_path(url)


_KIND = re.compile(r"[a-z]+(?:\.[a-z_]+)?")


@dataclass(frozen=True)
class Page:
    """One public page: its head, its words and its JSON-LD.

    `words` is the builders' `Html`, or a list of them; any plain text in it
    is escaped. `data` holds JSON-LD objects. `image` is an absolute http(s)
    address or a path on this site, `kind` an Open Graph type (`website`,
    `article`), and `query` the part of the canonical after the path
    (`?page=2`): the page's, never the request's."""

    title: str
    description: str
    words: Any
    data: Sequence[Mapping[str, Any]] = ()
    image: str | None = None
    kind: str = "website"
    published: date | datetime | None = None
    modified: date | datetime | None = None
    noindex: bool = False
    query: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "words", Html(_join([self.words])))
        data = tuple(self.data)
        if not all(isinstance(item, Mapping) for item in data):
            raise ValueError("A page's data is JSON-LD objects (dicts).")
        object.__setattr__(self, "data", data)
        if not _KIND.fullmatch(self.kind):
            raise ValueError(f"{self.kind!r} isn't an Open Graph type, such as website or article.")
        if self.query and not (
            self.query.startswith("?")
            and "#" not in self.query
            and not _has_control(self.query)
            and " " not in self.query
        ):
            raise ValueError(f"{self.query!r} isn't a query, such as ?page=2.")
        if self.image and not _picture(self.image):
            raise ValueError(f"{self.image!r} isn't an http(s) address or a path on this site.")


@dataclass(frozen=True)
class Moved:
    """A page that lives somewhere else now: a 301 (or a 302 when not
    `permanent`) to `path`, a path on this site, which may end in a query and
    a fragment. Without a query of its own, the request's query goes with it,
    before the fragment."""

    path: str
    permanent: bool = True

    def __post_init__(self) -> None:
        if not _site_path(self.path):
            raise ValueError(f"{self.path!r} isn't a path on this site.")


@dataclass(frozen=True)
class Entry:
    """A page for the sitemap: its path, when it last changed, and, with a
    title, a link in llms.txt. A `noindex` page is in neither."""

    path: str
    modified: date | datetime | None = None
    title: str | None = None
    description: str | None = None
    noindex: bool = False

    def __post_init__(self) -> None:
        if not _site_path(self.path) or "?" in self.path or "#" in self.path:
            raise ValueError(f"{self.path!r} isn't a path on this site.")


class Pages:
    """What a module answers for its public pages (its `server_copy.py`'s
    `PAGES`), from the same rows its API reads."""

    async def page(
        self, db: AsyncSession, path: str, params: Mapping[str, str]
    ) -> Page | Moved | None:
        """The page at `path`, which one of the module's `routes.public`
        patterns matched, with that pattern's `:name` parts as `params`.
        None is a 404. A database error is a 503 ("try later")."""
        raise NotImplementedError

    async def sitemap(self, db: AsyncSession) -> Iterable[Entry]:
        """Every public page, for sitemap.xml and llms.txt."""
        return ()


@dataclass(frozen=True)
class SitePages:
    """The site's own pages (`create_app(site=...)`, decision 0048): its
    `backend/app/site/pages.py`'s `SITE_PAGES`. They're always on, with no switch on
    Features, and answer as a module's do: `public` patterns with their
    `pages`, `member` ones in the shell with noindex. At the same rank the
    site's pattern wins over a module's, and the start logs it; a module's
    pattern with more fixed segments still wins.

    `name` heads the site's links in llms.txt."""

    public: tuple[str, ...] = ()
    member: tuple[str, ...] = ()
    pages: Pages | None = None
    name: str = "Pages"


# --- which module answers ----------------------------------------------------------------------


_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+|:[a-z_][a-z0-9_]*")


@dataclass(frozen=True)
class _Pattern:
    module: str
    text: str
    parts: tuple[str, ...]
    member: bool

    @property
    def rank(self) -> int:
        return sum(1 for part in self.parts if not part.startswith(":"))

    def match(self, segments: tuple[str, ...]) -> dict[str, str] | None:
        if len(segments) != len(self.parts):
            return None
        params = {}
        for part, segment in zip(self.parts, segments, strict=True):
            if part.startswith(":"):
                params[part[1:]] = segment
            elif part != segment:
                return None
        return params

    def meets(self, other: _Pattern) -> bool:
        """Whether some address matches both."""
        return len(self.parts) == len(other.parts) and all(
            mine == theirs or mine.startswith(":") or theirs.startswith(":")
            for mine, theirs in zip(self.parts, other.parts, strict=True)
        )


def _parse(module_id: str, text: str, member: bool) -> _Pattern:
    parts = () if text == "/" else tuple(text[1:].split("/"))
    names = [part for part in parts if part.startswith(":")]
    if (
        not text.startswith("/")
        or not all(_SEGMENT.fullmatch(part) and part not in (".", "..") for part in parts)
        or len(names) != len(set(names))
        or (parts and parts[0] in _RESERVED)
        or text in KERNEL_FILES
    ):
        raise ValueError(
            f"{module_id}'s route {text} can't be a page: a path of fixed segments and "
            ":names, with no trailing slash, outside /api, /admin and the kernel's files."
        )
    return _Pattern(module_id, text, parts, member)


@dataclass(frozen=True)
class Match:
    """The module that answers an address, the pattern that matched, its
    `:name` parts, and whether it's a member page."""

    module: str
    pattern: str
    params: dict[str, str]
    member: bool


class Routes:
    """The public and member pages of the modules installed, checked at start."""

    def __init__(
        self, patterns: list[_Pattern], pages: dict[str, Pages], names: dict[str, str]
    ) -> None:
        #: Most fixed segments first, the site's before a module's at one rank:
        #: the first match is the one that answers.
        self._patterns = sorted(
            patterns, key=lambda pattern: (-pattern.rank, pattern.module != SITE)
        )
        self._pages = pages
        self._names = names

    def resolve(self, path: str, on: frozenset[str] | None = None) -> Match | None:
        """The pattern that answers `path`, a path with no trailing slash,
        among the modules `on` (every module installed when None) and the
        site's own, which are always on: a module that's off steps aside, so
        its pattern never keeps an address from a module on whose pattern also
        takes it. A kernel page is no module's, so the shell, the sitemap and
        llms.txt all leave it to the kernel; nor is an address with a trailing
        slash, which the shell moves to the one without it (cubic on #79)."""
        if path in KERNEL_PAGE_TITLES or (path != "/" and path.endswith("/")):
            return None
        segments = () if path == "/" else tuple(path[1:].split("/"))
        for pattern in self._patterns:
            if on is not None and pattern.module not in on and pattern.module != SITE:
                continue
            params = pattern.match(segments)
            if params is not None:
                return Match(pattern.module, pattern.text, params, pattern.member)
        return None

    def home_owner(self, on: frozenset[str] | None = None) -> str | None:
        """The module on whose public page `/` is, if any."""
        found = self.resolve("/", on)
        return found.module if found is not None and not found.member else None

    @property
    def owns_home(self) -> bool:
        return self.home_owner() is not None

    def pages_of(self, module_id: str) -> Pages:
        return self._pages[module_id]

    def name(self, module_id: str) -> str:
        return self._names.get(module_id, module_id)

    def with_pages(self) -> list[str]:
        return sorted(self._pages)


def _site_patterns(site: SitePages) -> tuple[list[_Pattern], Pages | None]:
    if site.pages is not None and not isinstance(site.pages, Pages):
        raise ValueError("The site's pages must be a server_copy.Pages.")
    if site.public and site.pages is None:
        raise ValueError("The site lists public pages but gives no pages (app/site/pages.py).")
    if site.pages is not None and not site.public:
        raise ValueError("The site gives pages but lists no public pages to answer with them.")
    patterns = [_parse(SITE, text, False) for text in site.public]
    patterns += [_parse(SITE, text, True) for text in site.member]
    return patterns, site.pages


def build(installed: Iterable[InstalledModule], site: SitePages | None = None) -> Routes:
    """The modules' pages and the site's own, checked: `routes.public` and
    `pages` together, every pattern one the kernel can take, and no two
    answering the same address at the same rank, but for the site's against a
    module's, where the site's wins and the log says so. Raises ValueError."""
    patterns: list[_Pattern] = []
    pages: dict[str, Pages] = {}
    names: dict[str, str] = {}
    if site is not None:
        found, site_pages = _site_patterns(site)
        patterns += found
        names[SITE] = site.name
        if site_pages is not None:
            pages[SITE] = site_pages
    for module in installed:
        if module.id == SITE:
            raise ValueError(f"{SITE} names the site's own pages: a module can't take it.")
        routes = module.manifest.raw.get("routes") or {}
        public = list(routes.get("public") or [])
        member = list(routes.get("member") or [])
        names[module.id] = module.manifest.name
        if module.pages is not None and not isinstance(module.pages, Pages):
            raise ValueError(f"{module.id}'s pages must be a server_copy.Pages.")
        if public and module.pages is None:
            raise ValueError(
                f"{module.id} lists public routes but has no pages (its server_copy.py's PAGES)."
            )
        if module.pages is not None and not public:
            raise ValueError(f"{module.id} has pages but no public routes (module.json's routes).")
        if module.pages is not None:
            pages[module.id] = module.pages
        patterns += [_parse(module.id, text, False) for text in public]
        patterns += [_parse(module.id, text, True) for text in member]
    for pattern in patterns:
        _check_kernel_pages(pattern)
    for number, first in enumerate(patterns):
        for second in patterns[number + 1 :]:
            if first.rank != second.rank or not first.meets(second):
                continue
            if (first.module == SITE) != (second.module == SITE):
                ours, theirs = (first, second) if first.module == SITE else (second, first)
                log.warning(
                    "The site's %s takes the place of %s's %s.",
                    ours.text,
                    theirs.module,
                    theirs.text,
                )
                continue
            raise ValueError(
                f"{first.module}'s {first.text} and {second.module}'s {second.text} answer "
                "the same addresses at the same rank: give one more fixed segments."
            )
    return Routes(patterns, pages, names)


_KERNEL_PATTERNS = tuple(
    _Pattern(KERNEL, page.path, tuple(page.path[1:].split("/")), page.access == "member")
    for page in KERNEL_PAGES
)


def _check_kernel_pages(pattern: _Pattern) -> None:
    """Refuses a pattern that takes one of the kernel's pages under the
    kernel's own first segment (`/sign-in`, `/account/:tab`, `/auth/:step`).
    One that starts with a `:name` (`/:slug`) may meet them: the shell and
    the router answer a kernel page first, as the more fixed (change 9)."""
    if not pattern.parts or pattern.parts[0].startswith(":"):
        return
    for page in _KERNEL_PATTERNS:
        if pattern.meets(page):
            raise ValueError(
                f"{pattern.module}'s route {pattern.text} takes the kernel's page {page.text}: "
                "fill the kernel's slots instead (account.section for an account page)."
            )


# --- the site's identity -----------------------------------------------------------------------


def _no_nul(value: str) -> str:
    if chr(0) in value:
        raise ValueError("The text holds a NUL character.")
    return value


class SiteSettings(BaseModel):
    """The site's identity: the settings section `kernel.site`."""

    model_config = ConfigDict(extra="forbid")

    #: The default home page's description, and llms.txt's.
    description: str = Field(default="", max_length=300)
    #: What the site is, for the home page's JSON-LD.
    kind: Literal["Organization", "LocalBusiness", "MusicGroup", "Person"] = "Organization"
    #: An https address or a path on this site.
    logo: str = Field(default="", max_length=2000)
    #: The picture a page without one of its own is shared with.
    card_image: str = Field(default="", max_length=2000)
    #: The site's profiles elsewhere (JSON-LD's sameAs).
    same_as: list[str] = Field(default_factory=list, max_length=20)
    #: llms.txt's summary, after the description.
    llms_summary: str = Field(default="", max_length=2000)
    #: Whether the AI crawlers may read the site (robots.txt).
    ai_crawlers: Literal["allow", "refuse"] = "allow"

    @field_validator("description", "llms_summary")
    @classmethod
    def _text(cls, value: str) -> str:
        return _no_nul(value)

    @field_validator("logo", "card_image")
    @classmethod
    def _pictures(cls, value: str) -> str:
        if value and not _picture(value, https_only=True):
            raise ValueError(f"{value!r} isn't an https address or a path on this site.")
        return value

    @field_validator("same_as")
    @classmethod
    def _profiles(cls, value: list[str]) -> list[str]:
        for given in value:
            if len(given) > 2000 or not _absolute(given):
                raise ValueError(f"{given!r} isn't an http(s) address.")
        return value


@dataclass(frozen=True)
class Identity:
    """The site's name and address (SITE_NAME, SITE_URL) and its saved identity."""

    name: str
    url: str
    description: str = ""
    kind: Literal["Organization", "LocalBusiness", "MusicGroup", "Person"] = "Organization"
    logo: str = ""
    card_image: str = ""
    same_as: tuple[str, ...] = ()
    llms_summary: str = ""
    ai_crawlers: Literal["allow", "refuse"] = "allow"


@dataclass
class _Installed:
    name: str = "MechFrame site"
    url: str = "http://localhost:8000"


_site = _Installed()


def install(*, site_name: str, site_url: str) -> None:
    """The site's name and address, as `create_app` reads them."""
    _site.name = site_name
    _site.url = site_url.strip().rstrip("/")


def named() -> Identity:
    """The site's name and address alone, for an answer that reads nothing."""
    return Identity(name=_site.name, url=_site.url)


async def identity(db: AsyncSession) -> Identity:
    """The site's identity: its name and address, and the section `kernel.site`."""
    saved = cast(SiteSettings, await settings.for_module(db, SECTION))
    return Identity(
        name=_site.name,
        url=_site.url,
        description=saved.description,
        kind=saved.kind,
        logo=saved.logo,
        card_image=saved.card_image,
        same_as=tuple(saved.same_as),
        llms_summary=saved.llms_summary,
        ai_crawlers=saved.ai_crawlers,
    )


# --- the head ------------------------------------------------------------------------------------


def _encoded(path: str) -> str:
    """A path as a URL writes it: percent-encoded, parentheses too, so it
    can stand in a Markdown link."""
    return quote(path, safe="/!$&'*+,;=:@")


def absolute(url: str, site_url: str) -> str:
    """`url` as an absolute address: an http(s) one as it is, a path on this site."""
    if url.startswith(("https://", "http://")):
        return url
    return f"{site_url}/{url.lstrip('/')}"


def _attr(value: str) -> str:
    return html.escape(value, quote=True)


#: JSON's escapes for the characters that could end a script block or start
#: markup in it, so no value can close the tag.
_JSON_SAFE = {ord("<"): chr(92) + "u003c", ord(">"): chr(92) + "u003e", ord("&"): chr(92) + "u0026"}


def json_ld(data: Mapping[str, Any]) -> str:
    """One JSON-LD object as a data block no value can close."""
    text = json.dumps(data, ensure_ascii=False).translate(_JSON_SAFE)
    return f'<script type="application/ld+json">{text}</script>'


def _stamp(when: date | datetime) -> str:
    if isinstance(when, datetime) and when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.isoformat()


def head(page: Page, path: str, site: Identity) -> str:
    """A page's head tags, every value escaped and every URL absolute."""
    url = site.url + _encoded(path) + page.query
    image = page.image or site.card_image
    tags = [f"<title>{_attr(page.title)}</title>"]
    if page.description:
        tags.append(f'<meta name="description" content="{_attr(page.description)}" />')
    if page.noindex:
        tags.append('<meta name="robots" content="noindex" />')
    tags += [
        f'<link rel="canonical" href="{_attr(url)}" />',
        f'<meta property="og:title" content="{_attr(page.title)}" />',
    ]
    if page.description:
        tags.append(f'<meta property="og:description" content="{_attr(page.description)}" />')
    tags += [
        f'<meta property="og:url" content="{_attr(url)}" />',
        f'<meta property="og:type" content="{_attr(page.kind)}" />',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{_attr(absolute(image, site.url))}" />')
    tags += [
        f'<meta property="og:site_name" content="{_attr(site.name)}" />',
        f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}" />',
    ]
    if page.published is not None:
        tags.append(
            f'<meta property="article:published_time" content="{_stamp(page.published)}" />'
        )
    if page.modified is not None:
        tags.append(f'<meta property="article:modified_time" content="{_stamp(page.modified)}" />')
    tags += [json_ld(item) for item in page.data]
    return "\n    ".join(tags)


def plain_head(title: str, site: Identity) -> str:
    """The head of an answer that isn't a page to index (a 404, a member or
    admin page, a 503): its title, noindex and the site's name."""
    return "\n    ".join(
        [
            f"<title>{_attr(title)}</title>",
            '<meta name="robots" content="noindex" />',
            f'<meta property="og:site_name" content="{_attr(site.name)}" />',
        ]
    )


def words(page: Page) -> str:
    """A page's words, cleaned to the allowlist whatever made them."""
    return _WORDS.clean(str(page.words))


def home(site: Identity) -> Page:
    """The kernel's home page, until a module declares `/`: the site's name,
    its description, and the site as an Organization (or the kind it is)."""
    found: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": site.kind,
        "name": site.name,
        "url": site.url + "/",
    }
    if site.description:
        found["description"] = site.description
    if site.logo:
        found["image" if site.kind == "Person" else "logo"] = absolute(site.logo, site.url)
    if site.same_as:
        found["sameAs"] = list(site.same_as)
    return Page(
        site.name,
        site.description,
        [h1(site.name), p(site.description) if site.description else None],
        data=(found,),
    )


# --- the kernel's files -------------------------------------------------------------------------


async def entries(db: AsyncSession, routes: Routes, on: frozenset[str]) -> list[tuple[str, Entry]]:
    """Every page the sitemap and llms.txt list, by module: the kernel's home
    page while neither the site nor a module on owns `/`, then the site's
    entries and each module on's that aren't `noindex` and that its own
    public pattern answers among the modules on."""
    found: list[tuple[str, Entry]] = []
    if routes.home_owner(on) is None:
        found.append((KERNEL, Entry("/")))
    owners = routes.with_pages()
    for module_id in sorted(owners, key=lambda owner: owner != SITE):
        if module_id not in on and module_id != SITE:
            continue
        for entry in await routes.pages_of(module_id).sitemap(db):
            answers = routes.resolve(entry.path, on)
            if entry.noindex or answers is None or answers.module != module_id or answers.member:
                continue
            found.append((module_id, entry))
    return found


def sitemap_xml(found: Sequence[tuple[str, Entry]], site_url: str) -> str:
    """sitemap.xml: the first 50,000 entries, absolute, with lastmod."""
    if len(found) > MAX_SITEMAP:
        log.warning(
            "The sitemap has %s addresses; it lists the first %s.",
            f"{len(found):,}",
            f"{MAX_SITEMAP:,}",
        )
        found = found[:MAX_SITEMAP]
    lines = []
    for _module, entry in found:
        lastmod = f"<lastmod>{_stamp(entry.modified)}</lastmod>" if entry.modified else ""
        lines.append(
            f"  <url><loc>{xml_escape(site_url + _encoded(entry.path))}</loc>{lastmod}</url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(line + "\n" for line in lines)
        + "</urlset>\n"
    )


#: What robots.txt closes: the admin, anchored so a public `/administration`
#: stays open, and the API. Member pages stay open: their shell says noindex,
#: which a crawler can only read if it may fetch the page, and a wildcard rule
#: for them would also close any public page sharing their prefix
#: (CodeRabbit on #73).
_CLOSED = ("Disallow: /admin$", "Disallow: /admin/", "Disallow: /admin?", "Disallow: /api/")


def robots_txt(site: Identity) -> str:
    """robots.txt: the site open to every crawler but the admin and the API.
    The AI crawlers get a group of their own (a crawler obeys only the group
    that names it), with the same rules, or `Disallow: /` while the site
    refuses them."""
    closed = list(_CLOSED)
    lines = ["User-agent: *", "Allow: /", *closed, ""]
    lines.append("# The AI crawlers, by name: the site's own choice (kernel.site, ai_crawlers).")
    lines += [f"User-agent: {agent}" for agent in AI_CRAWLERS]
    lines += ["Disallow: /"] if site.ai_crawlers == "refuse" else ["Allow: /", *closed]
    lines += ["", f"Sitemap: {site.url}/sitemap.xml", ""]
    return "\n".join(lines)


def _line(text: str) -> str:
    return " ".join(text.split())


def _label(text: str) -> str:
    return _line(text).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def llms_txt(found: Sequence[tuple[str, Entry]], routes: Routes, site: Identity) -> str:
    """llms.txt (llmstxt.org): the site's name, description and summary, then
    a section per module of its titled pages, at most 500 links."""
    out = [f"# {_line(site.name)}", ""]
    if site.description:
        out += [f"> {_line(site.description)}", ""]
    if site.llms_summary.strip():
        out += [site.llms_summary.strip(), ""]
    sections: dict[str, list[str]] = {}
    links = 0
    for module_id, entry in found:
        if not entry.title:
            continue
        if links == MAX_LLMS_LINKS:
            break
        line = f"- [{_label(entry.title)}]({site.url}{_encoded(entry.path)})"
        if entry.description:
            line += f": {_line(entry.description)}"
        sections.setdefault(module_id, []).append(line)
        links += 1
    for module_id, lines in sections.items():
        out += [f"## {_line(routes.name(module_id))}", "", *lines, ""]
    return "\n".join(out).rstrip("\n") + "\n"
