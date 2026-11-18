# Handoff

Overwritten every session. 2026-11-17, night Eastern (Claude Code, the owner's machine): K3 public rendering (#73, decision 0041), built tests first to its approved contract, with thirteen changes after approval recorded in the contract. #72 had already landed, and the session landed #73 itself. Then this page (#74).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3, in decision 0029's order:** storage (#58, 0032), email (#59, 0033), the kernel's mails (#60), jobs (#63, 0035), events (#65, 0036), audit (#67, 0037), notifications (#69, 0038), moderation (#71, 0039), and now **public rendering** (#73, 0041; contract `dev plans/contracts/k3-public-rendering.md`):
  - `kernel.server_copy`: a module's `server_copy.py` sets `PAGES`, a `server_copy.Pages` whose `page(db, path, params)` answers each address its `routes.public` patterns match with a `Page` (head, words, JSON-LD), a `Moved` or None (404), in one read; `sitemap(db)` lists `Entry`s (`noindex` keeps one out; a titled one is in `llms.txt`). More fixed segments win; the start refuses ties, `routes.public` without pages or the reverse, and patterns under `/api`, `/admin` or on a kernel file.
  - The builders (`h1` ... `article`) escape every value; `cleaned` puts HTML made elsewhere through nh3 (new, hash-pinned) without `h1`; the finished words are cleaned again.
  - `kernel.shell`: `WEB_DIST`'s `index.html` is the shell, refused at start without its `page-head`/`page-body` markers; unset, a minimal shell. Files only from inside the folder; `/assets` immutable; trailing-slash 301; noindex shells for member and admin pages; real 404s; 503 with `Retry-After` when rows can't be read; HEAD as GET. The catch-all is registered last and never matches `/api`.
  - `sitemap.xml`, `robots.txt` (AI crawlers in their own group, refused by `kernel.site`'s `ai_crawlers`; it closes `/admin` and `/api/` only, member pages being `noindex` in their shell) and `llms.txt`, per request from the modules on. Matching, the sitemap and the home page use the modules that are on. The site's identity is the settings section `kernel.site`; the kernel's home page answers `/` until a module on declares it.
- **Review (all fixed in the PR, each with a failing-first test):** Codex: a `Moved` with a fragment took the request's query into the fragment. CodeRabbit: matching must use the modules on; a failed module-switch read left the transaction aborted and made a page a 503 (`_on` rolls back now); and two `robots.txt` findings on member-page rules, which led to dropping them (see the question below).
- **Tests:** last local run 1,684 passed, 8 skipped, 27 strict expected failures; coverage 98.50 %, `server_copy.py` and `shell.py` at 100 %; 35 of 35 mutants killed. The harness was checked live with `curl` (no JavaScript): `/` one `h1` and its words, a missing address a real 404.
- **Decision 0040 (the owner):** K4's admin shell to the Vibrant Mindz canvas Admin design, styled by tokens (amends 0008).

## Next

1. Done: K3's gate passed (#75), and the rename to MechFrame landed (#76).
2. K4 (the admin shell to decision 0040; mount with `createRoot` and style or hide `[data-server-copy]`; the Playwright parity test with the first React page), K5 (the site template sets `WEB_DIST`), the ten hooks, the site's steps 1 to 7.

## Open questions for the owner

- **Settled by the owner (2026-11-17):** member pages stay `noindex` in their shell, not disallowed in `robots.txt` (contract change 8, decision 0041 item 8).
- **K3's gate:** Retention and the AI client are `later` in `progress.json` but in KICKOFF's K3 table: is the gate checked without them?
- **main's push runs are red** on `npm audit`: GHSA-fc5q-39xc-vjpf (picomatch ReDoS) covers every version through 4.0.7, the latest, with no fix; it reaches only dev tooling. Pull requests that don't touch web paths skip that job. A ready allowlist (expiring, fails when stale) is parked in `dev plans/npm-audit-allowlist/`; changing the CI gate is yours to approve. Or wait for upstream.
- Decisions 0032 to 0039's own calls, each listed in its record: keep them?
- When to make the R2 test buckets; the desk steps (the `postgres` password; `Set-ExecutionPolicy` if wanted).
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner commits it.

## Notes

- **httpx drops a HEAD answer's body itself:** a HEAD test through it can't see whether the app sent one. Check the ASGI messages (`test_head_drops_the_body_from_the_messages_themselves`).
- **A review finding can change what the approved contract said:** say so in its "Changes after approval", the decision and SPEC, and tell the owner (robots.txt above).
- **A mutant that survives may be redundant output but real behaviour:** the off-module check in `entries` was; a test that the off module isn't read at all killed it.
- **A test's secret must not be able to appear in a random id:** `token=abc` turned up inside `shop-abc88e5e` (main's 17:13 UTC run). Use letters a hex id can't hold.
- **An `ON CONFLICT` on a partial unique index** names its predicate as literal SQL.
- **Never `--cov=kernel.<module>`**: it breaks the fixtures. Use `--cov=kernel`.
- Long heredocs with quotes break the Bash tool: write scripts with the Write tool. Working-tree files are CRLF.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code; it bans some short phrases, test data included.
- Editing CI's security gates is the owner's call: the auto-mode classifier refuses it, rightly.
