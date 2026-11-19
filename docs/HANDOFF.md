# Handoff

Overwritten every session. This one: 2026-11-19, evening Eastern (Claude Code, the owner's machine). #84 had landed at `5f7f987`. K4.7, people and roles, is #85, this page in it.

## State

- **K0 to K3 are done.** K2 steps 9 to 11 wait (decision 0029).
- **K4** (contract `dev plans/contracts/k4-web-kernel.md`, decision 0042): seven of its eight PRs are in or open: #78, #79, #80, #82, #83, #84 and #85.
- **#85, K4.7** (contract change 18, decision 0045):
  - **Backend, contract tests first** (`kernel/tests/contract/test_people_roles_contract.py`, 27 tests, all seen failing as `NotBuilt`; the eight admin tests marked not built since K2 now run): `GET /api/auth/admin/users`, `PUT .../roles`, `GET /api/auth/admin/roles`, and role editing (`POST`, `PUT`, `DELETE /api/auth/admin/roles…`) in `kernel/auth/roles.py`. Every refusal has a test, and a holder's next request carries a new token. `auth.role.manage` with migration `kernel_0012` (admin). Written down in `docs/contracts/auth-api.md`.
  - **Rules:** only the roles a change adds or removes are judged; `member` is no rank; a role edit is judged on every permission it has or would have; 404 `auth.role_not_found` (a `kernel.not_found` reads as not built in the suite).
  - **Locks:** a grant locks both accounts, then `owner`'s role row when it removes `owner`, then key-share on the other roles; deleting a role locks it for update. `kernel/tests/auth/test_roles.py` holds each race open; each failed with its lock taken out.
  - **Screens:** `kernel/web/src/admin/People.tsx` (search, roles by name, second factor, last seen, standing, Open to switch roles) and `Roles.tsx` (cards with counts, the permissions matrix in groups, New role and Edit for the site's own roles); `roleAccess.ts` names roles and says ahead what the server will refuse. The person card names roles from the roles read.
  - **Left off, not faked:** invites, Export, the role chips, reminders, suspending from People, names, the board's "own".
  - **By eye:** `dev plans/2026-11-19-k47-people-roles/`.
  - **Tests on the last head:** see #85's body.
- **v1.0:** 56 % (34 of 60 steps).

## Next

1. **Land #85** once "CI result" is green and the bots are clear; then republish the ledger.
2. **K4.8, settings and System** (additions 6 to 8). `kernel.jobs.manage` is already in; the dead-jobs list, retry and discard use it.

## Open questions for the owner

- **A name for a person:** the boards greet "Big Haas"; nothing sets `display_name` yet. People shows `name` once something sets it.
- **The sign-in screens' words:** a way for a site to reword kernel screens is unplanned.
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?
- `C:\DEV\knowledge\owner.md` is uncommitted; the owner commits it.

## Notes

- **SQLAlchemy 2.1:** `Result.tuples()` is deprecated (the suite treats warnings as errors), and `dict(result)` misreads a `Result` (it has `keys()`): build dicts with a comprehension.
- **Windows:** `roles.ts` and `Roles.tsx` in one folder collide (case-insensitive disk); the helper is `roleAccess.ts`.
- **The audit scanner** (`test_audit.py`) reads a file that imports `from kernel import audit` as calling the kernel's `record`, wherever it sits.
- **Flaky under load:** `test_an_undo_link_outlives_the_owners_reset` (a 5 s mail wait) failed once beside other suites and passed alone twice.
- **Traps:** a pinned count in `tests/test_theme_vibrant_mindz.py` moves with every alias. `npx.cmd playwright test -g "..."` with a space breaks its quoting; pick by `file:line`.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first.
