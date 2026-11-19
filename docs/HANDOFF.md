# Handoff

Overwritten every session. This one: 2026-11-19, afternoon Eastern (Claude Code, the owner's machine). #83 had landed at `8eab4db`. K4.6, the admin shell, is #84, this page in it.

## State

- **K0 to K3 are done.** K2 steps 9 to 11 wait (decision 0029).
- **K4** (contract `dev plans/contracts/k4-web-kernel.md`, decision 0042): six of its eight PRs are in: #78, #79, #80, #82, #83 and #84.
- **#84, K4.6** (contract change 17, decision 0044):
  - **Backend, tests first:** `GET /api/kernel/admin/attention` (`kernel/attention.py`; six tests in `kernel/tests/test_attention.py`, seen failing): the failed jobs (danger) for `kernel.settings.manage` and `kernel.jobs.manage`, the site's missing description (warning) and card picture (info) for `kernel.settings.manage`, the worst first. `kernel.jobs.manage` landed here (`kernel_0011`, admin by default). The staff's log answers `people` and `kept_days` and takes several `action`s (`docs/contracts/auth-api.md`, SPEC 14.10).
  - **The frame** (`kernel/web/src/admin/`): the sidebar as sections with a section's pages under the open one; the person's card; the breadcrumb; Ctrl K (`JumpTo`); the notices from the bell (`Notices`); View site; Menu under 960px. `AdminPage` is in `@/kernel` for modules' admin pages.
  - **Screens:** Dashboard (greeting, "Needs you", the modules' `admin.dashboard.widget` cards) and Activity (who did what to whom, by kind, an entry's fields beneath, the keep). The kit gains `StatCard` and the info tone (`color.info`, `color.info-tint`; Machined Light's `info-700` `#2864B8`).
  - **Left off, not faked:** a person's name (the session has none: the email stands in); role names come from ids until K4.7; Activity's search, Export CSV, and Content and Money kinds; the Dashboard's checklist and figures.
  - **By eye:** `dev plans/2026-11-19-k46-admin/`, with what differs from the boards.
  - **Review:** CodeRabbit's five findings fixed with failing-first tests: the phone's Menu reopening on a return to where it was opened, Mark all read failing silently, the notices and "Needs you" blank while read, and the e2e lookup of the admin's sign-in now paging past the newest fifty. A race in #83's step-up test (the Password field is drawn after two reads) showed under load and now waits for the field.
  - **Tests on the last head:** Vitest 430; Playwright 67 (`admin.spec.ts` 9); Python 2,051 at 98.58 % (the review touched no Python).
- **v1.0:** 55 % (33 of 60 steps).

## Next

1. **K4.7, people and roles** (contract §4 item 7; additions 4 and 5): People, Roles with New role and editing, `auth.role.manage` in `kernel.json` with its grant migration (`kernel_0012`). The auth threat checklist applies. The person card's and Activity's role names can then come from the roles read.
2. **Then K4.8,** settings and System (additions 6 to 8). `kernel.jobs.manage` is already in; the dead-jobs list, retry and discard use it.

## Open questions for the owner

- **A name for a person:** the boards greet "Big Haas"; nothing sets `display_name` yet (sign-up takes none). Add it to the account page and the session?
- **The sign-in screens' words:** a way for a site to reword kernel screens is unplanned.
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website (that project's session)?
- `C:\DEV\knowledge\owner.md` is uncommitted; the owner commits it.

## Notes

- **The e2e server for a look:** `E2E_PORT=8770 TEST_DATABASE_URL=... python -m harness.e2e`; wait for `/api/kernel/health` to answer 200 before the first call. Setup calls made from inside the page (`page.evaluate(fetch)`) share its cookies and pass the origin check. Stop it before a Playwright run: both use `mechframe_e2e`.
- **An admin page's breadcrumb** ends in the sidebar's name for the page unless `AdminPage`'s `crumb` says otherwise.
- **Kernel audit actions** each need staff words and a kind (`kernel/web/src/admin/actions.ts`); `Activity.test.tsx` reads `KERNEL_ACTIONS` from `audit.py` and fails on one without.
- **Traps:** a pinned count in `tests/test_theme_vibrant_mindz.py` moves with every alias and colour role. `npx.cmd playwright test -g "..."` with a space breaks its quoting; pick by `file:line`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first.
