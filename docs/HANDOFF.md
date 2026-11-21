# Handoff

Overwritten every session. This one: 2026-11-21, morning Eastern (Claude Code, the owner's machine). #98 landed at `747e5f6` and the ledger was republished. This session then built hook 3 as #99, which holds this handoff.

## State

- **The kernel is done**, K0 to K5. K2's steps 9 to 11 still wait for the site (decision 0029).
- **The ten contract hooks** (`dev plans/contracts/hooks.md`, decision 0052), one PR each: content lifecycle (#97), taxonomy (#98), search index (#99), then seed data, bot check, consent categories, export and erase, dashboard cards, entitlements, profile tabs.
- **Hook 3, search index, is #99:**
  - module.json's `content_types[].search`, and `search.py`'s `SEARCH`, a tuple of `search.Source` (`content_type`, `document(db, id)`, `documents(db)`), checked against each other at start (`search.build`);
  - `kernel.search`: `index(db, doc)` and `remove(db, type, id)` in the caller's transaction, `index` keeping out a lifecycle row that isn't published; `find` for the route;
  - the table `kernel_search_document` in `kernel_0014`: `tsv` a stored generated column (title A, body B, in the row's `language`) with a GIN index;
  - the kernel's first listeners, `app.KERNEL_LISTENERS`: `kernel.search_published` and `kernel.search_unpublished` each index the thing as it is now, so deliveries in any order leave the index right; the on-demand job `kernel.search_reindex` rebuilds each type and drops types no module searches;
  - `GET /api/kernel/search?q=&type=&cursor=&limit=`: public, 30 a minute, the modules on only, ranked by `websearch_to_tsquery` in `SEARCH_LANGUAGE` (one of Postgres 16's configurations, default `english`), a plain-text snippet, a keyset cursor over the rank; the snippet drawn from the body's first 20,000 characters (ts_headline costs ~17 ms at 100,000);
  - advisory locks: a change of one document holds its type's lock shared and its own alone; a reindex holds its type's alone;
  - the probe's notes have a body and are searchable; SPEC 5, 6, 7 (the index's third row), 10 and 14.11; the contract's "Changes after approval" says what moved from §2 (`SEARCH` a tuple; the job `kernel.search_reindex`, a job's name having one dot).
  - Nine mutants caught: no public check, no shared type lock, a listener that never removes, the types ignored, the worst first (caught once a paging test had more than a page and one), a tie's cursor repeating a document, orphans kept, the kernel's listeners not installed, a switched-off module's documents shown.
- **A fix rides in #99:** decision 0052's item 9 (taxonomy) sat under Alternatives; it's back in the Decision list.
- **v1.0:** 70 % (43 of 61 steps).

## Next

1. **Land #99** once "CI result" is green and no thread is open; then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **Hook 4, seed data:** the prompt is `dev plans/2026-11-21-next-session-hook-seed.md`.
3. Hooks 5 to 10 in order, then wave 1's modules. The first module closes the `MODULE.md` check gap (SPEC 16's Docs row).

## Open questions for the owner

- **A public name and handle for a person,** before hook 10 (the contract's §8, answer 4).
- **`mechframe-iac-probe`** on Railway isn't needed now: deleting it is yours.
- **A Railway variable to confirm a destructive migration** at pre-deploy (decision 0049)? A site's Railway plan in its CI (it needs a project token as an Actions secret)?
- **Six unused ledger assets:** `cd100445…`, `0f244b76…`, `7889d809…`, `e6e668c9…`, `5ca8682a…` and `78538570…` (the rows before #98's). Delete them?
- **cubic and CodeRabbit limits:** pay, or drop them? CodeRabbit was rate-limited on #98's last commit.
- Rewording the kernel's screens; decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps; renaming the folder and the `devkit-*` skills.

## Notes

- **The full suite takes about 30 minutes** under load. Run it in the background with its log in the scratchpad.
- **A hook's contract test** calls only routes listed in `docs/contracts/auth-api.md` (else `UnknownRoute`), and a 404 `kernel.not_found` reads as a route not built (`NotBuilt`): give a missing thing a code of its own.
- **A unit test's fixture** that sets a kernel module's installed global must restore it (`monkeypatch.setattr`), not empty it: the contract suite's app reads the same global.
- **`POST /api/_test/jobs {"name": "kernel.search_reindex"}`** runs a kernel job on demand: `jobs/run` never ticks the scheduler.
- **Adding a kernel job or listener** means updating `test_create_worker_builds_what_create_app_would`; a new kernel event, `test_the_kernel_declares_the_eleven_events_it_emits`.
- **A new config value** goes in `KernelConfig`, both `.env.example` files and `templates/site/.railway/railway.ts`.
- **The Bash tool decodes `\n`, `\r` and `\uXXXX`,** and some heredocs break on quotes: write patch scripts with the Write tool and run them.
- **The ledger's `check` record** changes only when the page is republished, not when its dataset is: confirm a rows upload by the uploaded file's sha256.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code (bot check's `form` provider lifts `contact_filter.py`).
- Editing CI's security gates is the owner's call. Never apply a site's `railway.ts` for the owner.
