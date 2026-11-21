# 0052: The ten contract hooks: their shapes and their order

- **Date:** 2026-11-20
- **Status:** Accepted (the owner approved `dev plans/contracts/hooks.md` "as recommended", 2026-11-20). Hooks applied to SPEC.md so far: 1, content lifecycle (#97); 2, taxonomy (#98); 3, search index (#99); 4, seed data (#102). Amended 2026-11-21 (the owner): hooks 9 and 10 wait (item 11).
- **Context:** Decision 0018 put ten hooks into SPEC.md before v1.0 freezes, one PR each, with `mechframe-hook-designer`. Each needed an exact shape: what a module declares, what the kernel does, and what a module that doesn't take part loses (nothing). Vibrant Mindz's step-1 modules (`media`, `pages`, `blog`, `embeds`, `contact`, `campaigns`) are extracted next, and they need some of the hooks from their first commit. Building the contract settled:
  - which hooks share a manifest field;
  - the order;
  - what export and erase still lacks: 14.7's export isn't built, and its contract test needs it;
  - consent's default for a new site;
  - where the contract tests' fake module lives.
- **Decision:**
  1. **One shared manifest field,** `content_types: [{key, label, lifecycle, taxonomy, search}]`, optional, `key` being `<id>.<entity>`. Hooks 1 to 3 hang off it, so an agent reads a module's content before any code runs. Each hook's PR adds its own flag.
  2. **The shapes** are the contract's §2 table: content lifecycle, taxonomy, search index, seed data, bot check, consent categories, export and erase, dashboard cards, entitlements and profile tabs, each with its exact names.
  3. **The order** puts step 1's needs first: lifecycle (blog), taxonomy (blog's topics), search (it listens to lifecycle), seed data, bot check (contact), consent (embeds), export and erase (contact, campaigns), dashboard cards and entitlements (step 5), and profile tabs (wave 2b).
  4. **Export (hook 7):** its PR builds 14.7's account export, a ZIP of JSON made as a job and mailed as a link, since its contract test needs it. Deletion stays with K2's step 11 (decision 0029).
  5. **Consent's default** is `CONSENT_MODE=ask`. Clicking an embed's facade grants `media`, so visitors see no change, and analytics waits for the consent banner.
  6. **A public name and handle** for profile tabs: asked again before hook 10, since the contract made no recommendation.
  7. **The fake module:** the harness's `probe` fills every hook and `probe-addon` none, so each hook's tests compare a module that takes part with one that doesn't. Their tables live on a metadata of their own (`harness.probe.TABLES`), which the test support makes when its app starts, so no migration or migration check sees them.
  8. **Hook 1, content lifecycle (#97):** `kernel.lifecycle`'s `Publishable` mixin gives a model `status`, `publish_at` and `published_at`, a CHECK and a partial index. `publish`, `schedule` and `unpublish` change them in the caller's transaction and emit `kernel.content.published` and `kernel.content.unpublished`. The kernel's `kernel.publish_due` job publishes what's due every minute, dated at its time, and `visible(Model)` is the one public WHERE. `published_at` keeps the first publication.
  9. **Hook 2, taxonomy (#98):** module.json's `vocabularies` and `content_types[].taxonomy`, with the kernel's three tables (`kernel_0013`). `taxonomy.tag(db, type, id, vocabulary, slugs)` takes the vocabulary, since a type can take several, and sets that vocabulary's terms to exactly the slugs, making any missing, each held FOR KEY SHARE so a deletion waits; a second tagging of the same thing in the same vocabulary waits for the first (an advisory lock, Codex on #98), so two at once never leave both's terms. `GET /api/kernel/terms` lists a vocabulary's terms in pages while a module declaring it is on. Staff's changes lock the vocabulary's row, so no two moves make a circle. A 404 has codes of its own (`kernel.vocabulary_not_found`, `kernel.term_not_found`), since the contract suite reads `kernel.not_found` as a route not built.
  10. **Hook 3, search index (#99):** module.json's `content_types[].search`, and `search.py`'s `SEARCH`, a tuple of `search.Source` (one per type, as `PUBLISHABLE` is), each answering one thing (`document`) and all of them (`documents`). The kernel's table `kernel_search_document` (`kernel_0014`) keeps each document's words as a stored generated column, so Postgres alone writes `tsv`. The kernel hears `kernel.content.published` and `.unpublished` with jobs of its own (`kernel.search_published`, `kernel.search_unpublished`), and either asks the source for the thing as it is now, so deliveries in any order leave the index right; a lifecycle row that isn't published is kept out whatever the source answers. `index` and `remove` serve content without lifecycle and edits. Changes of one document take turns (an advisory lock), and a reindex of a type holds that type's lock alone, so nothing changed meanwhile is lost. The reindex job is `kernel.search_reindex`: a job's name has one dot. `SEARCH_LANGUAGE` is one of Postgres 16's own configurations, checked at start. Snippets are plain text.
  11. **The order, amended (the owner, 2026-11-21):** hooks 4 to 8 next, then Vibrant Mindz's step 1. Hook 9, entitlements, lands just before step 5 (`downloads`), and hook 10, profile tabs, before wave 2b (`profiles`), which may be after v1.0 freezes. Step 1's modules need neither, and start about a session sooner. The plan: `dev plans/2026-11-21-vibrant-mindz-push-plan.md`.
- **Alternatives:**
  - All ten hooks before step 1, as first ordered: step 1's modules would wait on two hooks they don't use.
  - A search table in each module, or one index per module: a site search couldn't rank across them.
  - Indexing inside `lifecycle.publish`: every module's publish would wait on search, and an edit would still need `index`. The events were made for this listener.
  - Postgres triggers on each module's table: the kernel would write SQL into tables it doesn't own.
  - Flags of their own for each hook rather than `content_types`: three fields saying the same thing.
  - A publishing job in each module: every module would schedule its own way, and an editorial calendar couldn't read them.
  - `visible` showing a scheduled row whose time has passed, so nothing waits on the job: the published date and the events would then lag what the public sees.
  - A term table in each module: the blog's topics and the docs' topics couldn't be one list, and a site search couldn't facet across them.
  - Leaving the export route to K2's step 11: hook 7's contract test would have nothing to call.
  - `CONSENT_MODE=off` by default: simpler, but analytics would run before anyone agreed.
- **Consequences:**
  - Ten PRs from #97, each with its SPEC change-log line, an index row at the end of SPEC 7, and a `module-contract-lint` row.
  - The owner's account copies of `module-contract-lint` and `mechframe-module-extractor` need each hook's row at the next skill batch (`docs/SKILL-BACKLOG.md`).
  - A blog's scheduled post shows within a minute of its time.
  - `harness.probe` grows a little with each hook.
- **See:** `dev plans/contracts/hooks.md`; decisions 0018, 0029, 0035 (jobs), 0036 (events); SPEC.md sections 5, 6, 7, 10, 11 and 14.11; `skills/mechframe-hook-designer/SKILL.md`
