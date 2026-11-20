# Handoff

Overwritten every session. This one: 2026-11-19, night, to 2026-11-20, morning Eastern (Claude Code, the owner's machine). #86 had landed at `68bcc89`. K4.8, settings and System, landed as #87 by fast-forward (`a1f89e6`, 2026-11-20 05:23 Eastern). #88, the role-change event and this handoff, is open.

## State

- **K0 to K3 are done.** K2 steps 9 to 11 wait (decision 0029).
- **K4** (contract `dev plans/contracts/k4-web-kernel.md`, decision 0042): all eight PRs are in: #78, #79, #80, #82, #83, #84, #85 and #87. Its gate (contract §7) is next.
- **#87, K4.8** (contract change 19, decision 0046):
  - **Backend, contract tests first** (`kernel/tests/contract/test_settings_system_contract.py`, seen failing as `NotBuilt`): `kernel/admin.py` serves each settings section's form, save and history (`kernel.settings.manage`), the module list and switch (`kernel.module.manage`, audited, emitting `kernel.module.enabled` and `disabled`), and System with its failed jobs, retry and discard (`kernel.jobs.manage`). The rows are in `docs/contracts/auth-api.md`.
  - **The owner's calls:** the sign-up mode is the settings section `kernel.auth`, defaulting to `SIGN_UP_MODE` (`auth/sign_up.py`). A failed job whose sealed contents were wiped, or that nothing declares, can only be discarded.
  - **Retry** deletes the failed row and queues a new job with a new id, so a stale worker's claim (id, state, tries) can't land on it. It is audited with `queued_as`.
  - **Test support:** `harness/probe.py` adds the modules `probe` and `probe-addon` (which requires it), for the test app only, and `POST /api/_test/jobs` makes jobs over HTTP.
  - **Screens:** `Site.tsx`, `Features.tsx` and `System.tsx` under `SettingsPage.tsx`'s tab links. `useSettings` (`@/kernel`) is the form hook a module's settings section uses; `settings/group.ts` joins it to the Site tab's one Save and to the question asked on leaving with unsaved changes.
  - **By eye:** `dev plans/2026-11-19-k48-settings-system/`.
  - **Review:** Codex's three findings and every CodeRabbit round were fixed with failing-first tests. CodeRabbit's review of the last head was rate-limited. cubic is at its trial's review limit.
  - **Tests on the last head:** Vitest 490, Playwright 73, CI green. The whole Python suite: 2,124 passed at 98.24 % on an earlier head, and 2,126 passed on #88's merge of main (no coverage).
- **#88** (decision 0045 amended, contract change 20): a grant emits `auth.user.role_changed` `{user_id, added, removed}`, so every kernel event in SPEC 11's table is now emitted. It also marks K4.8 done in the progress file.
- **v1.0:** 58 % (35 of 60 steps) once #88 lands. The ledger's `steps` dataset still points at `41c2879`'s rows, so republish it after #88.

## Next

1. Land #88 (if it is still open), then republish the ledger.
2. **K4's gate** (contract §7; progress.json's K4 `gate`). Run every check on `main`, then write the evidence as K3's was (`dev plans/2026-11-17-k3-gate-evidence.md`).
3. K5 (`KICKOFF.md`): the site template and the CLI.

## Open questions for the owner

- **A name for a person:** the boards greet "Big Haas", but nothing sets `display_name` yet.
- **The kernel's screens' words:** no way for a site to reword them is planned.
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?
- cubic is at its trial limit: pay for it, or drop it.
- The ledger's replaced asset `cd100445…` is unused: delete it?
- `C:\dev plans\` is a stray folder left by a screenshot path; the owner deletes it (the safety check stopped me).

## Notes

- **`useSettings`** keeps three things apart: what it read, the version an edit began from, and what a save in flight sent. A field set back while its save is on its way is still an edit. Read its tests before changing it.
- **Playwright paths** resolve from the config's folder: `../../dev plans` landed at `C:\dev plans`.
- **Coverage measured while files change** reports the wrong lines (`admin.py` read 68 %; it is 99 %). Measure on a still tree.
- **Flaky under load:** K4.7's role e2e test failed once, then passed alone and on re-runs. The long admin axe test needs `test.setTimeout(60_000)`.
- **The audit scanner** accepts only literal action names, so `set_enabled` calls `audit.record` twice, once per action.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first.
