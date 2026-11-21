# Handoff

Overwritten every session. This one: 2026-11-20, night Eastern (Claude Code, the owner's machine). #97 landed at `cc3929b` and the ledger was republished. This session then built hook 2 as #98, which holds this handoff.

## State

- **The kernel is done**, K0 to K5. K2's steps 9 to 11 still wait for the site (decision 0029).
- **The ten contract hooks** (`dev plans/contracts/hooks.md`, decision 0052), one PR each: content lifecycle (#97, landed), taxonomy (#98), then search index, seed data, bot check, consent categories, export and erase, dashboard cards, entitlements, profile tabs.
- **Hook 2, taxonomy, is #98:**
  - module.json's `vocabularies` and `content_types[].taxonomy`, checked by `tools.validate_schemas` and again at start (`taxonomy.build`);
  - `kernel.taxonomy`: `tag(db, type, id, vocabulary, slugs)`, `terms_for`, `tagged` and `untag_all`;
  - the tables `kernel_vocabulary`, `kernel_term` and `kernel_term_link` in `kernel_0013`, with `kernel.taxonomy.manage` seeded for admin and editor;
  - `GET /api/kernel/terms`, and `POST`, `PATCH` and `DELETE /api/kernel/admin/terms[/{id}]`, audited as `kernel.term.*`;
  - the probe's notes take `topics` (hierarchical) and `tags` (flat);
  - SPEC 5, 6, 7 (the index's second row), 10 and 14.11; the contract's "Changes after approval" says what moved from §2.
  - Five mutants caught: no unlink, no ON CONFLICT on a racing term, a vocabulary of modules off listed, a term under its own child, and a parent in a flat vocabulary.
  - Full suite locally: 2,435 passed, 8 skipped, 19 xfailed, and one failure fixed after (the migrations round trip needed seed rows for the new tables), then the affected suites rerun: 283 passed. Coverage 97.94 %, `taxonomy.py` 100 %.
- **A test-isolation fix rides in #98:** `test_lifecycle.py`'s fixture emptied `lifecycle`'s installed types on teardown, which broke the contract suite's app (built once per session) when the unit test ran first. Both hooks' fixtures now use `monkeypatch.setattr` on the module global.
- **v1.0:** 68 % (42 of 61 steps).

## Next

1. **Land #98** once "CI result" is green and no thread is open; then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **Hook 3, search index:** the prompt is `dev plans/2026-11-20-next-session-hook-search.md`.
3. Hooks 4 to 10 in order, then wave 1's modules. The first module closes the `MODULE.md` check gap (SPEC 16's Docs row).

## Open questions for the owner

- **A public name and handle for a person,** before hook 10 (the contract's §8, answer 4).
- **`mechframe-iac-probe`** on Railway isn't needed now: deleting it is yours.
- **A Railway variable to confirm a destructive migration** at pre-deploy (decision 0049)? A site's Railway plan in its CI (it needs a project token as an Actions secret)?
- **Five unused ledger assets:** `cd100445…`, `0f244b76…`, `7889d809…`, `e6e668c9…` and `5ca8682a…` (the rows before #97's). Delete them?
- **cubic and CodeRabbit limits:** pay, or drop them? CodeRabbit skipped #97's later commits.
- Rewording the kernel's screens; decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps; renaming the folder and the `devkit-*` skills.

## Notes

- **The full suite takes about 30 minutes** under load (1,770 s). Run it in the background with its log in the scratchpad.
- **A hook's contract test** calls only routes listed in `docs/contracts/auth-api.md` (else `UnknownRoute`), and a 404 `kernel.not_found` reads as a route not built (`NotBuilt`): give a missing thing a code of its own.
- **A unit test's fixture** that sets a kernel module's installed global must restore it (`monkeypatch.setattr`), not empty it: the contract suite's app reads the same global.
- **A new kernel audit action** goes in `audit.KERNEL_ACTIONS`; `test_audit.py` holds every `audit.record` call to that list.
- **`POST /api/_test/jobs {"name": "kernel.publish_due"}`** runs a scheduled kernel job on demand: `jobs/run` never ticks the scheduler.
- **Adding a kernel event or job** means updating `test_the_kernel_declares_the_eleven_events_it_emits` and `test_create_worker_builds_what_create_app_would`.
- **The Bash tool decodes `\n`, `\r` and `\uXXXX`,** and some heredocs break on quotes: write patch scripts with the Write tool and run them.
- **The ledger's `check` record** changes only when the page is republished, not when its dataset is: confirm a rows upload by the uploaded file's sha256.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code (bot check's `form` provider lifts `contact_filter.py`).
- Editing CI's security gates is the owner's call. Never apply a site's `railway.ts` for the owner.
