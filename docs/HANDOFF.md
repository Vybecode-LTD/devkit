# Handoff

Overwritten every session. This one: 2026-11-20, night Eastern (Claude Code, the owner's machine). #96 landed at `407dadb`. This session wrote the ten hooks' contract, which the owner approved, and built hook 1 as #97, which holds this handoff.

## State

- **The kernel is done**, K0 to K5. K2's steps 9 to 11 still wait for the site (decision 0029). K5's gate and the kernel's close are in `dev plans/2026-11-20-k5-gate-evidence.md`.
- **The ten contract hooks** are approved (`dev plans/contracts/hooks.md`, decision 0052; the owner: "Approve as recommended"). One PR each, in this order: content lifecycle, taxonomy, search index, seed data, bot check, consent categories, export and erase, dashboard cards, entitlements, profile tabs.
- **Hook 1, content lifecycle, is #97:**
  - `kernel.lifecycle`: the `Publishable` mixin with its CHECK and due index, `publish`, `schedule`, `unpublish`, `visible`, `columns()` and `table_args()`, and the kernel's `kernel.publish_due` job, every minute;
  - module.json's optional `content_types`, checked by `tools.validate_schemas`;
  - discovery of `lifecycle.py`'s `PUBLISHABLE`, and the start's checks;
  - the probe's publishable notes, with a public page, on `harness.probe.TABLES`;
  - SPEC 5, 6, 7 (the new index "Hooks every module can fill"), 10 and 11.
  - The full suite locally: 2,397 passed and 2 lists updated after (the kernel's events, the worker's jobs); coverage 98.10 %, `lifecycle.py` 99.3 %. Three mutants caught.
- **v1.0:** 67 % (41 of 61 steps).

## Next

1. **Land #97** once "CI result" is green and no thread is open; then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **Hook 2, taxonomy** (the contract's §2 and §3): the prompt is `dev plans/2026-11-20-next-session-hook-taxonomy.md`.
3. Hooks 3 to 10 in order, then wave 1's modules. The first module closes the `MODULE.md` check gap (SPEC 16's Docs row).

## Open questions for the owner

- **A public name and handle for a person,** before hook 10 (the contract's §8, answer 4).
- **`mechframe-iac-probe`** on Railway isn't needed now: deleting it is yours.
- **A Railway variable to confirm a destructive migration** at pre-deploy (decision 0049)? A site's Railway plan in its CI (it needs a project token as an Actions secret)?
- **Four unused ledger assets:** `cd100445…`, `0f244b76…`, `7889d809…` and `e6e668c9…`. Delete them?
- **cubic and CodeRabbit limits:** pay, or drop them?
- Rewording the kernel's screens; decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps; renaming the folder and the `devkit-*` skills.

## Notes

- **The full suite takes about 30 minutes** under load now (1,770 s), not 13. Run it in the background with its log in the scratchpad.
- **A hook's contract test** calls only routes listed in `docs/contracts/auth-api.md` (else `UnknownRoute`). Addresses outside the API, such as a public page or `sitemap.xml`, take `extensions=UNCHECKED`.
- **`POST /api/_test/jobs {"name": "kernel.publish_due"}`** runs a scheduled kernel job on demand: `jobs/run` never ticks the scheduler.
- **Adding a kernel event or job** means updating `test_the_kernel_declares_the_eleven_events_it_emits` and `test_create_worker_builds_what_create_app_would`.
- **The Bash tool decodes `\n`, `\r` and `\uXXXX`,** and some heredocs break on quotes: write patch scripts with the Write tool and run them.
- **The ledger's `check` record** changes only when the page is republished, not when its dataset is, so it can't confirm a rows upload. Confirm with the uploaded file's sha256.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code (bot check's `form` provider lifts `contact_filter.py`).
- Editing CI's security gates is the owner's call. Never apply a site's `railway.ts` for the owner.
