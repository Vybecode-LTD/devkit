---
feature: K3 public rendering (kernel.server_copy: the shell, each page's head and words, sitemap.xml, robots.txt, llms.txt)
status: approved
approved: 2026-11-17 (the owner: "Approve as recommended", all five answers)
plan: KICKOFF.md K3 ("Public rendering"); docs/HANDOFF.md, Next
pr: 73 (predicted; #72 is the handoff)
---

# Contract: K3 public rendering (`kernel.server_copy`)

## 1. Goal

Every public address of a DevKit site answers a crawler that runs no JavaScript (GPTBot, ClaudeBot, PerplexityBot, link previews) with that page's own head tags, its words as plain semantic HTML and its JSON-LD, inside the app's shell. An address the site doesn't have is a real 404, never a 200 shell. A module gets this by answering one question per page, `page(db, path, params)`, from the same rows its API reads. The kernel also writes `sitemap.xml`, `robots.txt` (AI crawlers allowed unless the site turns them away) and `llms.txt` from what the modules on say, and serves the built web app with VybeSite's path-safety and cache rules.

## 2. Interfaces

`kernel/backend/kernel/server_copy.py`, public as `from kernel import server_copy`.

**A module with public pages** gives `InstalledModule(pages=...)` an object from its `server_copy.py`. The start refuses a module whose `routes.public` and `pages` don't come together.

```python
class Pages(server_copy.Pages):
    async def page(self, db: AsyncSession, path: str, params: Mapping[str, str]) -> server_copy.Page | server_copy.Moved | None: ...
    async def sitemap(self, db: AsyncSession) -> Iterable[server_copy.Entry]: ...
```

- `params` are the `:name` parts of the module's `routes.public` pattern that matched. `None` is a 404.
- `Page(title, description, words, data=(), image=None, kind="website", published=None, modified=None, noindex=False, query="")`:
  - `words` comes from the kernel's builders (`h1`, `h2`, `h3`, `p`, `ul`, `link`, `time`, `section`, `article`, `cleaned`), which escape every value.
  - `data` holds JSON-LD dicts.
  - `query` is the part of the canonical after the path (`?page=2`).
- `Moved(path, permanent=True)`: a 301 (or 302) to a path on this site, never `//host`.
- `Entry(path, modified=None, title=None, description=None)`. With a title, the page also joins `llms.txt`.

**Which module answers:** the kernel matches the path against the `routes.public` patterns of the modules on.
- A pattern with more fixed segments wins over one with fewer.
- The start refuses two modules whose patterns match the same addresses with the same rank.
- `/` belongs to whichever module declares it. Without one, the kernel's default home page answers: the site's name and description, and its Organization JSON-LD.

**What an address answers** (the catch-all route, registered last, `public`):

| Address | Answer |
| --- | --- |
| A module's page | 200, the shell with the page's head tags between `<!-- page-head -->` markers, its words in `<div data-server-copy>` between `<!-- page-body -->` markers, and its JSON-LD |
| A trailing slash (not `/`) | 301 without it, query kept |
| `Moved` | 301 or 302 to its path |
| A `routes.member` page | 200, the shell, `noindex`, the site's name as title, no words |
| `/admin` and below | 200, the shell, `noindex`, "Admin · {name}", no words |
| A real file in `WEB_DIST` | The file. `/assets/*` gets `public, max-age=31536000, immutable`. Only a file inside the folder is ever served: `..`, encoded separators and symlinks are refused |
| `/api/...` that no route answers | 404 `kernel.not_found` as problem JSON, never the shell |
| Anything else, `None`, a module off | 404, the shell, `noindex`, "Page not found · {name}" |
| A page whose rows can't be read | 503 with `Retry-After`, never a 404 for a page that may exist |

**Every answer's head and shell:**
- The head carries the title, description, an absolute canonical, `og:title`, `og:description`, an absolute `og:url`, `og:type` (a type value: `website`, `article`), an absolute `og:image` (the page's, else the site's card), `og:site_name`, `twitter:card`, and `article:published_time` and `article:modified_time` when given.
- The shell is sent `Cache-Control: no-cache`. HEAD is answered as GET, without the body.
- JSON-LD goes in `<script type="application/ld+json">`, escaped so no value can close the tag. The CSP is unchanged, since a data block never runs.
- With `WEB_DIST` unset, the kernel's own minimal shell is used: no scripts, the same markers.

**Kernel files** (`public`, generated per request from the modules on):
- `GET /sitemap.xml`: every `Entry` whose page isn't `noindex`, absolute, with `lastmod`. At most 50,000; past that, the first 50,000 and a warning in the log.
- `GET /robots.txt`: `Allow: /`, with `/admin`, `/api/` and every module's `routes.member` disallowed, and the `Sitemap:` line. The AI crawlers (GPTBot, ChatGPT-User, OAI-SearchBot, ClaudeBot, Claude-User, anthropic-ai, PerplexityBot, Google-Extended, Applebot-Extended, CCBot) get a group of their own: `Allow: /` by default, `Disallow: /` while the site refuses them. `ROBOTS_NOINDEX` keeps its `X-Robots-Tag` on every answer.
- `GET /llms.txt` (llmstxt.org): `# {name}`, `> {description}`, the site's summary, then a `## {module name}` section per module listing its titled entries as `- [title](url): description`. At most 500 links.

**Site identity** is the settings section `kernel.site`, saved through `settings.save`. It holds:
- `description`: up to 300 characters, the default home page's and `llms.txt`'s
- `kind`: `Organization`, `LocalBusiness`, `MusicGroup` or `Person`, for the home page's JSON-LD
- `logo` and `card_image`: absolute https or site paths
- `same_as`: up to 20 profile URLs
- `llms_summary`: up to 2,000 characters
- `ai_crawlers`: `allow` or `refuse`, `allow` by default

The name stays `SITE_NAME`. A module's page can read it all through `server_copy.identity(db)`.

**Config:** `WEB_DIST`, the built web app's folder (default unset).

## 3. Data

None: no tables. The settings section above is a row in `kernel_setting`.

## 4. Files

**New:**

- `kernel/backend/kernel/server_copy.py`: pages, matching, builders, head, JSON-LD, the kernel files
- `kernel/backend/kernel/shell.py`: serving `WEB_DIST` and the shell
- `kernel/tests/test_server_copy.py`
- `kernel/tests/test_shell.py`
- `docs/decisions/0041-public-rendering.md`

**Changed:**

- `kernel/__init__.py`
- `modules.py`: `pages`, and the routes check
- `app.py`: the kernel files, the catch-all last, the settings section
- `config.py`: `web_dist`
- `.env.example`
- `modules/_template/backend/my_module/server_copy.py`
- `SPEC.md`: 6, 7, 9 and the change log
- `requirements*.in/.txt`, if `cleaned` uses nh3 (question 4)
- `docs/TESTING.md`, the Stack in `CLAUDE.md`/`AGENTS.md`, `docs/progress.json`

## 5. Conventions this follows

- **Skill:** `server-copy-for-crawlers`.
- **Ported, not copied:**
  - VybeSite `site_routes.py`: the head markers, `render`'s tags, every URL absolute, 404 with noindex, admin's own title, redirects only to the site's own paths.
  - VybeSite `spa.py`: path containment, the cache headers, `/api/` misses as JSON 404, HEAD as GET, 503 never 404.
  - VybeSite `site_html.py`: one `h1`, no `style`, everything escaped, JSON-LD the server's.
  - VybeSite `routers/sitemap.py`: generated per request, from the parts on.
- **Kernel patterns:** `settings.py` for the section, and `modules.py` for checks at start.
- **Directive:** `C:\DEV\SEO_OPTIMIZATION.md`: AI crawler access, canonical, one `h1`, JSON-LD.

## 6. Non-goals

- No React server rendering and no hydration. K4's shell mounts with `createRoot`, which replaces the words, and K4 styles or hides them.
- No Playwright parity test yet: it comes with K4's first React page, the tooling included.
- No sitemap index, image, video or news sitemaps, hreflang or other languages.
- No caching of rendered pages, no CDN purge, no IndexNow or search-console files.
- No redirects table or admin page: a module returns `Moved` for its own old addresses, and a redirects module comes later.
- No capitals-to-lowercase redirects, no automatic breadcrumbs, and no per-page meta editing (modules and K4).
- No change to the CSP, and no inline script but JSON-LD.

## 7. Acceptance

**`test_server_copy.py`:**

- Matching: fixed segments win, ties refused at start, a module off is 404, and `routes.public` and `pages` must come together.
- Each URL-valued head tag (canonical, `og:url`, `og:image`) is absolute, every tag escaped, `og:image` falls back to the card, and JSON-LD can't close its tag.
- The builders escape everything and `words` never holds `style` or `script`.
- The default home page.
- `sitemap.xml`: only the modules on, `noindex` out, the cap.
- `robots.txt`: allow and refuse, member and admin disallowed.
- `llms.txt`: its format and cap.
- Identity settings refuse bad values.

**`test_shell.py`:**

- Every row of the address table, the traversal attempts (`..`, `%2e%2e`, `%2f`, an absolute path, a symlink), the cache headers, HEAD, and the minimal shell.
- A 503 when the page's read fails.

**Also:**

- Full suite green, coverage at 95 % or more, both files at 100 %.
- Mutants on matching precedence, path containment, the 404 and 503 split, the escaping, and robots' refuse switch, all killed.
- A live check in the harness: `curl` a page with JavaScript off (one `h1`, words present) and a missing address (404).

## 8. Open questions

None. On 2026-11-17 the owner approved the goal and non-goals as written, with the five answers recommended:

1. **One call per page, not three?** Recommended: `page(db, path, params)` returns the head, words and JSON-LD together, so the rows are read once. SPEC 9 has `head`, `copy` and `structured_data` separately; this changes SPEC 9.
2. **Who owns `/`, and where the site's identity lives.** Recommended: `/` is whichever module declares it (Vibrant Mindz's `pages`), with a kernel default home page until one does. The identity (description, kind, logo, card, profiles) is the settings section `kernel.site`, with `MusicGroup` among the kinds for the collective.
3. **AI crawlers.** Recommended: allowed by default, each named in its own group, with the site's `ai_crawlers` switch to refuse them all (SPEC 9 and the SEO directive).
4. **A safety net under the builders?** Recommended: also clean the finished words with nh3, a tight allowlist with no `style`, `script` or event attributes. That adds nh3 as a hash-pinned dependency; SPEC 15 already names it for user HTML, and `cleaned` lets the blog pass a post's Markdown HTML through it.
5. **Serve the built web app from the kernel now?** Recommended: yes, with VybeSite's path and cache rules and a minimal shell while `WEB_DIST` is unset, so the harness and K5's site template use it as it is.

## Changes after approval

Made while building (#73); decision 0041 records them.

1. **`Entry(noindex=False)`.** The kernel can't know an entry's page is `noindex` without asking every page on each sitemap request, so the module marks the entry from the same rows it marks the page; `sitemap.xml` and `llms.txt` leave it out. The kernel also drops an entry that its module's own public pattern doesn't answer (a member page, another module's address, no address at all).
2. **The plain head.** A member page, the admin, a 404 and a 503 carry the title, `noindex` and `og:site_name` only: they have no canonical address to give, as VybeSite's 404 head has none. "Every answer's head" holds for pages.
3. **`PAGES`.** The harness finds a module's pages by the fixed name `PAGES` in its `server_copy.py`, as it finds `router`, `Settings`, `CSP` and `EMAILS` (SPEC 7).
4. **A home module that's off.** While the module that declares `/` is off, the kernel's home page answers there, not a 404.
5. **A build without the markers is refused at start,** where VybeSite served it as built with a warning.
6. **`//`, a backslash or a control character** in a path is a 404 before anything else, so the trailing-slash 301 can never be turned toward another host.
7. **The catch-all never matches `/api`** (a path convertor), so the API's misses stay 404 for every method and a wrong method on an API route stays 405, as before.
8. **robots.txt's member rules** write `:names` as `*` and end with `$`, so `/account` doesn't also close `/accountant`.
9. **What an unread identity does:** the default home page and `robots.txt` answer 503 (a 5xx robots.txt keeps crawlers out while the AI switch is unread); a module's page whose own rows were read still answers, with the site's name alone.
10. **`docs/TESTING.md`** doesn't exist in this repo: nh3 is in the Stack (`CLAUDE.md`, `AGENTS.md`) and `requirements.in`.
