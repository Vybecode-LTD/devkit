---
name: devkit-hook-designer
description: Add a cross-module hook to the AI DevKit contract, a slot every module can fill (search index, consent categories, entitlements, taxonomy, content lifecycle, seed data and the like). Checks what SPEC.md already offers, picks the smallest shape (manifest field, fixed-name module part, kernel API, UI slot or event), then lands the spec text, JSON Schema, kernel registry, template stub, tests seen failing first, the module-contract-lint row, the decision record and the change-log line together. Use when a decision says the spec needs a new hook, or when two modules are about to solve the same cross-cutting problem in different ways.
---

# DevKit hook designer

A hook is a contract point that many modules fill in the same way, so a shared module (site search, the privacy center, memberships) can work across all of them without importing any of them. Without one, each module bolts the feature on its own way and the shared module can't be built later.

`SPEC.md` in the DevKit repo is the contract and its only copy (decision 0017). Re-read sections 5 to 11 and 16 before starting. Where this skill and the spec disagree, the spec wins.

## The rules that matter most

- **Reuse before adding.** Most "new" hooks are a small extension of a point the spec already has. A new kind of extension point is the last resort.
- **Optional by default.** A module that doesn't take part declares nothing and loses nothing. The kernel treats an absent part as "doesn't take part", never as an error.
- **Language-neutral.** Anything a hook puts on the wire is JSON Schema, RFC 9457 errors or a documented HTTP route, so the TypeScript port path (decision 0004) stays cheap.
- **No module imports another.** A hook is how the kernel, or a module listed in `requires.modules`, reaches every module. It never adds a cross-module import.
- **One hook per PR.** The spec change, its tests and its records land together (`docs/decisions/README.md`).

## Step 1: check what the spec already has

Read the sections below and write down, for the hook you're adding, whether each point already covers part of it.

| Extension point | Where in SPEC.md | Already used for |
| --- | --- | --- |
| Manifest field | 5 (`module.json`), `schema/module.schema.json` | `data_hooks`, `notifications`, `jobs`, `slots`, `events` |
| Fixed-name module part, found by the kernel | 7 (decision 0009), 9, 10 | `router.py`'s `router`, `schemas.py`'s `Settings`, `__init__.py`'s `CSP`, `server_copy.py`'s functions, `export_user_data` / `delete_user_data` |
| Kernel public API | 6 (each row has a "Since" phase) | `require_permission`, `notify`, `moderation`, `rate_limit` |
| UI slot | 8 | `admin.dashboard.widget`, `account.section`, `nav.*`, `site.footer` |
| Kernel event | 11 | `auth.user.deleted`, `kernel.module.disabled`, `kernel.settings.changed` |
| Kernel-owned table or file | 9, 10 | `kernel_event_outbox`, `sitemap.xml`, `llms.txt` |

If the spec already covers the whole hook, the job shrinks to: confirm it, add the missing contract test, and add the lint row. Say so in the PR.

## Step 2: pick the shape

Choose by what the hook carries. A hook often needs two shapes, such as a manifest field so agents can see it and a module part the kernel calls.

| The hook carries | Shape | Example |
| --- | --- | --- |
| A fact an agent or the CLI needs before any code runs | Manifest field, optional in the schema | Which content types take tags |
| Something the kernel calls on every module that takes part | Fixed-name part, discovered the way `CSP` is | `search.py`'s `documents()` |
| Something modules call | Kernel public API, with a "Since" phase | `require_access(resource)` |
| UI a module contributes | Slot | `profile.tab` |
| A reaction to a change elsewhere | Kernel event | `kernel.consent.changed` |
| Shared data every module points at | Kernel table (`kernel_` prefix), reached through the kernel API | Taxonomy terms |

Naming: manifest fields are snake_case; parts are fixed file and function names; slots are dotted lowercase; events follow `<owner>.<entity>.<past-tense verb>`. Modules may reference kernel tables but never another module's tables (section 10), so shared data the hook needs belongs to the kernel.

Write the shape down in three sentences before touching code: what a module declares or provides, what the kernel does with it, and what happens when a module doesn't take part.

## Step 3: tests first

Write these and see each one fail before the change (CLAUDE.md "Tests first").

1. **Kernel unit test** with two fake modules, one that takes part and one that doesn't. Both must load, and only the first must show up in the hook's results. Put it beside the code it tests in `kernel/tests/`.
2. **Schema test** in `tests/test_schemas.py` when there is a manifest field: one manifest that passes and one that breaks each new rule.
3. **Contract test** in `kernel/tests/contract/` when the hook shows on the HTTP API. It calls routes only, never the kernel's Python, and uses the harness's `/api/_test` routes for time and mail (decision 0010).
4. **A mutant check.** Remove the hook's core line and confirm a test fails. A test that passes either way proves nothing.

## Step 4: make the change

In one branch:

- **SPEC.md.** Put each piece where its kind already lives: manifest fields in 5's table and example, kernel API in 6 with its "Since" phase, module files in 4's layout and 7, slots in 8, data rules in 10, events in 11. Never renumber sections. Use MUST / SHOULD / MAY, and say what happens when a module doesn't take part. If section 16's quality gate gains a check, add it there.
- **Hooks index.** Keep one table at the end of section 7, "Hooks every module can fill": hook, shape, sections that define it. The first hook PR creates it, and each later PR adds a row.
- **Schema and checker.** `schema/module.schema.json` (the field optional, with `additionalProperties: false` kept), plus any rule a JSON Schema can't say in `tools/validate_schemas.py`.
- **Kernel.** An attribute on `InstalledModule` in `kernel/backend/kernel/modules.py`, and discovery where modules are actually found: `discover()` in `harness/registry.py` reads it with `_attribute()`, the way it reads `CSP`. A test that builds `InstalledModule` by hand passes without that line, so test discovery too. Then any registry or table with its migration on the `kernel` branch, and the public name in `kernel/__init__.py`.
- **Template.** `modules/_template`: the manifest's default value, an empty stub of the part, and a line under "Extension points" in `MODULE.md`.
- **Agent docs.** A row for the hook in `skills/module-contract-lint/SKILL.md`, and a step in `skills/devkit-module-extractor/SKILL.md` when extractions must fill it. The owner's account copies of both skills then need the same edit at the next skill batch, so note it in `docs/SKILL-BACKLOG.md`.
- **catalog.json.** Only if picking modules needs the new field (section 17).

## Step 5: records

- `docs/decisions/NNNN-<slug>.md` in the house format: Date, Status, Context, Decision, Alternatives, Consequences, See. When a batch of hooks was decided together, one record covers the batch: the first PR adds it, and each later PR updates its Status line with the hooks applied so far.
- A row in `docs/decisions/README.md`.
- A line in SPEC.md's change log: the date, the change, the decision number and the sections touched.
- `CLAUDE.md` and `AGENTS.md` "Last Completed Task", and `docs/HANDOFF.md`.
- Tell the owner which spec sections changed, so they know what to read.

## Step 6: verify

From the repo root, in PowerShell, with the test Postgres up (CLAUDE.md, "Test Postgres"). `DEVKIT_REQUIRE_DB` makes a database test fail rather than skip when Postgres isn't reachable, so the registry and migration tests can't pass by not running:

```
python -m tools.validate_schemas
$env:DEVKIT_REQUIRE_DB = "1"
python -m pytest
python -m ruff check . ; python -m black --check . ; python -m mypy
npm run lint ; npm run typecheck ; npm test      # when the web side changed
```

Then run `module-contract-lint` on `modules/_template`. Run VybeSite's brand check only if code was lifted from VybeSite.

## Report

```markdown
## Hook: <name> (decision NNNN)
**Shape:** <manifest field / part / API / slot / event>: <three sentences from step 2>
**Already in the spec:** <what was reused, with sections>
**Spec sections changed:** <list>
| Check | Result | Evidence |
| --- | --- | --- |
| Tests seen failing first | pass | <test names> |
| Mutant caught | pass | <which line, which test> |
| validate_schemas, pytest, ruff, black, mypy | pass | <counts> |
**Follow-ups:** <account copies of skills to update, modules to retrofit>
```

## The first batch: the roadmap hooks of 2026-11-13

The owner decided these when they picked the post-v1.0 modules (decision 0018, `docs/plans/module-roadmap.md`). The status column reflects SPEC.md on 2026-11-13; check again before starting, since it changes.

| Hook | Needed by | In the spec already | Likely shape |
| --- | --- | --- | --- |
| Export and erase | privacy-center | Yes: `data_hooks` (5) and `export_user_data` / `delete_user_data` (10); 14.13 tests delete only | Confirm; add an export contract test |
| Dashboard cards | setup-wizard, fleet | Partly: the `admin.dashboard.widget` slot (8) | Setup-checklist steps as a manifest field or a fixed-name part with a live check |
| Profile tabs | profiles | Partly: `account.section` is the member's own page | A public `profile.tab` slot plus a rule that it shows only public data |
| Search index | site-search, semantic-search, concierge, docs | No: 10 says Postgres full-text search in v1 | Fixed-name `search.py` returning documents, a kernel index table, reindex on events |
| Consent categories | consent, analytics-adapters, social-feeds, video | No: `CSP` hosts carry no category | A category on each `CSP` entry, the front end holding scripts and iframes until consent |
| Entitlements | memberships, member-only video, ai-studio | No: roles and permissions only (14.8) | Kernel `require_access(resource)` with providers registered by modules |
| Bot check | bot-shield, forms, reviews, submissions | No: `rate_limit` only | A kernel API dependency with a provider adapter and one setting |
| Content lifecycle | editorial-calendar, drops, podcast, changelog, announcements | No | Kernel columns and a mixin for status and `publish_at`, and one publishing job |
| Taxonomy | directory, recipes, docs, wiki | No | Kernel term tables, with the content types each module tags listed in its manifest |
| Seed data | catalog-site, visual-regression, theme-generator | No | A fixed-name seed part per module, run by a CLI command, never in production |

Also decided: i18n is a v1 rule (no hard-coded UI strings) rather than a hook, and flags wait until A/B testing is wanted.
