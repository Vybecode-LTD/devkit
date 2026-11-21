---
feature: The ten contract hooks (decision 0018), recorded as decision 0052
status: approved
approved: 2026-11-20 (the owner: "Approve as recommended"; §8's answers below)
plan: decision 0018; docs/plans/module-roadmap.md, wave 0; skills/mechframe-hook-designer/SKILL.md; docs/plans/vibrant-mindz-backend/KICKOFF.md, "Between step 0 and step 1"
pr: 97 first (predicted; #96 is the last), one PR per hook in §4's order
---

# Contract: the ten contract hooks

## 1. Goal

Every module fills the ten cross-module points the same way, so a shared module (site search, the consent banner, the privacy center, memberships, the setup wizard, profiles) can be built later without retrofitting the modules written before it. Vibrant Mindz's step-1 modules (`media`, `pages`, `blog`, `embeds`, `contact`, `campaigns`) fill the hooks they need from their first commit.

## 2. Interfaces

Each hook is optional: a module that doesn't take part declares nothing, and the kernel treats the absence as "doesn't take part", never as an error. SPEC 7 ends with the index "Hooks every module can fill" (hook, shape, sections). The first PR creates it, and each later PR adds a row.

**One shared manifest field** carries what three hooks need, so an agent sees a module's content before any code runs: `content_types`, optional, `[{key, label, lifecycle, taxonomy, search}]`. `key` is `<id>.<entity>` (as moderation kinds are), `lifecycle` and `search` are booleans defaulting to false, and `taxonomy` lists vocabulary keys, empty by default. Each of hooks 1 to 3 adds its own flag in its own PR.

| # | Hook | What a module declares or provides | What the kernel does | Spec |
| --- | --- | --- | --- | --- |
| 1 | **Content lifecycle** | Its model subclasses `lifecycle.Publishable`, which adds `status` (`draft`, `scheduled` or `published`, a `String(16)` with a CHECK), `publish_at` and `published_at` (timestamptz, null). `lifecycle.py`'s `PUBLISHABLE = (Post,)`. The manifest's `content_types[].lifecycle: true` | `lifecycle.publish(db, row)`, `schedule(db, row, at)` and `unpublish(db, row)` change the columns and emit `kernel.content.published` or `kernel.content.unpublished` (`{type, id}`) in the caller's transaction. The scheduled job `kernel.publish_due` (every minute) publishes due rows the same way. `lifecycle.visible(Model)` is the one WHERE that public reads, the server copy and the sitemap use | 5, 6, 7, 10, 11 |
| 2 | **Taxonomy** | `vocabularies: [{key, label, hierarchical}]` in the manifest, plus `content_types[].taxonomy: ["topics"]`. Two modules naming the same key share the vocabulary, and the start refuses one that disagrees on `hierarchical` | Tables `kernel_vocabulary`, `kernel_term` and `kernel_term_link` (§3). `taxonomy.tag(db, type, id, slugs)` makes any missing term, `taxonomy.terms_for(db, type, ids)`, `taxonomy.tagged(type, vocabulary, slug)` (a select of ids), `taxonomy.untag_all(db, type, id)`. `GET /api/kernel/terms?vocabulary=` (public), and admin `POST`, `PATCH` and `DELETE /api/kernel/admin/terms[/{id}]` under the new `kernel.taxonomy.manage` (admin, editor) | 5, 6, 10 |
| 3 | **Search index** | `search.py`'s `SEARCH`, a `search.Source` with `document(db, id) -> search.Document \| None` and `documents(db)` (an async iterator, for a reindex). `content_types[].search: true`. A module without lifecycle calls `search.index(db, doc)` and `search.remove(db, type, id)` itself | The table `kernel_search_document` (§3), filled in the caller's transaction. It listens to `kernel.content.*` and calls the module's `document()`. The job `kernel.search.reindex` runs on demand. `GET /api/kernel/search?q=&type=&cursor=&limit=` (public, `rate_limit("30/1m")`) answers `{items: [{type, id, title, snippet, path}], next_cursor}`, ranked by `websearch_to_tsquery` in `SEARCH_LANGUAGE` (default `english`). Public documents only | 6, 7, 10 |
| 4 | **Seed data** | `seed.py`'s `async def seed(db, ctx: seed.Context) -> None`. It is idempotent: fixed ids or slugs, upserts | `python -m app.seed` (the harness's `python -m harness.seed`), and `mechframe seed --site <dir>` runs it as `create-owner` runs `app.owner`. The kernel first, then the modules in `requires` order. `ctx` gives a fixed clock, `ctx.random` (seeded), `ctx.user(role)` and `ctx.put_image(name)`. It refuses unless `MECHFRAME_ALLOW_SEED=1`, which `.railway/railway.ts` never sets (a template test holds that) | 4, 7, 12 |
| 5 | **Bot check** | A public form's body carries `bot: kernel.BotProof` (`{website, elapsed_ms, token}`, all optional). Its service calls `await bot.verify(request, body.bot, form="contact.inquiry")` | `bot.verify` answers `bot.Pass()` or `bot.Held(reason)`. The module holds a held submission, as VybeSite's contact filter does, and never drops it silently. The provider is the setting `kernel.bot.provider`: the kernel's `form` (VybeSite's honeypot and 3-second fill time) by default, or one a module adds as `__init__.py`'s `BOT_PROVIDER` (bot-shield's Turnstile, later). Web: `<BotFields />` and `useBotProof()` in the UI kit | 6, 7, 8 |
| 6 | **Consent categories** | Each `CSP` entry gains a third item, its category: `("frame-src", "https://www.youtube-nocookie.com", "media")`. The categories are `necessary` (the default; no consent needed), `analytics`, `marketing` and `media` | The CSP itself is unchanged. `GET /api/kernel/site` gains `consent: {mode, categories}`, the categories of the modules on. Web: `useConsent(category)` gives `{granted, grant()}`, and `<ConsentGate category fallback>` holds a script or iframe until it's granted. The choice is kept in the first-party cookie `__Host-mf_consent`, set by script. `CONSENT_MODE` is `ask` (gates hold; an embed's facade click grants `media`) or `off` (all granted) | 8, 15 |
| 7 | **Export and erase** | Already in SPEC 5 and 10 (`data_hooks`). Now exact: `privacy.py`'s `export_user_data(db, subject) -> dict[str, list[dict]]` and `delete_user_data(db, subject) -> None`. `privacy.Subject` is `{user_id, email}`, so data held by address (contact inquiries, campaign contacts) is found too. The start refuses `data_hooks` that disagree with `privacy.py` | 14.7's export: `POST /api/auth/account/export` (step-up, `rate_limit("1/1h", key="account")`) enqueues `kernel.privacy.export`, which writes a ZIP of JSON (one file per module) to private storage and mails a link to `GET /api/auth/account/exports/{id}`. That route redirects the account's own signed-in owner to a 5-minute signed link. The file goes after 7 days. Deletion calls `delete_user_data` in K2's step 11 | 5, 10, 14.7 |
| 8 | **Dashboard cards** | `dashboard.py`'s `ATTENTION`, `async (db, user) -> list[attention.Item]` (each Item names its permission), and `SETUP`, a tuple of `setup.Step(key, title, why, link, permission, done)` where `done` is `async (db) -> bool` | "Needs you" (`GET /api/kernel/admin/attention`) adds the modules' items, worst first, each only for those who hold its permission. `GET /api/kernel/admin/setup` lists the steps of the modules on, each checked live. The Dashboard shows a Set up card while any step is open | 6, 7, 8 |
| 9 | **Entitlements** | `entitlements.py`'s `GRANTS`, `{kind: async (db, user_id, resource_id) -> access.Grant \| None}`, and the manifest's `grants: ["<kind>"]`. A kind is `<id>.<resource>` | `Depends(require_access(kind, param="id"))` answers 403 `kernel.no_access` unless some provider grants it. Deny by default, and any one grant opens it. `GET /api/kernel/access?kind=&id=` answers `{granted, offers: [{module, label, link}]}`, so a locked thing can say how to get it. Web: `useAccess(kind, id)`. The manifest's `grants` tells an agent which modules can open which kinds | 5, 6, 7 |
| 10 | **Profile tabs** | The slot `profile.tab`: `{label, path, lazy, permission?}`, drawn with `{userId}` | Typed in `Slots`, filtered by `useSlot` like the rest. Rule: a tab shows only what its module shows publicly. The page itself is the `profiles` module's (wave 2b) | 8 |

## 3. Data

Migrations go on the `kernel` branch, numbered from `kernel_0013` in landing order. `kernel.taxonomy.manage` gets a seed row in the migration that adds the taxonomy tables.

| Table | Columns |
| --- | --- |
| `kernel_vocabulary` | `id` uuid PK; `key` text unique; `label` text; `hierarchical` bool |
| `kernel_term` | `id` uuid PK; `vocabulary_id` FK; `parent_id` FK null; `slug`; `label`; `position` int; unique (`vocabulary_id`, `slug`) |
| `kernel_term_link` | `term_id` FK cascade; `content_type` text; `content_id` uuid; PK all three; index (`content_type`, `content_id`). No FK to a module's rows: the module calls `untag_all` when it deletes one |
| `kernel_search_document` | `content_type`, `content_id` PK; `title`; `body`; `path`; `language` regconfig; `tsv` tsvector (title weighted A, body B) with a GIN index; `updated_at` |
| `kernel_export` | `id` uuid PK; `user_id` FK cascade; `status` (`queued`, `ready` or `failed`); `storage_key` null; `created_at`; `expires_at` |

Lifecycle adds no kernel table: its columns live in each module's own table.

## 4. Files and order

Each PR follows the skill's step 4: SPEC, the index row, `schema/module.schema.json` and `tools/validate_schemas.py`, `InstalledModule` plus discovery in `harness/registry.py` and `kernel.load_module`, `kernel/__init__.py`, `modules/_template` (the default, a stub and a line under "Extension points"), the `module-contract-lint` and `mechframe-module-extractor` rows, `docs/SKILL-BACKLOG.md`, and the change-log line. `harness/probe.py`'s `probe` fills each hook and `probe-addon` doesn't, so they are the contract tests' "takes part" and "doesn't".

**The order, step 1's needs first:** 1 content lifecycle (blog), 2 taxonomy (blog's topics), 3 search index (it listens to lifecycle), 4 seed data (every module from step 1 on), 5 bot check (contact), 6 consent (embeds), 7 export and erase (contact, campaigns), 8 dashboard cards (step 5's Connect Stripe checklist), 9 entitlements (step 5's downloads), 10 profile tabs (wave 2b). The first PR also adds decision 0052. Each later PR updates its Status line with the hooks applied so far, and decision 0018's too.

## 5. Conventions this follows

`skills/mechframe-hook-designer/SKILL.md`; SPEC 5 to 11 and 16; `kernel/backend/kernel/modules.py`'s `_attribute` discovery (as `CSP` and `PAGES` are); `kernel.audit.record` (written in the caller's transaction); VybeSite's `contact_filter.py` for the `form` provider (lifted, so it gets the brand check).

## 6. Non-goals

- No admin Terms page, term picker, search page or consent banner. Those are the modules' (`site-search`, `consent`) or wait for the first module that draws one.
- Lifecycle has no `unpublish_at`, revisions or approval flow, and it's for public content only: a campaign's sends keep their own states.
- Search covers no member-only or permissioned documents, and no engine but Postgres (SPEC 10).
- Consent isn't stored server-side or per account, and the CSP doesn't change with consent.
- Bot check has no Turnstile adapter: that's `bot-shield`.
- No account deletion: that's K2's step 11 (decision 0029).
- No i18n or flags (decision 0018).

## 7. Acceptance

Per hook, tests seen failing first (the skill's step 3):

- **A kernel unit test** with `probe` and `probe-addon`: both load, and only `probe` shows in the hook's results.
- **A schema test** in `tests/test_schemas.py` for each manifest field: one manifest that passes, and one that breaks each rule.
- **A discovery test** through `harness/registry.py`.
- **A contract test** in `kernel/tests/contract/test_hook_<name>.py`, HTTP only, using `/api/_test` for time and mail:
  1. A draft is a 404 and missing from `sitemap.xml`; once it's scheduled and the clock passes `publish_at`, `jobs/run` makes it 200 and listed.
  2. Tagging shows in `GET /api/kernel/terms`; a term's `DELETE` needs `kernel.taxonomy.manage`.
  3. A published probe is found by `GET /api/kernel/search`, and unpublished, it isn't.
  4. Seeding twice leaves the same rows; without `MECHFRAME_ALLOW_SEED` it refuses.
  5. A filled `website` field, a fill under 3 seconds, or no proof at all is held; a person's form passes.
  6. `GET /api/kernel/site` lists `media` only while `probe` is on (plus a Vitest test: `<ConsentGate>` holds its child until `grant()`).
  7. The export ZIP holds `probe`'s file, not `probe-addon`'s; another account gets 404 on the link.
  8. A setup step's `done` flips live; an attention item shows only to its permission's holders.
  9. 403 `kernel.no_access` until `probe`'s provider grants, then 200.
  10. A Vitest test: `useSlot("profile.tab")` gives only entries from modules that are on.
- **A mutant caught** (the hook's core line removed fails a test), named in the PR.
- The full suite, lint and types, `module-contract-lint` on `modules/_template`, and the brand check where code is lifted.

**Done when:** all ten rows are in SPEC 7's index, each with its contract test passing in CI, and decision 0052's Status reads "all ten applied".

## Changes after approval

- 2026-11-20, hook 2 (#98): `taxonomy.tag(db, type, id, vocabulary, slugs)` takes the vocabulary, since a content type can take several, and sets that vocabulary's terms to exactly `slugs`. `GET /api/kernel/terms` pages with `cursor` and `limit` and answers 404 `kernel.vocabulary_not_found` for a vocabulary no module on declares; a missing term is 404 `kernel.term_not_found` (the contract suite reads `kernel.not_found` as a route not built). A term with children answers 409 `kernel.term_has_children` rather than taking them with it. The probe declares `tags` (flat) beside `topics` (hierarchical).
- 2026-11-21, hook 3 (#99): `SEARCH` is a tuple of `search.Source`, one per content type (as `PUBLISHABLE` is), each naming its `content_type`. The reindex job is `kernel.search_reindex`, since a job's name is `<owner>.<name>` with one dot; the kernel's listeners are `kernel.search_published` and `kernel.search_unpublished`. Either listener indexes the thing as it is now (its source's answer while it's there and published), so deliveries in any order leave the index right, and `index` keeps out a lifecycle row that isn't published. `GET /api/kernel/search` answers 422 `kernel.invalid_request` for a `type` no module on searches, `limit` is 1 to 50 (20), and the snippet is plain text. `SEARCH_LANGUAGE` is one of Postgres 16's own text search configurations, checked at start.

## 8. Open questions

None open. The owner's answers (2026-11-20, "Approve as recommended"):

1. **The shapes and the order** in §2 and §4: as written.
2. **Export (hook 7):** hook 7's PR builds 14.7's account export, which its contract test needs.
3. **Consent's default:** `ask`. An embed's facade click is the consent, and analytics waits for the banner.
4. **A public name and handle** for profile tabs: the draft gave no recommendation, so it's asked again before hook 10.
