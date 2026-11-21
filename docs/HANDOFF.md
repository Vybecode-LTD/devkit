# Handoff

Overwritten every session. This one: 2026-11-20, late evening Eastern (Claude Code, the owner's machine). #95 had landed at `b543642`. This session checked K5's gate and the kernel's close: #96, docs only, holds this handoff.

## State

- **The kernel is done**, K0 to K5. K2's steps 9 to 11 still wait for the site (decision 0029), so K2's `gate_passed` stays false.
- **K5's gate passed** on `main` at `b543642` (`dev plans/2026-11-20-k5-gate-evidence.md`):
  - `python -m tools.site_smoke --keep` ran 26 steps, all green. On `test-site`, kernel only: install, lint, types, migrations, 15 Python tests, Vitest, the build, Railway's types, 4 Playwright tests, then `mechframe check` exiting 0. Then again with `fixture-notes` and `fixture-pins` added.
  - Every contract §7 bullet is matched to its tests by name.
  - CI at that head: Python 2,374 passed at 98.16 %, Vitest 511 at 96.69 % of lines. E2E: Playwright 73, and the site smoke green.
- **The kernel's close** (KICKOFF), in the same file:
  - every SPEC 16 row passes in CI;
  - the auth contract tests pass, but 19 strict xfails wait for K2's steps 9 to 11;
  - gitleaks (240 commits), pip-audit, `tools.npm_audit` and the brand check are clean, and so are the new site's own two lockfiles;
  - the docs are current: `create-owner` was added to `CLAUDE.md`'s commands;
  - **the spec sections changed since K0,** by section, for the owner.
- **One gap, for the first module:** SPEC 16's Docs row has `mechframe check` find a `MODULE.md` that's missing a required section (SPEC 17). Nothing checks that yet, since no module has a `MODULE.md`.
- **v1.0:** 65 % (40 of 61 steps). The gates don't count as steps.

## Next

1. **Land #96** once "CI result" is green and no thread is open. Then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **The ten contract hooks** (decision 0018). They come before wave 1's modules (`docs/plans/vibrant-mindz-backend/KICKOFF.md` line 18; the roadmap's wave 0). Their contract goes to the owner first, then one PR per hook.
3. **Wave 1:** `media`, `pages`, `blog`, `embeds`, `contact` and `campaigns` from VybeSite. The first of them closes the `MODULE.md` gap.

The starting prompt is `dev plans/2026-11-20-next-session-modules-wave-1.md`.

## Open questions for the owner

- **`mechframe-iac-probe`** (Railway, "color8's Projects") isn't needed now that K5's gate has passed. Deleting it is yours.
- **A Railway variable to confirm a destructive migration** in the pre-deploy step (decision 0049, alternatives)?
- **Plan a site's Railway file in its CI?** It needs a project token as an Actions secret, which only you can make.
- **Three unused ledger assets:** `cd100445…`, `0f244b76…` and `7889d809…`. Delete them?
- **cubic and CodeRabbit limits:** pay, or drop them? CodeRabbit has been at its free limit since #93.
- A name for a person (nothing sets `display_name`)? A way for a site to reword the kernel's screens?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?

## Notes

- **The smoke's stdout reaches a redirected log only when it exits.** Watch `%TEMP%\mechframe-smoke-*\smoke.log` for each step as it runs. `--keep` leaves the site there; this session's is `mechframe-smoke-nm99466y`, outside the repo.
- **`tools.npm_audit` audits the repo's root lockfile only:** in a made site, run `npm audit` twice, once in its root (`package-lock.json`) and once in `web/` (`web/package-lock.json`).
- **The Bash tool decodes `\n`, `\r` and `\uXXXX`** in command text, heredocs too. Write a patch script with the Write tool and run it. Most docs are CRLF in this checkout.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call.
- Never apply a site's `railway.ts` for the owner: the apply, the project and its variables are theirs.
